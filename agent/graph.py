### `agent/graph.py`
**Назначение:** Определение LangGraph state machine с узлами research→plan→execute→reflect.

```python
# agent/graph.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from typing import TypedDict, Optional, Literal, List, Annotated
from pydantic import BaseModel, Field, validator
import os, json, logging, asyncpg
from datetime import datetime

from agent.llm import call_vllm
from agent.tools import qdrant_search, neo4j_query, safe_docker_exec, gitlab_api_call
from agent.memory import store_error_case, update_knowledge_graph
from agent.schemas import ExecutionStep, DockerCommand, GitLabAction

logger = logging.getLogger(__name__)

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

async def research_node(state: AgentState) -> AgentState:
    """Поиск похожих ошибок в векторной БД и графе знаний"""
    if not state.get("error_context"):
        return state  # Нет ошибки — пропускаем research
    
    # Hybrid search в Qdrant
    similar = await qdrant_search(
        query=state["error_context"],
        filter={"project": state["project_path"]} if state["project_path"] else None,
        limit=5,
        score_threshold=0.6
    )
    
    # Graph query в Neo4j
    kg_results = []
    if similar:
        sig = extract_signature(state["error_context"])
        kg_results = await neo4j_query("""
            MATCH (e:Error {signature: $sig})-[:FIXED_BY*1..2]->(s:Solution)
            WHERE s.validated = true
            RETURN s.steps AS fix_steps, s.validation_cmd, s.success_count
            ORDER BY s.success_count DESC LIMIT 3
        """, params={"sig": sig})
    
    state["retrieved_cases"] = similar + kg_results
    logger.info(f"Research: found {len(state['retrieved_cases'])} similar cases")
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

async def verify_node(state: AgentState) -> AgentState:
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
graph.add_node("research", research_node)
graph.add_node("plan", plan_node)
graph.add_node("execute", execute_node)
graph.add_node("verify", verify_node)
graph.add_node("reflect", reflect_node)

graph.set_entry_point("research")
graph.add_edge("research", "plan")
graph.add_edge("plan", "execute")
graph.add_conditional_edges("execute", route_after_execute)
graph.add_conditional_edges("verify", route_after_verify)
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

def generate_audit_id() -> str:
    import uuid, hashlib, time
    return hashlib.sha256(f"{uuid.uuid4()}{time.time()}".encode()).hexdigest()[:16]
```

---
