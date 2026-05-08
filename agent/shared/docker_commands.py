"""
Общие константы и утилиты для работы с Docker-командами.
Используется в agent/security/ и docker-executor/
"""
from enum import Enum
from typing import Set, List, Tuple
import re

class DockerCommand(str, Enum):
    """Разрешённые Docker-команды (read-only операции)"""
    # Контейнеры
    PS = "ps"
    INSPECT = "inspect"
    LOGS = "logs"
    STATS = "stats"
    TOP = "top"
    
    # Образы
    IMAGES = "images"
    HISTORY = "history"
    
    # Сеть
    NETWORK_LS = "network ls"
    NETWORK_INSPECT = "network inspect"
    
    # Тома
    VOLUME_LS = "volume ls"
    VOLUME_INSPECT = "volume inspect"
    
    # Система
    INFO = "info"
    VERSION = "version"
    
    # Контейнер-specific (требуют имя/ID)
    EXEC = "exec"  # Только с --read-only флагами, валидируется отдельно

class AllowedShellCommand(str, Enum):
    """Allowlist для безопасных shell-команд"""
    CAT = "cat"
    LS = "ls"
    DF = "df"
    GREP = "grep"
    TAIL = "tail"
    HEAD = "head"
    FIND = "find"
    WC = "wc"
    STAT = "stat"
    PS = "ps"
    TOP = "top"

# Глобальный allowlist для быстрой проверки
ALLOWED_DOCKER_COMMANDS: Set[str] = {cmd.value for cmd in DockerCommand}

# Флаги, которые ВСЕГДА запрещены (даже с разрешёнными командами)
FORBIDDEN_FLAGS: Set[str] = {
    "--rm", "-rm",  # Удаление после выполнения
    "--force", "-f",  # Force-операции (риск)
    "--no-trunc",  # Может раскрыть чувствительные данные
}

# Флаги, требующие дополнительного подтверждения
REQUIRES_APPROVAL_FLAGS: Set[str] = {
    "--delete", "--remove", "-d", "-r",
    "exec",  # exec может запускать произвольные команды
}

def parse_docker_command(cmd_str: str) -> Tuple[bool, str, List[str]]:
    """
    Парсит docker-команду и возвращает:
    (валидна?, ошибка_или_сообщение, список_аргументов)
    """
    import shlex
    
    if not cmd_str.strip().startswith("docker "):
        return False, "Command must start with 'docker '", []
    
    try:
        parts = shlex.split(cmd_str)
    except ValueError as e:
        return False, f"Parse error: {e}", []
    
    if len(parts) < 2:
        return False, "Invalid docker command format", []
    
    # parts[0] = "docker", parts[1] = команда
    command = parts[1]
    args = parts[2:]
    
    # Проверка подкоманд (network ls, volume ls)
    if len(parts) >= 3 and command in ("network", "volume"):
        command = f"{command} {parts[2]}"
        args = parts[3:]
    
    if command not in ALLOWED_DOCKER_COMMANDS:
        return False, f"Command '{command}' not in allowlist", []
    
    # Проверка запрещённых флагов
    for arg in args:
        if arg in FORBIDDEN_FLAGS:
            return False, f"Flag '{arg}' is forbidden", []
        # Проверка на injection в аргументах
        if re.search(r'[;&|`$(){}<>\\]', arg):
            return False, f"Argument contains dangerous characters: {arg}", []
    
    return True, "OK", args

def requires_human_approval(cmd_str: str) -> bool:
    """Проверяет, требует ли команда подтверждения пользователя"""
    is_valid, _, args = parse_docker_command(cmd_str)
    if not is_valid:
        return True  # Неизвестная команда → требует проверки
    
    # Проверка флагов, требующих approval
    for arg in args:
        if arg in REQUIRES_APPROVAL_FLAGS:
            return True
    
    # exec всегда требует approval (может запускать произвольный код)
    if "exec" in cmd_str:
        return True
    
    return False
