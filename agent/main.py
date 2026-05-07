# agent/main.py
import os, logging, asyncio, uuid, hashlib, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app, Counter, Histogram
import httpx

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
            r = await client.get(f"{os.getenv('LLM_API_BASE', 'http://vllm:8000/v1')}/health")
            return r.status_code == 200
    except:
        return False

async def check_qdrant() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{os.getenv('QDRANT_URL', 'http://qdrant:6333')}/readyz")
            return r.status_code == 200
    except:
        return False

async def check_neo4j() -> bool:
    try:
        from neo4j import GraphDatabase
        uri = os.getenv('NEO4J_URI', 'bolt://neo4j:7687')
        password = os.getenv('NEO4J_PASSWORD', 'password')
        driver = GraphDatabase.driver(uri, auth=("neo4j", password))
        driver.verify_connectivity()
        driver.close()
        return True
    except:
        return False

async def check_postgres() -> bool:
    try:
        import asyncpg
        dsn = os.getenv('DATABASE_URL', 'postgresql://devops:secure_password_change_me@postgres:5432/devops_db')
        # Convert postgresql+asyncpg to postgresql for asyncpg if needed
        dsn = dsn.replace('postgresql+asyncpg://', 'postgresql://')
        conn = await asyncpg.connect(dsn)
        await conn.close()
        return True
    except:
        return False

def generate_audit_id() -> str:
    return hashlib.sha256(f"{uuid.uuid4()}{time.time()}".encode()).hexdigest()[:16]

