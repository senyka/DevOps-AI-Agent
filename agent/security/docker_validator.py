"""
Модуль безопасности для валидации Docker-команд.
Реализует строгий allowlist подход.
Использует общий модуль docker_commands для централизованной конфигурации.
"""
from typing import Set, List
import re

from agent.shared.docker_commands import (
    parse_docker_command as parse_docker_cmd_shared,
    requires_human_approval,
    ALLOWED_DOCKER_COMMANDS,
    FORBIDDEN_FLAGS,
    REQUIRES_APPROVAL_FLAGS
)

class AllowedCommand(str, Enum):
    """Разрешённые Docker команды."""
    PS = "ps"
    LOGS = "logs"
    INSPECT = "inspect"
    VERSION = "version"
    INFO = "info"
    STATS = "stats"


# Разрешённые флаги для каждой команды
ALLOWED_FLAGS: dict[AllowedCommand, Set[str]] = {
    AllowedCommand.PS: {"-a", "--all", "--format", "--filter", "--no-trunc", "-q", "--quiet", "-s", "--size"},
    AllowedCommand.LOGS: {"--tail", "--since", "--until", "--timestamps", "-f", "--follow", "-n", "--details"},
    AllowedCommand.INSPECT: {"--format", "--size", "-s"},
    AllowedCommand.VERSION: set(),
    AllowedCommand.INFO: {"--format"},
    AllowedCommand.STATS: {"--format", "--no-stream", "-a", "--all"},
}

# Запрещённые подстроки в аргументах
FORBIDDEN_SUBSTRINGS: List[str] = [
    "rm", "kill", "stop", "exec", "run", "build", "push", "pull", "rmi",
    "--force", "-f", "delete", "remove", "prune", "system"
]


def validate_docker_command(command: str) -> tuple[bool, str]:
    """
    Валидирует Docker команду по белому списку.
    Использует общую функцию из agent.shared.docker_commands.

    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not command or not isinstance(command, str):
        return False, "Пустая или некорректная команда"

    # Нормализация: убираем лишние пробелы
    command = command.strip()

    # Проверка что команда начинается с docker
    parts = command.split()
    if not parts:
        return False, "Пустая команда"

    if parts[0] != "docker":
        return False, f"Команда должна начинаться с 'docker', получено: {parts[0]}"

    # Используем общую функцию валидации
    is_valid, message, _ = parse_docker_cmd_shared(command)
    
    if not is_valid:
        return False, message
    
    # Дополнительная проверка на запрещённые подстроки
    for part in parts[2:]:  # Пропускаем "docker" и команду
        part_lower = part.lower()
        for danger in FORBIDDEN_SUBSTRINGS:
            if danger in part_lower:
                return False, f"Обнаружена подозрительная подстрока '{danger}' в аргументе"

    return True, ""


def check_approval_required(command: str) -> bool:
    """Проверка необходимости human-in-the-loop"""
    return requires_human_approval(command)


def sanitize_container_name(name: str) -> str:
    """
    Санитизирует имя контейнера, оставляя только безопасные символы.
    """
    # Разрешены только alphanumeric, дефис, подчёркивание, точка
    sanitized = re.sub(r'[^a-zA-Z0-9_.-]', '', name)
    if not sanitized:
        raise ValueError("Имя контейнера не может быть пустым после санитизации")
    return sanitized
