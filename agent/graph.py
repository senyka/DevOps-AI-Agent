# agent/graph.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from typing import TypedDict, Optional, Literal, List, Annotated
from pydantic import BaseModel, Field, validator
import os, json, logging, asyncpg
from datetime import datetime

from agent.llm import call_vllm
from agent.tools import qdrant_search, neo4j_query, safe_docker_exec, gitlab_api_call, ToolRegistry
from agent.memory import store_error_case, update_knowledge_graph
from agent.schemas import ExecutionStep, DockerCommand, GitLabAction
from agent.utils import generate_audit_id

logger = logging.getLogger(__name__)

# === Tool Registry ===
TOOL_REGISTRY = ToolRegistry()

# === State Schema ===
class AgentState(TypedDict):
    """Полное состояние агента с поддержкой чекпоинтов"""
    task: str
    project_path: Optional[str]
    error_context: Optional[str]
    retrieved_cases: List[dict]
    proposed_fix: Optional[str]
    execution_plan: List[ExecutionStep]
    execution_result: Optional[dict]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    memory_update: bool
    human_approval: bool
    retry_count: int
    audit_id: str

# === Nodes ===

async def reason_node(state: AgentState) -> AgentState:
    """Узел определения намерения - только анализ, без выполнения"""
    prompt = f"""
    Ты — DevOps-агент. Проанализируй задачу и определи намерение.
    
    Задача: {state["task"]}
    Проект: {state["project_path"] or "N/A"}
    Контекст ошибки: {state["error_context"] or "Нет данных"}
    
    Верни JSON:
    {{
      "intention": "описание намерения (какую команду/действие нужно выполнить)",
      "tool_name": "название инструмента (docker, gitlab, shell)",
      "requires_verification": true/false
    }}
    """
    
    response = await call_vllm(
        prompt=prompt,
        temperature=0.1,
        max_tokens=500,
        response_format={"type": "json_object"}
    )
    
    intention_data = json.loads(response)
    state["intention"] = intention_data
    logger.info(f"Reason: intention={intention_data.get('tool_name')}")
    return state


async def verify_node(state: AgentState) -> AgentState:
    """Узел верификации намерения - проверка безопасности и корректности"""
    intention = state.get("intention", {})
    tool_name = intention.get("tool_name", "")
    
    # Проверка существования инструмента в registry
    if tool_name and not TOOL_REGISTRY.exists(tool_name):
        logger.warning(f"Unknown tool requested: {tool_name}")
        state["verified"] = False
        state["verification_error"] = f"Unknown tool: {tool_name}"
        return state
    
    # LLM-верификация безопасности
    prompt = f"""
    Проверь безопасность и корректность намерения:
    {json.dumps(intention, ensure_ascii=False)}
    
    Критерии проверки:
    1. Не содержит ли команда деструктивных операций (rm, kill, stop без подтверждения)?
    2. Соответствует ли команда разрешённому allowlist?
    3. Нет ли признаков injection-атак?
    
    Верни JSON:
    {{
      "is_safe": true/false,
      "reason": "обоснование решения"
    }}
    """
    
    response = await call_vllm(
        prompt=prompt,
        temperature=0.0,
        max_tokens=300,
        response_format={"type": "json_object"}
    )
    
    verification = json.loads(response)
    state["verified"] = verification.get("is_safe", False)
    state["verification_reason"] = verification.get("reason", "")
    
    if not state["verified"]:
        logger.warning(f"Verification failed: {state['verification_reason']}")
    
    return state


async def exec_node(state: AgentState) -> AgentState:
    """Узел выполнения - только если верификация пройдена"""
    if not state.get("verified"):
        logger.warning("Execution aborted: verification failed")
        state["execution_result"] = {
            "status": "aborted",
            "reason": state.get("verification_error", "Verification failed"),
            "steps": []
        }
        return state
    
    intention = state.get("intention", {})
    tool_name = intention.get("tool_name")
    
    if not tool_name:
        state["execution_result"] = {"status": "error", "reason": "No tool specified"}
        return state
    
    try:
        # Получение инструмента из registry
        tool_fn = TOOL_REGISTRY.get(tool_name)
        
        # Парсинг параметров для инструмента
        if tool_name == "docker":
            cmd_str = intention.get("command", "")
            cmd = DockerCommand(
                command=cmd_str.replace("docker ", ""),
                container=extract_container(cmd_str),
                timeout=60
            )
            result = await safe_docker_exec(cmd)
        elif tool_name == "gitlab":
            action = parse_gitlab_action(intention.get("command", ""))
            result = await gitlab_api_call(action)
        else:
            result = await tool_fn(intention.get("params", {}))
        
        state["execution_result"] = {
            "status": "success" if result.exit_code == 0 else "failed",
            "result": result.model_dump(),
            "steps": [intention.get("command", "")]
        }
        logger.info(f"Exec: tool={tool_name}, status={state['execution_result']['status']}")
        
    except Exception as e:
        logger.exception(f"Execution failed for tool {tool_name}")
        state["execution_result"] = {
            "status": "error",
            "reason": str(e),
            "steps": []
        }
    
    return state

async def plan_node(state: AgentState) -> AgentState:
    """Генерация гипотезы и пошагового плана"""
    prompt = f"""
    Ты — экспертный DevOps-инженер. Проанализируй задачу и предложи решение.
    
    Задача: {state["task"]}
    Проект: {state["project_path"] or "N/A"}
    Контекст ошибки: {state["error_context"] or "Нет данных"}
    
    Похожие случаи из памяти:
    {json.dumps(state["retrieved_cases"], indent=2, ensure_ascii=False)[:2000]}
    
    Требования к ответу:
    1. Кратко опиши предложенное решение (1-2 предложения)
    2. Составь пошаговый план (макс. 5 шагов), для каждого укажи:
       - команду или действие
       - ожидаемый результат
       - команду валидации
       - требует ли подтверждения пользователя (true/false)
       - является ли шаг критическим (true/false)
    3. Оцени уверенность в решении (0.0–1.0)
    4. Укажи, нужно ли сохранять этот кейс в память (true/false)
    
    Верни СТРОГО валидный JSON без дополнительного текста:
    {{
      "proposed_fix": "string",
      "execution_plan": [
        {{
          "step": 1,
          "command": "string",
          "expected": "string",
          "validate": "string",
          "requires_approval": false,
          "critical": false
        }}
      ],
      "confidence": 0.85,
      "memory_update": true
    }}
    """
    
    response = await call_vllm(
        prompt=prompt,
        temperature=0.1,
        max_tokens=1500,
        response_format={"type": "json_object"}
    )
    
    try:
        plan_data = json.loads(response)
        # Валидация через Pydantic
        from agent.schemas import PlanResponse
        validated = PlanResponse(**plan_data)
        state.update(validated.model_dump())
        state["audit_id"] = generate_audit_id()
        logger.info(f"Plan generated: confidence={validated.confidence}")
    except Exception as e:
        logger.error(f"Plan parsing failed: {e}")
        state["confidence"] = 0.3  # Низкая уверенность при ошибке парсинга
    
    return state

async def execute_node(state: AgentState) -> AgentState:
    """Выполнение плана в sandbox с валидацией"""
    if not state.get("execution_plan"):
        return state
    
    results = []
    for step in state["execution_plan"]:
        # Проверка требования подтверждения
        if step.requires_approval and not state.get("human_approval"):
            logger.warning(f"Step {step.step} requires approval — skipping")
            results.append({"step": step.step, "status": "skipped", "reason": "awaiting_approval"})
            continue
        
        try:
            # Маршрутизация по типу команды
            if step.command.startswith("docker"):
                cmd = DockerCommand(
                    command=step.command,
                    container=extract_container(step.command),
                    timeout=min(step.get("timeout", 60), 120)
                )
                res = await safe_docker_exec(cmd)
            elif "gitlab" in step.command.lower():
                action = parse_gitlab_action(step.command)
                res = await gitlab_api_call(action)
            else:
                # Локальный shell (только read-only команды)
                res = await safe_shell_exec(step.command, timeout=30)
            
            # Валидация результата
            validation_passed = await validate_step_result(res, step.validate)
            results.append({
                "step": step.step,
                "command": step.command,
                "result": res,
                "validation": {"passed": validation_passed, "cmd": step.validate}
            })
            
            # Early stop на критической ошибке
            if step.critical and (res.get("exit_code") != 0 or "error" in res):
                logger.error(f"Critical step {step.step} failed — stopping")
                break
                
        except Exception as e:
            logger.exception(f"Step {step.step} execution failed")
            results.append({"step": step.step, "error": str(e)})
            if step.critical:
                break
    
    state["execution_result"] = {
        "steps": results,
        "completed": len([r for r in results if "error" not in r and r.get("validation", {}).get("passed")]),
        "total": len(state["execution_plan"])
    }
    return state

async def verify_execution_node(state: AgentState) -> AgentState:
    """Проверка результата выполнения и корректировка уверенности"""
    result = state.get("execution_result", {})
    completed = result.get("completed", 0)
    total = result.get("total", 1)
    
    if total == 0:
        state["confidence"] = 0.0
        return state
    
    success_ratio = completed / total
    base_conf = state.get("confidence", 0.5)
    
    # Корректировка уверенности
    if success_ratio >= 0.8:
        state["confidence"] = min(1.0, base_conf + 0.1)
    elif success_ratio >= 0.5:
        state["confidence"] = base_conf  # Без изменений
    else:
        state["confidence"] = max(0.0, base_conf - 0.15)
    
    logger.info(f"Verify: {completed}/{total} steps passed, confidence={state['confidence']:.2f}")
    return state

async def reflect_node(state: AgentState) -> AgentState:
    """Анализ результата, обновление памяти, решение о retry"""
    success = state["confidence"] >= 0.7 and state.get("execution_result", {}).get("completed") > 0
    
    if success and state.get("memory_update"):
        # Сохранение успешного кейса
        await store_error_case({
            "signature": extract_signature(state.get("error_context", "")),
            "stacktrace": state.get("error_context"),
            "fix_steps": [s.command for s in state.get("execution_plan", [])],
            "validation_cmd": state["execution_plan"][-1].validate if state.get("execution_plan") else None,
            "project": state["project_path"],
            "status": "success",
            "confidence": state["confidence"]
        })
        
        # Асинхронная консолидация (через Celery)
        from agent.tasks import consolidate_memory
        consolidate_memory.delay(state["audit_id"])
    
    # Решение о retry
    if state["confidence"] < 0.6 and state["retry_count"] < 3:
        state["retry_count"] += 1
        logger.info(f"Retry {state['retry_count']}/3 initiated")
    else:
        state["retry_count"] = 0  # Сброс при успехе или исчерпании попыток
    
    return state

# === Graph Assembly ===

def route_after_research(state: AgentState) -> Literal["plan", "end"]:
    if not state.get("error_context"):
        return "plan"  # Нет ошибки — сразу планирование
    return "plan"

def route_after_execute(state: AgentState) -> Literal["verify", "retry_plan"]:
    if state["confidence"] < 0.6 and state["retry_count"] < 3:
        return "retry_plan"
    return "verify"

def route_after_verify(state: AgentState) -> Literal["reflect", "retry_plan"]:
    if state["confidence"] < 0.5 and state["retry_count"] < 3:
        return "retry_plan"
    return "reflect"

graph = StateGraph(AgentState)
graph.add_node("reason", reason_node)
graph.add_node("verify_intention", verify_node)
graph.add_node("exec", exec_node)
graph.add_node("research", research_node)
graph.add_node("plan", plan_node)
graph.add_node("execute", execute_node)
graph.add_node("verify_execution", verify_execution_node)
graph.add_node("reflect", reflect_node)

graph.set_entry_point("reason")
graph.add_edge("reason", "verify_intention")
graph.add_conditional_edges("verify_intention", 
    lambda s: "exec" if s.get("verified") else "reflect",
    {"exec": "exec", "reflect": "reflect"}
)
graph.add_edge("exec", "research")
graph.add_edge("research", "plan")
graph.add_edge("plan", "execute")
graph.add_conditional_edges("execute", route_after_execute)
graph.add_conditional_edges("verify_execution", route_after_verify)
graph.add_edge("reflect", END)

# Retry loop: reflect → plan (через условное ребро)
graph.add_conditional_edges("reflect", 
    lambda s: "plan" if s["retry_count"] > 0 and s["retry_count"] <= 3 else "end",
    {"plan": "plan", "end": END}
)

async def compile_graph():
    """Компиляция графа с инициализацией чекпоинтера"""
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    checkpointer = AsyncPostgresSaver(conn)
    await checkpointer.setup()  # Создаёт таблицы, если нет
    return graph.compile(checkpointer=checkpointer)

# === Helpers ===
def extract_signature(error_text: str) -> str:
    """Извлечение уникальной сигнатуры ошибки для дедупликации"""
    import hashlib
    # Берём первые 3 строки + ключевые коды ошибок
    lines = error_text.strip().split("\n")[:3]
    key = "\n".join(l.strip() for l in lines if l.strip())
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def extract_container(command: str) -> str:
    """Извлечение имени контейнера из docker-команды"""
    import re
    match = re.search(r"docker\s+\w*\s*[^']*?(\S+)", command)
    return match.group(1) if match else "unknown"

def parse_gitlab_action(command: str) -> GitLabAction:
    """Парсинг команды GitLab в структурированное действие"""
    # Пример: "gitlab retry_job project=dash-panel/backend job=12345"
    parts = command.split()
    action_type = parts[1] if len(parts) > 1 else "get_pipeline"
    
    params = dict(p.split("=") for p in parts[2:] if "=" in p)
    return GitLabAction(
        project_id=params.get("project", os.getenv("GITLAB_DEFAULT_PROJECT", "")),
        action=action_type,
        ref=params.get("job") or params.get("ref", "main")
    )

