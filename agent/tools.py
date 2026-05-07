# agent/tools.py
import os, re, json, asyncio, logging
from typing import Optional, Union
from pydantic import BaseModel, Field, validator
import httpx, asyncpg
from datetime import datetime

from agent.schemas import DockerCommand, GitLabAction, ExecutionResult
from agent.security.docker_validator import validate_docker_command, sanitize_container_name

logger = logging.getLogger(__name__)

GITLAB_URL = os.getenv("GITLAB_URL", "https://gitlab.dash-panel.tech")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD")
DOCKER_EXECUTOR_URL = os.getenv("DOCKER_EXECUTOR_URL", "http://docker-executor:5001")

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
    """Выполнение Cypher-запроса с параметрами и валидацией безопасности"""
    from agent.security.cypher_sanitizer import is_cypher_safe, validate_cypher_params
    
    # Валидация Cypher-запроса
    is_safe, error_msg = is_cypher_safe(cypher)
    if not is_safe:
        logger.warning(f"Cypher query blocked: {error_msg}")
        raise ValueError(f"Unsafe Cypher query: {error_msg}")
    
    # Валидация параметров
    if params:
        params_valid, params_error = validate_cypher_params(params)
        if not params_valid:
            logger.warning(f"Cypher params blocked: {params_error}")
            raise ValueError(f"Unsafe Cypher params: {params_error}")
    
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
    """Выполнение Docker-команды через docker-executor сервис"""
    try:
        # Валидация команды через security модуль
        full_command = f"docker {cmd.command}"
        is_valid, error_msg = validate_docker_command(full_command)
        if not is_valid:
            return ExecutionResult(
                error=f"Command validation failed: {error_msg}",
                exit_code=-1,
                command=cmd.command,
                timestamp=datetime.utcnow().isoformat()
            )
        
        # Санитизация имени контейнера
        safe_container = sanitize_container_name(cmd.container)
        
        # Отправка команды в docker-executor сервис
        async with httpx.AsyncClient(timeout=cmd.timeout + 30) as client:
            payload = {
                "command": f"docker {cmd.command}",
                "timeout": cmd.timeout
            }
            resp = await client.post(
                f"{DOCKER_EXECUTOR_URL}/exec",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if resp.status_code != 200:
                error_data = resp.json() if resp.content else {"error": "Unknown error"}
                return ExecutionResult(
                    error=error_data.get("error", "Executor request failed"),
                    exit_code=-1,
                    command=cmd.command,
                    timestamp=datetime.utcnow().isoformat()
                )
            
            result_data = resp.json()
            return ExecutionResult(
                stdout=result_data.get("output", ""),
                stderr=result_data.get("stderr", ""),
                exit_code=result_data.get("exit_code"),
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
