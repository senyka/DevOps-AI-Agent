# agent/utils.py
"""
Общие утилиты для DevOps AI Agent.
"""
import uuid
import hashlib
import time
from typing import Optional
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)


def generate_audit_id() -> str:
    """
    Генерация уникального ID для аудита.
    
    Returns:
        str: 16-символьный hex-идентификатор
    """
    return hashlib.sha256(f"{uuid.uuid4()}{time.time()}".encode()).hexdigest()[:16]


@asynccontextmanager
async def managed_qdrant_client(url: str):
    """
    Контекстный менеджер для Qdrant клиента с гарантией закрытия.
    
    Args:
        url: URL Qdrant сервера
        
    Yields:
        AsyncQdrantClient: Клиент Qdrant
    """
    from qdrant_client import AsyncQdrantClient
    
    client = AsyncQdrantClient(url=url)
    try:
        yield client
    finally:
        await client.close()


@asynccontextmanager
async def managed_neo4j_driver(uri: str, username: str, password: str):
    """
    Контекстный менеджер для Neo4j драйвера с гарантией закрытия.
    
    Args:
        uri: URI Neo4j сервера
        username: Имя пользователя
        password: Пароль
        
    Yields:
        AsyncGraphDatabase.driver: Драйвер Neo4j
    """
    from neo4j import AsyncGraphDatabase
    
    driver = AsyncGraphDatabase.driver(uri, auth=(username, password))
    try:
        yield driver
    finally:
        await driver.close()


@asynccontextmanager
async def managed_postgres_pool(dsn: str, min_size: int = 2, max_size: int = 10):
    """
    Контекстный менеджер для PostgreSQL pool с гарантией закрытия.
    
    Args:
        dsn: DSN подключения к PostgreSQL
        min_size: Минимальный размер пула
        max_size: Максимальный размер пула
        
    Yields:
        asyncpg.Pool: Пул подключений PostgreSQL
    """
    import asyncpg
    
    pool = await asyncpg.create_pool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=30
    )
    try:
        yield pool
    finally:
        await pool.close()


async def safe_async_call(coro, default=None, logger_name: Optional[str] = None):
    """
    Безопасный вызов асинхронной функции с обработкой ошибок.
    
    Args:
        coro: Coroutine для выполнения
        default: Значение по умолчанию при ошибке
        logger_name: Имя логгера для записи ошибок
        
    Returns:
        Результат выполнения или default при ошибке
    """
    import logging
    
    log = logging.getLogger(logger_name or __name__)
    try:
        return await coro
    except Exception as e:
        log.exception(f"Async call failed: {e}")
        return default
