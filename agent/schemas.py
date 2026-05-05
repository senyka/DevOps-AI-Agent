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
