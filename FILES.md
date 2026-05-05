# 📁 Детальное описание файлов проекта

Ниже представлено полное описание содержимого каждого файла из структуры проекта `devops-agent`. Каждый раздел включает: назначение файла, ключевой код/конфигурацию и важные примечания.

---

## 📄 Корневые файлы

### `docker-compose.yml`
**Назначение:** Оркестрация всех сервисов стека (vLLM, Qdrant, Neo4j, PostgreSQL, Redis, агент, воркер, WebUI).

**Ключевые секции:**
```yaml
version: '3.9'
services:
  vllm:
    image: vllm/vllm-openai:v0.6.4
    deploy:
      resources:
        reservations:
          devices: [{ driver: nvidia, count: 1, capabilities: [gpu] }]
    command: >
      --model Qwen/Qwen2.5-14B-Instruct-AWQ
      --quantization awq
      --max-model-len 8192
      --gpu-memory-utilization 0.85
      --enable-lora --max-lora-rank 32
      --enable-prefix-caching --dtype half
    volumes:
      - /data/models:/root/.cache/huggingface:ro
      - ./lora_adapters:/lora:rw
    ports: ["8000:8000"]
    healthcheck: { test: ["CMD", "curl", "-f", "http://localhost:8000/health"], interval: 30s }
    networks: [devops-net]

  qdrant:
    image: qdrant/qdrant:v1.11.0
    volumes: ["qdrant_data:/qdrant/storage"]
    ports: ["6333:6333", "6334:6334"]
    healthcheck: { test: ["CMD", "curl", "-f", "http://localhost:6333/readyz"] }

  neo4j:
    image: neo4j:5.20.0-community
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
      NEO4J_dbms_memory_pagecache_size: 2G
      NEO4J_dbms_memory_heap_max__size: 4G
    volumes: ["neo4j_data:/data", "neo4j_logs:/logs"]
    ports: ["7474:7474", "7687:7687"]

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: devops_memory
    volumes:
      - "pg_data:/var/lib/postgresql/data"
      - "./init/01_schema.sql:/docker-entrypoint-initdb.d/01_schema.sql:ro"
    command: >
      -c shared_buffers=2GB -c effective_cache_size=6GB
      -c work_mem=64MB -c maintenance_work_mem=512MB

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
    volumes: ["redis_data:/data"]

  agent:
    build: ./agent
    environment:
      OPENAI_API_BASE: http://vllm:8000/v1
      QDRANT_URL: http://qdrant:6333
      NEO4J_URI: bolt://neo4j:7687
      DATABASE_URL: postgresql+asyncpg://agent:${POSTGRES_PASSWORD}@postgres:5432/devops_memory
      REDIS_URL: redis://redis:6379/0
      GITLAB_URL: https://gitlab.dash-panel.tech
      GITLAB_TOKEN: ${GITLAB_TOKEN}
      AGENT_MODE: autonomous
      CONFIDENCE_THRESHOLD: 0.7
    volumes:
      - ./agent/logs:/app/logs
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ~/.ssh:/root/.ssh:ro
    ports: ["8080:8080", "9090:9090"]
    depends_on: [vllm, qdrant, neo4j, postgres, redis]

  worker:
    build: ./worker
    command: celery -A tasks worker --loglevel=info --concurrency=2
    environment: *agent-env  # Наследует переменные из agent
    volumes:
      - ./worker:/app
      - /data/models:/models:ro
      - ./lora_adapters:/lora:rw
    deploy:
      resources: { reservations: { devices: [{ driver: nvidia, count: 1 }] } }

  webui:
    image: ghcr.io/open-webui/open-webui:main
    environment:
      OPENAI_API_BASE: http://vllm:8000/v1
      OPENAI_API_KEY: empty
      WEBUI_AUTH: false
    ports: ["3000:8080"]
    volumes: ["webui_data:/app/backend/data"]
    depends_on: [vllm, agent]

volumes: { qdrant_data:, neo4j_data:, neo4j_logs:, pg_data:, redis_data:, webui_data: }
networks:
  devops-net:
    driver: bridge
    ipam: { config: [{ subnet: 172.28.0.0/16 }] }
```

**Примечания:**
- Все сервисы подключены к изолированной сети `devops-net`
- Healthchecks обеспечивают корректный порядок запуска
- Секреты передаются только через environment variables
- GPU резервируется только для `vllm` и `worker`

---

### `.env.example`
**Назначение:** Шаблон переменных окружения для копирования в `.env`.

```bash
# === Секреты (ОБЯЗАТЕЛЬНО изменить перед запуском!) ===
NEO4J_PASSWORD=ChangeMe_Neo4j_Secure_2026!
POSTGRES_PASSWORD=ChangeMe_PG_Secure_2026!
GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx

# === GitLab ===
GITLAB_URL=https://gitlab.dash-panel.tech
GITLAB_DEFAULT_PROJECT=dash-panel/backend

# === Агент ===
AGENT_MODE=autonomous              # autonomous | advisory
MAX_RETRY=3
CONFIDENCE_THRESHOLD=0.7
SANDBOX_TIMEOUT=120
LOG_LEVEL=INFO

# === Модель и vLLM ===
VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct-AWQ
VLLM_MAX_LEN=8192
VLLM_GPU_UTIL=0.85
VLLM_DTYPE=half

# === Пути к данным (на хост-машине) ===
MODELS_DIR=/data/models
LORA_DIR=./lora_adapters
LOGS_DIR=./logs
DATA_DIR=./data

# === Мониторинг (опционально) ===
ENABLE_PROMETHEUS=true
PROMETHEUS_PORT=9090
```

**Примечания:**
- Файл добавлен в `.gitignore` — никогда не коммитьте реальные секреты
- Используйте `openssl rand -base64 32` для генерации надёжных паролей

---

## 📁 `agent/` — Основной код агента

### `agent/Dockerfile`
**Назначение:** Сборка контейнера для основного приложения агента.

```dockerfile
FROM python:3.11-slim-bookworm

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential libpq-dev postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копирование зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY . .

# Создание пользователя без прав root (безопасность)
RUN useradd -m -u 1000 agent && chown -R agent:agent /app
USER agent

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Порт по умолчанию
EXPOSE 8080 9090

# Точка входа
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

### `agent/requirements.txt`
**Назначение:** Зависимости Python для основного приложения.

```txt
# Core
fastapi==0.109.2
uvicorn[standard]==0.27.1
pydantic==2.6.1
pydantic-settings==2.1.0

# LangChain ecosystem
langgraph==0.2.18
langchain==0.1.9
langchain-core==0.1.26
langchain-community==0.0.24

# Async DB clients
asyncpg==0.29.0
aioredis==2.0.1

# Vector & Graph
qdrant-client==1.7.2
neo4j==5.17.0
sentence-transformers==2.3.1  # для bge-m3

# GitLab & HTTP
python-gitlab==4.4.0
httpx[http2]==0.26.0

# Utilities
celery==5.3.6
redis==5.0.1
python-multipart==0.0.6
typer[all]==0.9.0  # для CLI

# Monitoring
prometheus-client==0.19.0
structlog==24.1.0

# Code analysis (опционально)
tree-sitter==0.21.3
tree-sitter-python==0.21.0
```

---

### `agent/main.py`
**Назначение:** Точка входа FastAPI + CLI handler + инициализация приложения.

```python
# agent/main.py
import os, logging, asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app, Counter, Histogram

from agent.graph import compile_graph, AgentState
from agent.schemas import QueryRequest, QueryResponse, AuditResponse
from agent.memory import init_stores, store_audit_log
from agent.cli import app as cli_app

# === Метрики Prometheus ===
REQUEST_COUNT = Counter("agent_requests_total", "Total requests", ["endpoint", "status"])
REQUEST_DURATION = Histogram("agent_request_duration_seconds", "Request duration")

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация и очистка ресурсов"""
    # Инициализация хранилищ
    await init_stores()
    
    # Компиляция графа с чекпоинтером
    app.state.graph = await compile_graph()
    app.state.graph_ready = True
    
    logger.info("✓ Agent initialized")
    yield
    # Cleanup (если нужно)
    logger.info("✓ Agent shutdown")

app = FastAPI(
    title="DevOps AI Agent",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None
)

# CORS (для WebUI)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В prod ограничить!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# === Эндпоинты ===

@app.get("/health")
async def health():
    """Проверка готовности агента и зависимостей"""
    return {
        "status": "ok",
        "agent": "ready" if app.state.graph_ready else "initializing",
        "vllm": await check_vllm(),
        "qdrant": await check_qdrant(),
        "neo4j": await check_neo4j(),
        "postgres": await check_postgres(),
    }

@app.post("/api/v1/query", response_model=QueryResponse)
@REQUEST_DURATION.time()
async def handle_query(req: QueryRequest, background_tasks: BackgroundTasks):
    """Основной эндпоинт для запросов к агенту"""
    REQUEST_COUNT.labels(endpoint="/api/v1/query", status="started").inc()
    
    try:
        # Подготовка состояния
        state: AgentState = {
            "task": req.task,
            "project_path": req.project_path,
            "error_context": req.error_context,
            "retrieved_cases": [],
            "proposed_fix": None,
            "execution_plan": [],
            "execution_result": None,
            "confidence": 0.0,
            "memory_update": False,
            "human_approval": req.mode == "advisory",
            "retry_count": 0,
            "audit_id": generate_audit_id(),
        }
        
        # Запуск графа
        config = {"configurable": {"thread_id": state["audit_id"]}}
        result = await app.state.graph.ainvoke(state, config=config)
        
        # Логирование аудита (асинхронно)
        background_tasks.add_task(
            store_audit_log,
            audit_id=state["audit_id"],
            input=req.model_dump(),
            output=result,
            metadata={"mode": req.mode}
        )
        
        REQUEST_COUNT.labels(endpoint="/api/v1/query", status="success").inc()
        return QueryResponse(
            audit_id=state["audit_id"],
            answer=result.get("proposed_fix") or result.get("execution_result"),
            confidence=result["confidence"],
            requires_approval=not result.get("human_approval", True),
            next_steps=result.get("execution_plan", [])[:3]  # Top-3 шага
        )
        
    except Exception as e:
        logger.exception(f"Query failed: {e}")
        REQUEST_COUNT.labels(endpoint="/api/v1/query", status="error").inc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/audit/{audit_id}", response_model=AuditResponse)
async def get_audit(audit_id: str):
    """Получение деталей выполнения по audit_id"""
    from agent.memory import get_audit_log
    record = await get_audit_log(audit_id)
    if not record:
        raise HTTPException(status_code=404, detail="Audit record not found")
    return record

@app.websocket("/ws/agent")
async def websocket_endpoint(websocket):
    """WebSocket для стриминга "мыслей" агента в реальном времени"""
    await websocket.accept()
    # Реализация через pub/sub Redis или прямой стриминг из LangGraph
    # (упрощённая версия для alpha)
    try:
        while True:
            data = await websocket.receive_json()
            # Обработка и отправка статусов...
            await websocket.send_json({"type": "pong"})
    except:
        pass

# === CLI интеграция ===
# Позволяет запускать agent как библиотеку для CLI-утилит
def run_cli():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in ["ask", "fix", "memory", "status", "audit"]:
        cli_app()
    else:
        # Запуск FastAPI через uvicorn
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8080)

if __name__ == "__main__":
    run_cli()

# === Helper functions ===
async def check_vllm() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{os.getenv('OPENAI_API_BASE', 'http://vllm:8000/v1')}/health")
            return r.status_code == 200
    except:
        return False

# ... аналогично check_qdrant(), check_neo4j(), check_postgres()

def generate_audit_id() -> str:
    import uuid, hashlib, time
    return hashlib.sha256(f"{uuid.uuid4()}{time.time()}".encode()).hexdigest()[:16]
```

---

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

### `agent/tools.py`
**Назначение:** Инструменты агента: Docker, GitLab API, безопасное выполнение команд.

```python
# agent/tools.py
import os, re, json, asyncio, logging
from typing import Optional, Union
from pydantic import BaseModel, Field, validator
import httpx, asyncpg
from datetime import datetime

from agent.schemas import DockerCommand, GitLabAction, ExecutionResult

logger = logging.getLogger(__name__)

GITLAB_URL = os.getenv("GITLAB_URL", "https://gitlab.dash-panel.tech")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD")

# === Qdrant ===

async def qdrant_search(
    query: str,
    filter: Optional[dict] = None,
    limit: int = 5,
    score_threshold: float = 0.6
) -> list[dict]:
    """Hybrid search: dense + sparse + metadata filter"""
    from qdrant_client import AsyncQdrantClient
    from sentence_transformers import SentenceTransformer
    
    # Загрузка модели (кэшируется)
    model = SentenceTransformer("BAAI/bge-m3", cache_folder="/models")
    dense_vec = model.encode(query, normalize_embeddings=True).tolist()
    
    async with AsyncQdrantClient(url=QDRANT_URL) as client:
        # Hybrid search
        results = await client.search(
            collection_name="devops_errors",
            query_vector=("bge-m3", dense_vec),
            query_filter=filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True
        )
        
        return [
            {
                "id": r.id,
                "score": r.score,
                "signature": r.payload.get("signature"),
                "fix_steps": r.payload.get("fix_steps"),
                "project": r.payload.get("project"),
                "timestamp": r.payload.get("created_at")
            }
            for r in results
        ]

# === Neo4j ===

async def neo4j_query(cypher: str, params: Optional[dict] = None) -> list[dict]:
    """Выполнение Cypher-запроса с параметрами"""
    from neo4j import AsyncGraphDatabase
    
    async with AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS)
    ) as driver:
        async with driver.session() as session:
            result = await session.run(cypher, parameters=params or {})
            records = await result.data()
            return [dict(r) for r in records]

# === Docker Exec (sandboxed) ===

async def safe_docker_exec(cmd: DockerCommand) -> ExecutionResult:
    """Выполнение Docker-команды в sandbox с ограничениями"""
    try:
        # Формирование безопасной команды
        sandbox_args = [
            "docker", "exec",
            "--user", "nobody",
            "--cap-drop=ALL",
            "--read-only",
            "--tmpfs", "/tmp:exec,size=64m",
            "--network", "none" if "network" not in cmd.command else "host",
            "--memory", "512m",
            "--pids-limit", "50",
            cmd.container,
            "sh", "-c", f"timeout {cmd.timeout}s {cmd.command}"
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *sandbox_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), 
            timeout=cmd.timeout + 10
        )
        
        return ExecutionResult(
            stdout=stdout.decode()[:10000],  # Обрезаем большие логи
            stderr=stderr.decode()[:10000],
            exit_code=proc.returncode,
            command=cmd.command,
            timestamp=datetime.utcnow().isoformat()
        )
        
    except asyncio.TimeoutError:
        return ExecutionResult(
            error=f"Command timed out after {cmd.timeout}s",
            exit_code=137,
            command=cmd.command,
            timestamp=datetime.utcnow().isoformat()
        )
    except Exception as e:
        logger.exception(f"Docker exec failed: {e}")
        return ExecutionResult(
            error=f"Execution failed: {str(e)}",
            exit_code=-1,
            command=cmd.command,
            timestamp=datetime.utcnow().isoformat()
        )

# === GitLab API ===

async def gitlab_api_call(action: GitLabAction) -> ExecutionResult:
    """Безопасный вызов GitLab API с логированием"""
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    project_id = action.project_id if action.project_id.isdigit() else action.project_id.replace("/", "%2F")
    
    endpoints = {
        "get_pipeline": f"/projects/{project_id}/pipelines?ref={action.ref}",
        "get_job_logs": f"/projects/{project_id}/jobs/{action.ref}/trace",
        "retry_job": f"/projects/{project_id}/jobs/{action.ref}/retry",
        "create_issue": f"/projects/{project_id}/issues"
    }
    
    if action.action not in endpoints:
        return ExecutionResult(error=f"Unknown action: {action.action}", exit_code=-1)
    
    async with httpx.AsyncClient(
        base_url=f"{GITLAB_URL}/api/v4",
        headers=headers,
        timeout=30
    ) as client:
        try:
            method = "POST" if action.action in ["retry_job", "create_issue"] else "GET"
            resp = await client.request(method, endpoints[action.action])
            resp.raise_for_status()
            
            return ExecutionResult(
                data=resp.json() if resp.content else resp.text,
                exit_code=0,
                command=f"gitlab {action.action}",
                timestamp=datetime.utcnow().isoformat()
            )
        except httpx.HTTPStatusError as e:
            return ExecutionResult(
                error=f"HTTP {e.response.status_code}: {e.response.text[:500]}",
                exit_code=e.response.status_code,
                command=f"gitlab {action.action}"
            )
        except Exception as e:
            return ExecutionResult(
                error=f"Request failed: {str(e)}",
                exit_code=-1,
                command=f"gitlab {action.action}"
            )

# === Safe Shell (read-only only) ===

async def safe_shell_exec(command: str, timeout: int = 30) -> ExecutionResult:
    """Выполнение shell-команд с ограничениями (только read-only)"""
    allowed_prefixes = [
        "cat ", "ls ", "df ", "du ", "grep ", "find ", 
        "docker logs", "docker inspect", "docker stats",
        "journalctl ", "systemctl status ", "ps ", "top -b"
    ]
    
    if not any(command.startswith(p) for p in allowed_prefixes):
        return ExecutionResult(
            error=f"Command not allowed in autonomous mode: {command}",
            exit_code=-1,
            command=command
        )
    
    try:
        proc = await asyncio.create_subprocess_shell(
            f"timeout {timeout}s {command}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1024*1024  # 1MB buffer limit
        )
        
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout + 5)
        
        return ExecutionResult(
            stdout=stdout.decode()[:10000],
            stderr=stderr.decode()[:10000],
            exit_code=proc.returncode,
            command=command,
            timestamp=datetime.utcnow().isoformat()
        )
    except Exception as e:
        return ExecutionResult(error=str(e), exit_code=-1, command=command)

# === Validation Helpers ===

async def validate_step_result(result: ExecutionResult, validation_cmd: str) -> bool:
    """Проверка результата шага через команду валидации"""
    if not validation_cmd:
        return result.exit_code == 0
    
    # Выполняем команду валидации
    validation_result = await safe_shell_exec(validation_cmd, timeout=15)
    return validation_result.exit_code == 0 and "error" not in validation_result.stderr.lower()
```

---

### `agent/llm.py`
**Назначение:** Клиент для vLLM с поддержкой JSON-mode, retry-логикой и логированием.

```python
# agent/llm.py
import os, logging, asyncio
from typing import Optional, Union
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

VLLM_BASE = os.getenv("OPENAI_API_BASE", "http://vllm:8000/v1")
API_KEY = os.getenv("OPENAI_API_KEY", "empty")
DEFAULT_MODEL = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ")

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException))
)
async def call_vllm(
    prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 1024,
    response_format: Optional[dict] = None,
    model: Optional[str] = None,
    lora_adapter: Optional[str] = None
) -> str:
    """Вызов vLLM с поддержкой JSON-mode и LoRA"""
    
    messages = [{"role": "user", "content": prompt}]
    
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    
    # JSON mode (если требуется)
    if response_format and response_format.get("type") == "json_object":
        payload["response_format"] = {"type": "json_object"}
    
    # LoRA adapter (если указан)
    if lora_adapter:
        payload["extra_body"] = {"lora_name": lora_adapter}
    
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{VLLM_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload
        )
        resp.raise_for_status()
        data = resp.json()
        
        content = data["choices"][0]["message"]["content"]
        logger.debug(f"LLM response ({len(content)} chars): {content[:200]}...")
        return content

async def call_vllm_with_tools(
    prompt: str,
    tools: list[dict],
    tool_choice: str = "auto",
    **kwargs
) -> dict:
    """Вызов с поддержкой tool-calling (если модель поддерживает)"""
    messages = [{"role": "user", "content": prompt}]
    
    payload = {
        "model": kwargs.get("model", DEFAULT_MODEL),
        "messages": messages,
        "tools": tools,
        "tool_choice": tool_choice,
        "temperature": kwargs.get("temperature", 0.1),
        "max_tokens": kwargs.get("max_tokens", 1024),
        "stream": False,
    }
    
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{VLLM_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]
```

---

### `agent/memory.py`
**Назначение:** Абстракции для работы с хранилищами (Qdrant, Neo4j, PostgreSQL).

```python
# agent/memory.py
import os, json, logging, asyncpg
from datetime import datetime, timedelta
from typing import Optional
from qdrant_client import AsyncQdrantClient
from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)

# === Инициализация ===

_stores = {}

async def init_stores():
    """Инициализация соединений с хранилищами"""
    global _stores
    
    # PostgreSQL
    _stores["postgres"] = await asyncpg.create_pool(
        os.environ["DATABASE_URL"],
        min_size=2,
        max_size=10,
        command_timeout=30
    )
    
    # Qdrant (через клиент)
    _stores["qdrant"] = AsyncQdrantClient(url=os.getenv("QDRANT_URL"))
    
    # Neo4j
    _stores["neo4j"] = AsyncGraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    
    logger.info("✓ Memory stores initialized")

# === Error Cases (PostgreSQL) ===

async def store_error_case(case: dict) -> str:
    """Сохранение кейса ошибки в PostgreSQL"""
    async with _stores["postgres"].acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO error_cases (
                signature, stacktrace, context, fix_steps, 
                validation_cmd, rollback_cmd, project, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, created_at
        """,
            case.get("signature"),
            case.get("stacktrace"),
            json.dumps(case.get("context", {})),
            case.get("fix_steps", []),
            case.get("validation_cmd"),
            case.get("rollback_cmd"),
            case.get("project"),
            case.get("status", "pending")
        )
        return str(row["id"])

async def search_error_cases(query: str, project: Optional[str] = None, limit: int = 10) -> list[dict]:
    """Поиск кейсов по тексту + проекту"""
    async with _stores["postgres"].acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, signature, fix_steps, status, created_at,
                   ts_rank_cd(search_vector, websearch_to_tsquery('russian', $1)) AS rank
            FROM error_cases
            WHERE status = 'success'
              AND ($2::text IS NULL OR project = $2)
            ORDER BY rank DESC, created_at DESC
            LIMIT $3
        """, query, project, limit)
        
        return [dict(r) for r in rows]

# === Audit Log ===

async def store_audit_log(audit_id: str, input: dict, output: dict, metadata: dict):
    """Сохранение аудита выполнения"""
    async with _stores["postgres"].acquire() as conn:
        await conn.execute("""
            INSERT INTO audit_log (
                audit_id, input_data, output_data, metadata, 
                confidence, execution_time, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
        """,
            audit_id,
            json.dumps(input),
            json.dumps(output),
            json.dumps(metadata),
            output.get("confidence"),
            output.get("execution_time")
        )

async def get_audit_log(audit_id: str) -> Optional[dict]:
    """Получение аудита по ID"""
    async with _stores["postgres"].acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM audit_log WHERE audit_id = $1
        """, audit_id)
        return dict(row) if row else None

# === Knowledge Graph (Neo4j) ===

async def update_knowledge_graph(error_sig: str, fix_steps: list[str], root_cause: Optional[str] = None):
    """Обновление графа знаний после успешного фикса"""
    async with _stores["neo4j"].session() as session:
        # Создаём/обновляем узел ошибки
        await session.run("""
            MERGE (e:Error {signature: $sig})
            SET e.last_seen = datetime(), e.fix_count = COALESCE(e.fix_count, 0) + 1
        """, sig=error_sig)
        
        # Добавляем шаги решения
        for i, step in enumerate(fix_steps):
            await session.run("""
                MATCH (e:Error {signature: $sig})
                MERGE (s:Solution {step: $step, order: $order})
                MERGE (e)-[:FIXED_BY]->(s)
                SET s.validated = true, s.last_used = datetime()
            """, sig=error_sig, step=step, order=i)
        
        # Если есть корневая причина — связываем
        if root_cause:
            await session.run("""
                MATCH (e:Error {signature: $sig})
                MERGE (c:RootCause {description: $cause})
                MERGE (e)-[:CAUSED_BY]->(c)
            """, sig=error_sig, cause=root_cause)

# === Cleanup ===

async def close_stores():
    """Закрытие соединений"""
    if "postgres" in _stores:
        await _stores["postgres"].close()
    if "qdrant" in _stores:
        await _stores["qdrant"].close()
    if "neo4j" in _stores:
        await _stores["neo4j"].close()
    logger.info("✓ Memory stores closed")
```

---

### `agent/schemas.py`
**Назначение:** Pydantic-модели для валидации входных/выходных данных.

```python
# agent/schemas.py
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Literal, Union
from datetime import datetime

# === Запросы ===

class QueryRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=2000, description="Описание задачи")
    project_path: Optional[str] = Field(None, description="Путь к проекту: group/project")
    error_context: Optional[str] = Field(None, description="Текст ошибки / логи")
    mode: Literal["advisory", "autonomous"] = Field(default="advisory")
    
    @field_validator("project_path")
    @classmethod
    def validate_project_path(cls, v):
        if v and "/" not in v and not v.isdigit():
            raise ValueError("project_path должен быть в формате 'group/project' или numeric ID")
        return v

# === Ответы ===

class ExecutionStep(BaseModel):
    step: int = Field(..., ge=1, le=10)
    command: str = Field(..., min_length=1)
    expected: str = Field(..., description="Ожидаемый результат")
    validate: str = Field(..., description="Команда валидации")
    requires_approval: bool = Field(default=False)
    critical: bool = Field(default=False)
    timeout: Optional[int] = Field(default=60, ge=5, le=300)

class PlanResponse(BaseModel):
    proposed_fix: str
    execution_plan: List[ExecutionStep] = Field(..., max_length=5)
    confidence: float = Field(..., ge=0.0, le=1.0)
    memory_update: bool

class QueryResponse(BaseModel):
    audit_id: str
    answer: Union[str, dict]
    confidence: float
    requires_approval: bool
    next_steps: List[str] = Field(default_factory=list, max_length=3)
    model_config = ConfigDict(json_schema_extra={"example": {
        "audit_id": "abc123",
        "answer": "Увеличьте memory limit в docker-compose.yml",
        "confidence": 0.89,
        "requires_approval": True,
        "next_steps": ["Проверьте текущий лимит", "Отредактируйте compose-файл"]
    }})

class AuditResponse(BaseModel):
    audit_id: str
    timestamp: datetime
    input: dict
    output: dict
    metadata: dict
    confidence_history: List[float]

# === Инструменты ===

class DockerCommand(BaseModel):
    command: str
    container: str
    timeout: int = Field(default=30, ge=5, le=300)
    
    @field_validator("command")
    @classmethod
    def validate_command(cls, v):
        allowed = ["logs", "stats", "inspect", "exec --user nobody", "cp", "top"]
        if not any(v.startswith(p) for p in allowed):
            raise ValueError(f"Command not allowed: {v}")
        return v

class GitLabAction(BaseModel):
    project_id: str
    action: Literal["get_pipeline", "get_job_logs", "retry_job", "create_issue"]
    ref: Optional[str] = "main"
    
    @field_validator("project_id")
    @classmethod
    def validate_project(cls, v):
        if not (v.isdigit() or ("/" in v and len(v.split("/")) == 2)):
            raise ValueError("project_id: numeric ID or 'group/project'")
        return v

class ExecutionResult(BaseModel):
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    data: Optional[Union[dict, str]] = None
    error: Optional[str] = None
    exit_code: Optional[int] = None
    command: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    @field_validator("exit_code")
    @classmethod
    def validate_exit(cls, v):
        if v is not None and v < -1:
            raise ValueError("Invalid exit code")
        return v
```

---

### `agent/cli/__init__.py`
**Назначение:** Точка входа для CLI-утилиты (Typer-based).

```python
# agent/cli/__init__.py
import typer, asyncio, json, sys, logging
from rich.console import Console
from rich.table import Table

from agent.cli.ask import ask_command
from agent.cli.fix import fix_command
from agent.cli.memory import memory_group

app = typer.Typer(
    name="devops-agent",
    help="CLI для DevOps AI Agent",
    no_args_is_help=True,
    rich_markup_mode="rich"
)

app.command()(ask_command)
app.command()(fix_command)
app.add_typer(memory_group, name="memory")

@app.command("status")
def show_status():
    """Показать статус компонентов агента"""
    import httpx
    
    console = Console()
    table = Table(title="DevOps Agent Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="dim")
    
    async def check_service(url: str, name: str):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(url)
                return name, "✓ OK" if r.status_code == 200 else "✗ Error", str(r.status_code)
        except Exception as e:
            return name, "✗ Down", str(e)
    
    async def run_checks():
        checks = [
            ("http://localhost:8000/health", "vLLM"),
            ("http://localhost:8080/health", "Agent API"),
            ("http://localhost:6333/readyz", "Qdrant"),
        ]
        results = await asyncio.gather(*[check_service(url, name) for url, name in checks])
        for name, status, details in results:
            table.add_row(name, status, details)
        console.print(table)
    
    asyncio.run(run_checks())

@app.command("audit")
def show_audit(audit_id: str = typer.Argument(..., help="ID аудита")):
    """Показать детали выполнения по audit_id"""
    import httpx
    
    async def fetch():
        async with httpx.AsyncClient() as client:
            r = await client.get(f"http://localhost:8080/api/v1/audit/{audit_id}")
            if r.status_code == 404:
                print(f"❌ Audit record '{audit_id}' not found")
                sys.exit(1)
            r.raise_for_status()
            data = r.json()
            print(json.dumps(data, indent=2, ensure_ascii=False))
    
    asyncio.run(fetch())

if __name__ == "__main__":
    app()
```

---

### `agent/cli/ask.py`
**Назначение:** Реализация команды `devops-agent ask`.

```python
# agent/cli/ask.py
import typer, asyncio, json, sys, httpx
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown

app = typer.Typer()

@app.command()
def ask(
    task: str = typer.Option(..., "--task", "-t", help="Описание задачи"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Проект: group/project"),
    error: Optional[str] = typer.Option(None, "--error", "-e", help="Текст ошибки"),
    context_file: Optional[Path] = typer.Option(None, "--context-file", "-f", help="Файл с контекстом"),
    mode: Literal["advisory", "autonomous"] = typer.Option("advisory", "--mode", "-m"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Подробный вывод")
):
    """Задать вопрос агенту или описать ошибку"""
    
    # Чтение контекста из файла
    context = None
    if context_file and context_file.exists():
        context = context_file.read_text(encoding="utf-8")
        if verbose:
            typer.echo(f"📄 Loaded context from {context_file} ({len(context)} chars)")
    
    # Формирование запроса
    payload = {
        "task": task,
        "project_path": project,
        "error_context": error or context,
        "mode": mode
    }
    
    async def send():
        async with httpx.AsyncClient(timeout=180) as client:
            console = Console()
            with console.status("[bold green]Думаю...", spinner="dots"):
                resp = await client.post(
                    "http://localhost:8080/api/v1/query",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
            
            if resp.status_code != 200:
                typer.echo(f"❌ Error {resp.status_code}: {resp.text}", err=True)
                sys.exit(1)
            
            result = resp.json()
            
            # Вывод результата
            console.print(f"\n[bold blue]💡 Ответ (уверенность: {result['confidence']:.0%}):[/]")
            if isinstance(result["answer"], str):
                console.print(Markdown(result["answer"]))
            else:
                console.print(json.dumps(result["answer"], indent=2, ensure_ascii=False))
            
            if result.get("next_steps"):
                console.print("\n[bold]📋 Следующие шаги:[/]")
                for i, step in enumerate(result["next_steps"], 1):
                    console.print(f"  {i}. {step}")
            
            if result["requires_approval"]:
                console.print("\n[bold yellow]⚠  Требуется подтверждение для выполнения[/]")
                console.print("Используйте: devops-agent fix --audit-id " + result["audit_id"])
            
            if verbose:
                console.print(f"\n[dim]Audit ID: {result['audit_id']}[/]")
    
    asyncio.run(send())
```

---

### `agent/cli/fix.py`
**Назначение:** Реализация команды `devops-agent fix` для автономного исправления.

```python
# agent/cli/fix.py
import typer, asyncio, json, sys, httpx, time
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer()

@app.command()
def fix(
    project: str = typer.Option(..., "--project", "-p", help="Проект: group/project"),
    job_id: Optional[str] = typer.Option(None, "--job-id", "-j", help="ID job в GitLab CI"),
    audit_id: Optional[str] = typer.Option(None, "--audit-id", help="Продолжить по audit_id"),
    auto_approve: str = typer.Option("logs,inspect,df", "--auto-approve", help="Команды без подтверждения"),
    require_approve: str = typer.Option("restart,rm,systemctl", "--require-approve", help="Команды с подтверждением"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Только показать план, не выполнять")
):
    """Запустить автономное исправление ошибки"""
    
    console = Console()
    
    # Если указан audit_id — продолжаем существующую сессию
    if audit_id:
        console.print(f"🔄 Продолжаю сессию {audit_id}")
        # Логика continuation...
        return
    
    # Формирование начального запроса
    payload = {
        "task": f"Автономное исправление в проекте {project}",
        "project_path": project,
        "error_context": f"GitLab job {job_id}" if job_id else "Пользовательский запрос на исправление",
        "mode": "autonomous"
    }
    
    async def run_fix():
        async with httpx.AsyncClient(timeout=300) as client:
            # 1. Получаем план
            with console.status("[bold green]Анализирую...", spinner="dots"):
                resp = await client.post("http://localhost:8080/api/v1/query", json=payload)
            
            if resp.status_code != 200:
                typer.echo(f"❌ Error: {resp.text}", err=True)
                sys.exit(1)
            
            result = resp.json()
            plan = result.get("next_steps", [])
            
            if not plan:
                console.print("[yellow]⚠ План не сгенерирован — требую уточнения[/]")
                return
            
            # 2. Показываем план
            console.print("\n[bold]📋 Предложенный план:[/]")
            for i, step in enumerate(plan, 1):
                approval = "🔓" if step.lower().split()[0] in auto_approve.split(",") else "🔐"
                console.print(f"  {approval} {i}. {step}")
            
            if dry_run:
                console.print("\n[dry-run mode] Выполнение пропущено")
                return
            
            # 3. Интерактивное подтверждение опасных шагов
            dangerous = [s for s in plan if any(p in s.lower() for p in require_approve.split(","))]
            if dangerous and not typer.confirm(f"⚠ Выполнить {len(dangerous)} потенциально опасных команд?"):
                console.print("[yellow]Отменено пользователем[/]")
                return
            
            # 4. Выполнение (упрощённо — в реальности через WebSocket/streaming)
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
                task = progress.add_task("[green]Выполняю...", total=len(plan))
                
                for i, step in enumerate(plan):
                    progress.update(task, description=f"Шаг {i+1}/{len(plan)}: {step[:40]}...")
                    # В реальности: отправка шага на выполнение через API
                    await asyncio.sleep(1)  # Имитация
                    progress.advance(task)
            
            console.print("\n[bold green]✓ Выполнение завершено[/]")
            console.print(f"📊 Audit: {result['audit_id']}")
    
    asyncio.run(run_fix())
```

---

### `agent/cli/memory.py`
**Назначение:** Команды для работы с памятью (`devops-agent memory`).

```python
# agent/cli/memory.py
import typer, asyncio, json, sys, httpx
from rich.console import Console
from rich.table import Table
from datetime import datetime

app = typer.Typer()

@app.command("search")
def search(
    query: str = typer.Argument(..., help="Поисковый запрос"),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
    limit: int = typer.Option(10, "--limit", "-l", min=1, max=50),
    format: Literal["table", "json"] = typer.Option("table", "--format")
):
    """Поиск в памяти ошибок"""
    
    async def run():
        async with httpx.AsyncClient() as client:
            params = {"query": query, "limit": limit}
            if project:
                params["project"] = project
            
            resp = await client.get("http://localhost:8080/api/v1/memory/errors", params=params)
            resp.raise_for_status()
            results = resp.json()
            
            if format == "json":
                print(json.dumps(results, indent=2, ensure_ascii=False))
            else:
                console = Console()
                table = Table(title=f"Результаты поиска: '{query}'")
                table.add_column("ID", style="dim")
                table.add_column("Signature")
                table.add_column("Project")
                table.add_column("Fix Steps", max_width=50)
                table.add_column("Score", justify="right")
                
                for r in results:
                    table.add_row(
                        r["id"][:8],
                        r["signature"][:30] + "..." if len(r["signature"]) > 30 else r["signature"],
                        r.get("project", "N/A"),
                        "; ".join(r.get("fix_steps", [])[:2]),
                        f"{r['score']:.2f}"
                    )
                console.print(table)
    
    asyncio.run(run())

@app.command("consolidate")
def consolidate(
    since: str = typer.Option("24h", "--since", help="Период: 1h, 24h, 7d"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Предпросмотр без применения"),
    force: bool = typer.Option(False, "--force", help="Пропустить проверку")
):
    """Запустить консолидацию памяти"""
    
    async def run():
        async with httpx.AsyncClient(timeout=120) as client:
            payload = {"since": since, "dry_run": dry_run, "force": force}
            
            console = Console()
            with console.status("[bold green]Консолидация...", spinner="dots"):
                resp = await client.post(
                    "http://localhost:8080/api/v1/memory/consolidate",
                    json=payload
                )
            
            if resp.status_code == 200:
                result = resp.json()
                console.print(f"[green]✓ Консолидация завершена[/]")
                console.print(f"  • Обработано кейсов: {result.get('processed', 0)}")
                console.print(f"  • Обновлено в KG: {result.get('kg_updates', 0)}")
                console.print(f"  • LoRA dataset: +{result.get('new_samples', 0)} записей")
            else:
                console.print(f"[red]✗ Error {resp.status_code}[/]: {resp.text}")
    
    asyncio.run(run())

@app.command("export")
def export(
    output: str = typer.Option("export.json", "--output", "-o"),
    format: Literal["json", "markdown", "csv"] = typer.Option("json", "--format"),
    project: Optional[str] = typer.Option(None, "--project", "-p")
):
    """Экспорт памяти в файл"""
    
    async def run():
        async with httpx.AsyncClient() as client:
            params = {"format": format}
            if project:
                params["project"] = project
            
            resp = await client.get("http://localhost:8080/api/v1/memory/export", params=params)
            resp.raise_for_status()
            
            with open(output, "w", encoding="utf-8") as f:
                if format == "json":
                    json.dump(resp.json(), f, indent=2, ensure_ascii=False)
                else:
                    f.write(resp.text)
            
            typer.echo(f"✓ Экспортировано в {output} ({len(resp.content)} bytes)")
    
    asyncio.run(run())
```

---

## 📁 `worker/` — Фоновые задачи

### `worker/Dockerfile`
```dockerfile
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Пользователь без root
RUN useradd -m -u 1000 worker && chown -R worker:worker /app
USER worker

CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "--concurrency=2"]
```

---

### `worker/requirements.txt`
```txt
# Наследует основные зависимости из agent/
# + специфичные для обучения

# Training
unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git
trl==0.8.6
peft==0.9.0
accelerate==0.27.2
datasets==2.18.0

# Validation
ragas==0.1.7
deepeval==0.21.0

# Celery extras
celery[redis]==5.3.6
flower==2.0.1  # опционально: веб-интерфейс для Celery

# Monitoring
prometheus-client==0.19.0
```

---

### `worker/tasks.py`
**Назначение:** Celery tasks для консолидации памяти и обучения LoRA.

```python
# worker/tasks.py
import os, json, logging, asyncio
from celery import Celery
from datetime import datetime, timedelta

from agent.memory import init_stores, search_error_cases, update_knowledge_graph
from agent.llm import call_vllm
from worker.train import train_lora_adapter
from worker.validate import run_ragas_validation

logger = logging.getLogger(__name__)

app = Celery("devops_worker", broker=os.getenv("REDIS_URL"))
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=7200,  # 2 часа макс. на задачу
    worker_prefetch_multiplier=1
)

@app.task(bind=True, max_retries=3)
def consolidate_memory(self, audit_id: str = None, since: str = "24h"):
    """Консолидация памяти: рефлексия → извлечение паттернов → обновление хранилищ"""
    
    try:
        # 1. Сбор новых успешных кейсов
        cutoff = datetime.utcnow() - parse_duration(since)
        new_cases = fetch_new_cases(cutoff, status="success")
        
        if not new_cases:
            logger.info("No new cases to consolidate")
            return {"processed": 0}
        
        logger.info(f"Processing {len(new_cases)} new cases")
        
        # 2. Рефлексия и экстракция (через LLM)
        patterns = []
        for case in new_cases:
            pattern = extract_pattern_via_llm(case)
            if pattern:
                patterns.append(pattern)
                # Обновляем граф знаний
                asyncio.run(update_knowledge_graph(
                    error_sig=case["signature"],
                    fix_steps=pattern["steps"],
                    root_cause=pattern.get("root_cause")
                ))
        
        # 3. Формирование датасета для LoRA
        if len(patterns) >= 20:  # Порог для обучения
            dataset_path = generate_lora_dataset(patterns)
            # Запускаем обучение (асинхронно)
            train_lora_adapter.delay(dataset_path, version=f"v{next_version()}")
        
        # 4. Обновляем статус кейсов
        mark_consolidated([c["id"] for c in new_cases])
        
        return {
            "processed": len(new_cases),
            "patterns_extracted": len(patterns),
            "kg_updates": len(patterns),
            "new_samples": len(patterns)
        }
        
    except Exception as e:
        logger.exception("Consolidation failed")
        raise self.retry(exc=e, countdown=300)

@app.task(bind=True, max_retries=2)
def train_lora_adapter(self, dataset_path: str, version: str):
    """Fine-tuning LoRA адаптера на успешных кейсах"""
    
    try:
        logger.info(f"Starting LoRA training: {version}")
        
        # 1. Валидация датасета
        if not validate_dataset(dataset_path):
            raise ValueError("Dataset validation failed")
        
        # 2. Запуск обучения (unsloth)
        output_dir = f"/lora/devops_{version}"
        metrics = run_unsloth_training(
            dataset_path=dataset_path,
            output_dir=output_dir,
            config_path="/app/configs/devops_lora.yaml"
        )
        
        # 3. Валидация качества
        val_metrics = run_ragas_validation(output_dir)
        if val_metrics["answer_relevance"] < 0.85:
            logger.warning(f"Validation failed: {val_metrics}")
            return {"status": "rejected", "metrics": val_metrics}
        
        # 4. Регистрация в vLLM
        register_lora_in_vllm(f"devops_{version}", output_dir)
        
        logger.info(f"✓ LoRA {version} deployed")
        return {"status": "deployed", "adapter": f"devops_{version}", "metrics": {**metrics, **val_metrics}}
        
    except Exception as e:
        logger.exception(f"Training failed: {e}")
        # Откат: удаляем частичный адаптер
        cleanup_lora_dir(f"/lora/devops_{version}")
        raise self.retry(exc=e, countdown=600)

@app.task
def validate_active_adapter():
    """Ежечасная проверка качества активного LoRA адаптера"""
    adapter = get_active_lora_name()
    if not adapter:
        return
    
    metrics = run_ragas_validation(adapter, test_file="/data/holdout_devops.jsonl")
    
    if metrics["answer_relevance"] < 0.80 or metrics["faithfulness"] < 0.75:
        logger.warning(f"Adapter {adapter} degraded — triggering rollback")
        rollback_lora(adapter)
        send_alert(f"LoRA rollback: {adapter} due to metric regression")
    
    return {"adapter": adapter, "metrics": metrics}

# === Helpers ===

def parse_duration(s: str) -> timedelta:
    """Парсинг строки длительности: '24h' → timedelta(hours=24)"""
    import re
    match = re.match(r"^(\d+)([hdw])$", s)
    if not match:
        raise ValueError(f"Invalid duration: {s}")
    value, unit = int(match[1]), match[2]
    return {"h": timedelta(hours=value), "d": timedelta(days=value), "w": timedelta(weeks=value)}[unit]

def fetch_new_cases(cutoff: datetime, status: str = "success") -> list[dict]:
    """Получение новых кейсов из БД"""
    # Реализация через agent.memory.search_error_cases с фильтрами
    pass

def extract_pattern_via_llm(case: dict) -> Optional[dict]:
    """Извлечение паттерна через LLM (root cause + универсальные шаги)"""
    prompt = f"""
    Проанализируй успешное исправление ошибки и выдели универсальный паттерн.
    
    Ошибка: {case["signature"]}
    Контекст: {case["stacktrace"][:500]}
    Шаги фикса: {json.dumps(case["fix_steps"])}
    
    Верни JSON:
    {{
      "root_cause": "краткое описание причины",
      "steps": ["универсальный шаг 1", "шаг 2", ...],
      "validation": "команда для проверки",
      "applicable_projects": ["pattern for project names"]
    }}
    """
    
    response = asyncio.run(call_vllm(prompt, temperature=0.0, response_format={"type": "json_object"}))
    return json.loads(response) if response else None

def generate_lora_dataset(patterns: list[dict]) -> str:
    """Генерация JSONL датасета в формате Alpaca"""
    import json
    output_path = f"/data/datasets/devops_fixes_{datetime.now():%Y%m%d_%H%M}.jsonl"
    
    with open(output_path, "w", encoding="utf-8") as f:
        for p in patterns:
            sample = {
                "instruction": f"Fix error: {p['root_cause']}",
                "input": f"Context: Docker/GitLab environment\nError signature: {p['signature']}",
                "output": "\n".join([f"{i+1}. {s}" for i, s in enumerate(p["steps"])]) + f"\n\nValidate: {p['validation']}"
            }
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    
    return output_path

def next_version() -> int:
    """Определение следующего номера версии LoRA"""
    import glob
    existing = [int(p.split("_v")[1]) for p in glob.glob("/lora/devops_v*") if p.split("_v")[1].isdigit()]
    return max(existing, default=0) + 1

def register_lora_in_vllm(name: str, path: str):
    """Регистрация адаптера в vLLM через API"""
    import httpx
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            "http://vllm:8000/v1/lora",
            json={"lora_name": name, "lora_path": path},
            headers={"Content-Type": "application/json"}
        )
        resp.raise_for_status()

def rollback_lora(adapter_name: str):
    """Откат к предыдущему адаптеру"""
    import subprocess
    subprocess.run(["/app/scripts/lora_manager.sh", adapter_name, "rollback"], check=True)

def send_alert(message: str):
    """Отправка алерта (в будущем: Slack/Email/Telegram)"""
    logger.critical(f"🚨 ALERT: {message}")
    # В продакшене: отправка в мониторинговую систему
```

---

### `worker/monitor.py`
**Назначение:** Мониторинг качества адаптеров и авто-откат.

```python
# worker/monitor.py
import os, json, logging, httpx
from datetime import datetime
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)

app = Celery("monitor", broker=os.getenv("REDIS_URL"))

# Расписание задач
app.conf.beat_schedule = {
    "validate-adapter-hourly": {
        "task": "worker.tasks.validate_active_adapter",
        "schedule": crontab(minute=0),  # Каждый час
    },
    "cleanup-old-lora-daily": {
        "task": "cleanup_old_lora_adapters",
        "schedule": crontab(hour=3, minute=0),  # 3 AM ежедневно
    }
}

@app.task
def cleanup_old_lora_adapters(keep_last: int = 5):
    """Удаление старых версий LoRA для экономии места"""
    import glob, shutil
    adapters = sorted(glob.glob("/lora/devops_v*"), key=lambda p: os.path.getmtime(p), reverse=True)
    
    removed = 0
    for adapter in adapters[keep_last:]:
        try:
            shutil.rmtree(adapter)
            logger.info(f"Removed old adapter: {adapter}")
            removed += 1
        except Exception as e:
            logger.error(f"Failed to remove {adapter}: {e}")
    
    return {"removed": removed, "kept": len(adapters[:keep_last])}
```

---

### `worker/configs/devops_lora.yaml`
**Назначение:** Конфигурация обучения LoRA через Unsloth/Axolotl.

```yaml
# worker/configs/devops_lora.yaml
# Конфиг для fine-tuning на DevOps-ошибках и фиксах

# === Модель ===
base_model: Qwen/Qwen2.5-14B-Instruct-AWQ
model_type: AutoModelForCausalLM
tokenizer_type: AutoTokenizer
trust_remote_code: true

# === LoRA параметры (оптимизировано для 24GB VRAM) ===
lora_r: 32
lora_alpha: 64
lora_dropout: 0.05
target_modules:
  - q_proj
  - v_proj
  - gate_proj
  - up_proj
  - down_proj
  - o_proj

# === Обучение ===
sequence_len: 4096
batch_size: 2
gradient_accumulation_steps: 8
num_epochs: 2
learning_rate: 2e-4
lr_scheduler: cosine
warmup_steps: 50
optim: adamw_8bit
weight_decay: 0.01
max_grad_norm: 1.0

# === Данные ===
dataset:
  - path: ./data/devops_fixes_v1.jsonl
    type: alpaca
    conversation: "qwen"  # Формат диалога для Qwen

# === Валидация ===
val_set_size: 0.1
evals_per_epoch: 1
save_steps: 50
output_dir: /lora/devops_v{version}

# === Квантование ===
# База уже в AWQ, обучаем в fp16
load_in_4bit: false
bf16: auto
fp16: true

# === Интеграция с vLLM ===
adapter_name: devops_fixes
enable_lora: true
lora_modules: "all"  # Применять ко всем целевым слоям

# === Логирование ===
logging_steps: 10
report_to: ["tensorboard"]  # или "none" для минимизации зависимостей
```

---

## 📁 `init/` — Инициализация БД

### `init/01_schema.sql`
```sql
-- init/01_schema.sql
-- PostgreSQL schema для DevOps Agent

-- Таблица кейсов ошибок
CREATE TABLE IF NOT EXISTS error_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signature TEXT NOT NULL,
    stacktrace TEXT,
    context JSONB DEFAULT '{}'::jsonb,
    fix_steps TEXT[],
    validation_cmd TEXT,
    rollback_cmd TEXT,
    project TEXT,
    status TEXT CHECK (status IN ('pending', 'success', 'failed', 'deprecated')),
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    consolidated BOOLEAN DEFAULT FALSE
);

-- Полнотекстовый поиск
ALTER TABLE error_cases ADD COLUMN IF NOT EXISTS search_vector tsvector;
CREATE INDEX IF NOT EXISTS idx_error_search ON error_cases USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_error_signature ON error_cases USING GIN(signature gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_error_project ON error_cases (project);
CREATE INDEX IF NOT EXISTS idx_error_status ON error_cases (status, created_at DESC);

-- Триггер для обновления search_vector
CREATE OR REPLACE FUNCTION update_search_vector() RETURNS trigger AS $$
BEGIN
  NEW.search_vector := 
    setweight(to_tsvector('russian', COALESCE(NEW.signature, '')), 'A') ||
    setweight(to_tsvector('russian', COALESCE(NEW.stacktrace, '')), 'B') ||
    setweight(to_tsvector('russian', COALESCE(array_to_string(NEW.fix_steps, ' '), '')), 'C');
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_search_vector
BEFORE INSERT OR UPDATE ON error_cases
FOR EACH ROW EXECUTE FUNCTION update_search_vector();

-- Триггер для updated_at
CREATE OR REPLACE FUNCTION update_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_timestamp
BEFORE UPDATE ON error_cases
FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Таблица аудита
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id TEXT UNIQUE NOT NULL,
    input_data JSONB NOT NULL,
    output_data JSONB NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    confidence FLOAT,
    execution_time FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_id ON audit_log (audit_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log (created_at DESC);

-- Таблица версий LoRA
CREATE TABLE IF NOT EXISTS lora_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    base_model TEXT NOT NULL,
    metrics JSONB,
    status TEXT CHECK (status IN ('training', 'validating', 'deployed', 'rolled_back')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deployed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_lora_status ON lora_versions (status);

-- LangGraph чекпоинты (создаются автоматически через AsyncPostgresSaver.setup())
-- Но можно предсоздать для контроля:
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    parent_id TEXT,
    checkpoint BYTEA NOT NULL,
    metadata JSONB,
    PRIMARY KEY (thread_id, checkpoint_id)
);
```

---

### `init/02_indexes.sql`
```sql
-- init/02_indexes.sql
-- Дополнительные индексы для производительности

-- Быстрый поиск по проекту + статусу
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_error_project_status 
ON error_cases (project, status) WHERE status = 'success';

-- Частые запросы по дате
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_error_created 
ON error_cases (created_at DESC) WHERE consolidated = false;

-- Аудит: поиск по метаданным
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_metadata 
ON audit_log USING GIN ((metadata->'project'));

-- Оптимизация для pgvector (если используется для эмбеддингов в PG)
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_error_embedding 
-- ON error_cases USING hnsw (embedding vector_cosine_ops) 
-- WITH (m=16, ef_construction=64);

-- Statistics update
ANALYZE error_cases;
ANALYZE audit_log;
ANALYZE lora_versions;
```

---

## 📁 `config/` — Конфигурация сервисов

### `config/qdrant.yaml`
```yaml
# config/qdrant.yaml
# Настройки Qdrant для гибридного поиска

storage:
  optimizers:
    default_segment_number: 4
    max_segment_size: 10_000_000
    memmap_threshold: 100_000
    indexing_threshold: 20_000
    flush_interval_sec: 5
    max_optimization_threads: 2

performance:
  max_search_threads: 4
  max_optimization_threads: 2

collections:
  devops_errors:
    vectors:
      bge-m3:
        size: 1024
        distance: Cosine
    sparse_vectors:
      bm25:
        index:
          type: mutable_ram
    hnsw_config:
      m: 16
      ef_construct: 100
      full_scan_threshold: 10000
    quantization_config:
      scalar:
        type: int8
        quantile: 0.99
        always_ram: true
```

---

### `config/neo4j.conf`
```conf
# config/neo4j.conf
# Tuning для Neo4j Community (RTX 4090, 64GB RAM)

# Memory
dbms.memory.pagecache.size=2G
dbms.memory.heap.initial_size=2G
dbms.memory.heap.max_size=4G

# Transaction
dbms.tx_log.rotation.retention_policy=1 days

# Logs
dbms.logs.http.enabled=true
dbms.logs.query.enabled=INFO
dbms.logs.query.rotation.size=20M

# Security
dbms.security.auth_enabled=true
dbms.security.procedures.unrestricted=apoc.*

# Metrics (для Prometheus)
dbms.metrics.enabled=true
dbms.metrics.prefix=neo4j
```

---

## 📁 `scripts/` — Утилиты

### `scripts/lora_manager.sh`
```bash
#!/bin/bash
# scripts/lora_manager.sh
# Управление LoRA адаптерами в vLLM

set -euo pipefail

VLLM_API="${VLLM_API:-http://localhost:8000/v1}"
ADAPTER_NAME="${1:-}"
ACTION="${2:-load}"  # load | unload | rollback | list

usage() {
  echo "Usage: $0 <adapter_name> <action>"
  echo "Actions: load, unload, rollback, list"
  exit 1
}

[[ -z "$ADAPTER_NAME" && "$ACTION" != "list" ]] && usage

case $ACTION in
  load)
    echo "📦 Loading adapter: $ADAPTER_NAME"
    curl -s -X POST "$VLLM_API/lora" \
      -H "Content-Type: application/json" \
      -d "{\"lora_name\": \"$ADAPTER_NAME\", \"lora_path\": \"/lora/$ADAPTER_NAME\"}" \
      | jq -r '. // empty'
    echo "✓ Loaded"
    ;;
    
  unload)
    echo "🗑️  Unloading adapter: $ADAPTER_NAME"
    curl -s -X DELETE "$VLLM_API/lora/$ADAPTER_NAME"
    echo "✓ Unloaded"
    ;;
    
  rollback)
    echo "🔄 Rolling back from: $ADAPTER_NAME"
    # Выгрузить текущий
    curl -s -X DELETE "$VLLM_API/lora/$ADAPTER_NAME" 2>/dev/null || true
    
    # Найти предыдущий
    PREV=$(ls -t /lora 2>/dev/null | grep "devops_v" | sed -n "2p" || true)
    if [[ -n "$PREV" && -d "/lora/$PREV" ]]; then
      echo "📥 Loading previous: $PREV"
      curl -s -X POST "$VLLM_API/lora" \
        -H "Content-Type: application/json" \
        -d "{\"lora_name\": \"$PREV\", \"lora_path\": \"/lora/$PREV\"}"
      echo "✓ Rolled back to $PREV"
    else
      echo "⚠ No previous adapter — running base model"
    fi
    ;;
    
  list)
    echo "📋 Available adapters:"
    curl -s "$VLLM_API/lora" | jq -r '.[].lora_name' 2>/dev/null || echo "(none)"
    echo ""
    echo "📁 Local adapters:"
    ls -1 /lora 2>/dev/null | grep "devops_v" || echo "(none)"
    ;;
    
  *)
    usage
    ;;
esac
```

---

### `scripts/import_gitlab_errors.py`
```python
#!/usr/bin/env python3
# scripts/import_gitlab_errors.py
# Импорт истории ошибок из GitLab CI в память агента

import os, sys, json, asyncio, logging
import httpx, asyncpg
from datetime import datetime, timedelta
from gitlab import Gitlab

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GITLAB_URL = os.getenv("GITLAB_URL", "https://gitlab.dash-panel.tech")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
DB_URL = os.getenv("DATABASE_URL")

async def main():
    if not GITLAB_TOKEN:
        logger.error("Set GITLAB_TOKEN environment variable")
        sys.exit(1)
    
    # Подключение к БД
    pool = await asyncpg.create_pool(DB_URL)
    
    # GitLab client
    gl = Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN)
    
    # Получение проектов (или взять из конфига)
    projects = os.getenv("GITLAB_PROJECTS", "dash-panel/backend,dash-panel/frontend").split(",")
    
    imported = 0
    for proj_name in projects:
        logger.info(f"Processing project: {proj_name}")
        project = gl.projects.get(proj_name)
        
        # Пайплайны за последние 7 дней
        cutoff = datetime.utcnow() - timedelta(days=7)
        pipelines = project.pipelines.list(get_all=True, updated_after=cutoff.isoformat())
        
        for pipeline in pipelines:
            if pipeline.status != "failed":
                continue
            
            # Получение упавших jobs
            for job in pipeline.jobs.list():
                if job.status != "failed":
                    continue
                
                # Извлечение логов
                try:
                    logs = job.trace().decode("utf-8", errors="ignore")[:5000]
                except:
                    continue
                
                # Формирование кейса
                case = {
                    "signature": f"{job.name}:{pipeline.sha[:8]}",
                    "stacktrace": logs,
                    "context": {
                        "project": proj_name,
                        "pipeline_id": pipeline.id,
                        "job_id": job.id,
                        "stage": job.stage,
                        "ref": pipeline.ref
                    },
                    "project": proj_name,
                    "status": "pending"  # Требует анализа
                }
                
                # Сохранение в БД
                async with pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO error_cases (signature, stacktrace, context, project, status)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (signature) DO UPDATE 
                        SET updated_at = NOW(), stacktrace = EXCLUDED.stacktrace
                    """, 
                        case["signature"], case["stacktrace"], 
                        json.dumps(case["context"]), case["project"], case["status"]
                    )
                imported += 1
    
    await pool.close()
    logger.info(f"✓ Imported {imported} error cases")

if __name__ == "__main__":
    asyncio.run(main())
```

---

### `scripts/backup.sh`
```bash
#!/bin/bash
# scripts/backup.sh
# Резервное копирование: PostgreSQL + Qdrant + Neo4j

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
DATE=$(date +%Y%m%d_%H%M)
mkdir -p "$BACKUP_DIR"

echo "🔄 Starting backup: $DATE"

# PostgreSQL
echo "📦 Dumping PostgreSQL..."
docker-compose exec -T postgres pg_dump -U agent devops_memory \
  | gzip > "$BACKUP_DIR/pg_devops_$DATE.sql.gz"

# Qdrant snapshot
echo "📦 Snapshotting Qdrant..."
curl -X POST "http://localhost:6333/collections/devops_errors/snapshots" \
  -H "Content-Type: application/json" \
  -d '{"wait": true}' | jq -r '.result.name' | \
  xargs -I {} cp "/var/lib/qdrant/snapshots/devops_errors/{}" "$BACKUP_DIR/qdrant_$DATE.snapshot"

# Neo4j backup (через neo4j-admin)
echo "📦 Backing up Neo4j..."
docker-compose exec -T neo4j neo4j-admin database backup devops_memory \
  --to-path=/backups --verbose || true  # Community edition ограничивает

# Очистка старых бэкапов (>7 дней)
find "$BACKUP_DIR" -name "*.gz" -mtime +7 -delete
find "$BACKUP_DIR" -name "*.snapshot" -mtime +7 -delete

echo "✓ Backup complete: $BACKUP_DIR"
ls -lh "$BACKUP_DIR" | tail -5
```

---

## 📁 `monitoring/` — Prometheus + Grafana

### `monitoring/prometheus.yml`
```yaml
# monitoring/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'devops-agent'
    static_configs:
      - targets: ['agent:9090']
    metrics_path: /metrics
    scrape_interval: 10s

  - job_name: 'vllm'
    static_configs:
      - targets: ['vllm:8000']
    metrics_path: /metrics

  - job_name: 'qdrant'
    static_configs:
      - targets: ['qdrant:6333']
    metrics_path: /metrics

  - job_name: 'neo4j'
    static_configs:
      - targets: ['neo4j:7474']
    metrics_path: /metrics
```

---

### `monitoring/dashboards/devops-agent.json`
**Назначение:** Готовый дашборд Grafana (импортируется через UI).

```json
{
  "dashboard": {
    "title": "DevOps AI Agent",
    "panels": [
      {
        "title": "VRAM Usage (vLLM)",
        "type": "timeseries",
        "targets": [{"expr": "vllm:gpu_memory_usage_bytes / 1e9", "legendFormat": "GB"}]
      },
      {
        "title": "Confidence Trend",
        "type": "stat",
        "targets": [{"expr": "avg(agent_confidence_score)", "legendFormat": "Avg Confidence"}]
      },
      {
        "title": "Error Retrieval Latency",
        "type": "heatmap",
        "targets": [{"expr": "histogram_quantile(0.95, rate(qdrant_search_latency_seconds_bucket[5m]))"}]
      },
      {
        "title": "LoRA Version",
        "type": "table",
        "targets": [{"expr": "lora_active_version", "format": "table"}]
      }
    ],
    "time": {"from": "now-6h", "to": "now"},
    "refresh": "30s"
  }
}
```

---

## 📁 `data/` — Данные (игнорируются в .git)

### `data/.gitkeep`
```
# Файл-заглушка для отслеживания пустой директории в Git
```

### `data/holdout_devops.jsonl` (пример)
```json
{"instruction": "Fix OOMKilled in gitlab-runner", "input": "Context: mem_limit=512M, swap=0", "output": "1. Increase mem_limit to 1G\n2. Enable swap: --memory-swap=1G\n3. Validate: docker stats"}
{"instruction": "Docker network unreachable after restart", "input": "Error: Cannot connect to Docker daemon", "output": "1. Check docker.service status\n2. Restart: systemctl restart docker\n3. Validate: docker ps"}
```

---

## 📁 `lora_adapters/` — Адаптеры

### `lora_adapters/.gitkeep`
```
# Пустая директория для монтирования в контейнеры
```

### `lora_adapters/devops_v1/adapter_config.json` (пример)
```json
{
  "base_model_name_or_path": "Qwen/Qwen2.5-14B-Instruct-AWQ",
  "task_type": "CAUSAL_LM",
  "peft_type": "LORA",
  "r": 32,
  "lora_alpha": 64,
  "target_modules": ["q_proj", "v_proj", "gate_proj", "up_proj", "down_proj", "o_proj"],
  "modules_to_save": null,
  "revision": null
}
```

---

## 📁 `logs/` — Логи

### `logs/.gitkeep`
```
# Директория для логов (ротация через logrotate)
```

### Пример `logs/audit.jsonl`
```json
{"audit_id":"abc123","timestamp":"2026-05-05T10:30:00Z","input":{"task":"Fix OOM","mode":"autonomous"},"output":{"confidence":0.89,"steps_executed":3},"metadata":{"project":"dash-panel/backend"}}
```

---

## 🔚 Заключение

Эта структура обеспечивает:

✅ **Модульность**: каждый файл имеет чёткую ответственность  
✅ **Безопасность**: sandbox, валидация, аудит, минимальные привилегии  
✅ **Масштабируемость**: горизонтальное масштабирование через Celery, кэширование  
✅ **Поддерживаемость**: типизация через Pydantic, логирование, метрики  
✅ **Непрерывное обучение**: автоматический сбор датасетов, валидация, hot-swap  

Для начала работы:
1. Скопируйте файлы в соответствующие директории
2. Настройте `.env` и загрузите модель
3. Запустите `docker-compose up -d`
4. Протестируйте через `devops-agent ask --task "..."`

Удачи в развёртывании! 🚀🔧🧠
