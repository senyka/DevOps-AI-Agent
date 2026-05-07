"""
Модуль безопасности для валидации Docker-команд.
Реализует строгий allowlist подход.
"""
from enum import Enum
from typing import Set, List
import re


class AllowedCommand(str, Enum):
    """Разрешённые Docker команды."""
    PS = "ps"
    LOGS = "logs"
    INSPECT = "inspect"
    VERSION = "version"
    INFO = "info"


# Разрешённые флаги для каждой команды
ALLOWED_FLAGS: dict[AllowedCommand, Set[str]] = {
    AllowedCommand.PS: {"-a", "--all", "--format", "--filter", "--no-trunc", "-q", "--quiet", "-s", "--size"},
    AllowedCommand.LOGS: {"--tail", "--since", "--until", "--timestamps", "-f", "--follow", "-n", "--details"},
    AllowedCommand.INSPECT: {"--format", "--size", "-s"},
    AllowedCommand.VERSION: set(),
    AllowedCommand.INFO: {"--format"},
}

# Запрещённые подстроки в аргументах
FORBIDDEN_SUBSTRINGS: List[str] = [
    "rm", "kill", "stop", "exec", "run", "build", "push", "pull", "rmi",
    "--force", "-f", "delete", "remove", "prune", "system"
]


def validate_docker_command(command: str) -> tuple[bool, str]:
    """
    Валидирует Docker команду по белому списку.

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

    if len(parts) < 2:
        return False, "Не указана подкоманда"

    # Основная подкоманда
    sub_cmd = parts[1]

    try:
        cmd = AllowedCommand(sub_cmd)
    except ValueError:
        return False, f"Команда '{sub_cmd}' не входит в разрешённый список: {[c.value for c in AllowedCommand]}"

    allowed_flags = ALLOWED_FLAGS.get(cmd, set())

    # Проверка флагов и аргументов
    i = 2
    while i < len(parts):
        part = parts[i]

        if part.startswith("-"):
            # Извлекаем имя флага (без значения)
            flag = part.split("=")[0]
            # Для флагов с короткой формой типа -n 10
            if flag == part and i + 1 < len(parts) and not parts[i + 1].startswith("-"):
                # Это флаг со значением в следующем аргументе
                pass

            if flag not in allowed_flags:
                return False, f"Флаг '{flag}' не разрешён для команды '{cmd.value}'"
        else:
            # Аргумент (имя контейнера, image id и т.д.)
            # Проверка на запрещённые подстроки
            part_lower = part.lower()
            for danger in FORBIDDEN_SUBSTRINGS:
                if danger in part_lower:
                    return False, f"Обнаружена подозрительная подстрока '{danger}' в аргументе"

            # Дополнительная проверка: аргумент не должен содержать shell-метасимволы
            if re.search(r'[;&|`$(){}]', part):
                return False, "Аргумент содержит недопустимые символы"

        i += 1

    return True, ""


def sanitize_container_name(name: str) -> str:
    """
    Санитизирует имя контейнера, оставляя только безопасные символы.
    """
    # Разрешены только alphanumeric, дефис, подчёркивание, точка
    sanitized = re.sub(r'[^a-zA-Z0-9_.-]', '', name)
    if not sanitized:
        raise ValueError("Имя контейнера не может быть пустым после санитизации")
    return sanitized
