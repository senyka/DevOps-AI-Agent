"""
Модуль безопасности - импортирует все компоненты.
"""
from agent.shared.docker_commands import (
    DockerCommand as AllowedCommand,
    ALLOWED_DOCKER_COMMANDS as ALLOWED_FLAGS,
    FORBIDDEN_FLAGS as FORBIDDEN_SUBSTRINGS,
)
from agent.security.docker_validator import (
    validate_docker_command,
    sanitize_container_name,
    check_approval_required,
)

from agent.security.approval import (
    DangerSignal,
    DANGER_SIGNALS,
    check_danger,
    get_all_dangers,
    requires_approval,
)

from agent.security.cypher_sanitizer import (
    FORBIDDEN_CYPHER_PATTERNS,
    READ_ONLY_OPERATIONS,
    is_cypher_safe,
    sanitize_cypher_identifier,
    validate_cypher_params,
)

from agent.security.secrets import (
    get_secret,
    get_required_secret,
    validate_secrets_config,
)

from agent.security.logging import (
    SENSITIVE_KEYS,
    SENSITIVE_PATTERNS,
    MASK_VALUE,
    SensitiveDataFilter,
    mask_sensitive_data,
    setup_secure_logging,
)

__all__ = [
    # Docker validation
    "AllowedCommand",
    "ALLOWED_FLAGS",
    "FORBIDDEN_SUBSTRINGS",
    "validate_docker_command",
    "sanitize_container_name",
    "check_approval_required",
    # Approval
    "DangerSignal",
    "DANGER_SIGNALS",
    "check_danger",
    "get_all_dangers",
    "requires_approval",
    # Cypher
    "FORBIDDEN_CYPHER_PATTERNS",
    "READ_ONLY_OPERATIONS",
    "is_cypher_safe",
    "sanitize_cypher_identifier",
    "validate_cypher_params",
    # Secrets
    "get_secret",
    "get_required_secret",
    "validate_secrets_config",
    # Logging
    "SENSITIVE_KEYS",
    "SENSITIVE_PATTERNS",
    "MASK_VALUE",
    "SensitiveDataFilter",
    "mask_sensitive_data",
    "setup_secure_logging",
]
