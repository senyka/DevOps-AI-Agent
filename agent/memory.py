# agent/memory.py
import os, json, logging, asyncpg
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from contextlib import asynccontextmanager
import hashlib

from agent.utils import managed_qdrant_client, managed_neo4j_driver, managed_postgres_pool

logger = logging.getLogger(__name__)

# === Инициализация ===

_stores = {}

async def init_stores():
    """Инициализация соединений с хранилищами"""
    global _stores

    # PostgreSQL - используем контекстный менеджер при необходимости
    _stores["postgres_dsn"] = os.environ["DATABASE_URL"]

    # Qdrant (через клиент)
    _stores["qdrant_url"] = os.getenv("QDRANT_URL", "http://qdrant:6333")

    # Neo4j
    _stores["neo4j_uri"] = os.getenv("NEO4J_URI")
    _stores["neo4j_username"] = os.getenv("NEO4J_USERNAME", "neo4j")
    _stores["neo4j_password"] = os.getenv("NEO4J_PASSWORD")

    logger.info("✓ Memory stores initialized")

# === Error Cases (PostgreSQL) ===

async def store_error_case(case: dict) -> str:
    """Сохранение кейса ошибки в PostgreSQL с proper resource management"""
    dsn = _stores.get("postgres_dsn")
    if not dsn:
        raise RuntimeError("PostgreSQL DSN not configured")

    async with managed_postgres_pool(dsn) as pool:
        async with pool.acquire() as conn:
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


async def search_error_cases(query: str, project: Optional[str] = None, limit: int = 10) -> list:
    """Поиск кейсов по тексту + проекту с дедупликацией"""
    dsn = _stores.get("postgres_dsn")
    if not dsn:
        raise RuntimeError("PostgreSQL DSN not configured")
    async with managed_postgres_pool(dsn) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, signature, fix_steps, status, created_at,
                       ts_rank_cd(search_vector, websearch_to_tsquery('russian', $1)) AS rank
                FROM error_cases
                WHERE status = 'success'
                  AND ($2::text IS NULL OR project = $2)
                ORDER BY rank DESC, created_at DESC
                LIMIT $3
            """, query, project, limit)

            # Дедупликация результатов
            return dedupe_memory([dict(r) for r in rows])

# === Audit Log ===

async def store_audit_log(audit_id: str, input: dict, output: dict, metadata: dict):
    """Сохранение аудита выполнения с proper resource management"""
    dsn = _stores.get("postgres_dsn")
    if not dsn:
        raise RuntimeError("PostgreSQL DSN not configured")
    async with managed_postgres_pool(dsn) as pool:
        async with pool.acquire() as conn:
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
    """Получение аудита по ID с proper resource management"""
    dsn = _stores.get("postgres_dsn")
    if not dsn:
        raise RuntimeError("PostgreSQL DSN not configured")
    async with managed_postgres_pool(dsn) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM audit_log WHERE audit_id = $1
            """, audit_id)
            return dict(row) if row else None

# === Knowledge Graph (Neo4j) ===

async def update_knowledge_graph(error_sig: str, fix_steps: list[str], root_cause: Optional[str] = None):
    """Обновление графа знаний после успешного фикса"""
    uri = _stores.get("neo4j_uri")
    username = _stores.get("neo4j_username", "neo4j")
    password = _stores.get("neo4j_password")
    async with managed_neo4j_driver(uri, username, password) as driver:
        async with driver.session() as session:
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
    """Закрытие соединений (теперь не требуется, т.к. используем контекстные менеджеры)"""
    logger.info("✓ Memory stores cleanup not required - using context managers")


# === Memory Helpers ===

def dedupe_memory(mem_list: List[Dict]) -> List[Dict]:
    """
    Дедупликация памяти по content/signature.
    Args:
        mem_list: Список записей памяти

    Returns:
        Список без дубликатов
    """
    seen = set()
    out = []
    for item in mem_list:
        # Ключ для дедупликации: signature или content
        key = item.get("signature") or item.get("content") or str(item)
        if key not in seen:
            out.append(item)
            seen.add(key)
    return out


def summarize_memory(memory_items: List[Dict], max_lines: int = 10) -> List[Dict]:
    """
    Резюмирование последних записей памяти.

    Args:
        memory_items: Список записей памяти
        max_lines: Максимальное количество строк в резюме

    Returns:
        Список с одной записью-резюме
    """
    if not memory_items:
        return []

    # Берём последние N записей
    recent = memory_items[-max_lines:]
    text = "\n".join(item.get("content", str(item)) for item in recent)

    # Простое резюмирование (в production можно использовать LLM)
    summary_text = f"Summary of {len(recent)} recent items:\n{text[:500]}..."

    return [{"type": "summary", "content": summary_text, "timestamp": datetime.utcnow().isoformat()}]


def extract_session_id(key: str, session_id: Optional[str] = None) -> str:
    """
    Извлечение session-id для ключей памяти.

    Args:
        key: Базовый ключ
        session_id: Опциональный session-id

    Returns:
        Ключ с session-id
    """
    if session_id:
        return f"{session_id}:{key}"

    # Генерируем hash из ключа как fallback
    return hashlib.sha256(key.encode()).hexdigest()[:16]
