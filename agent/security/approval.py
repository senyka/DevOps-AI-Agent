"""
Модуль для проверки опасных паттернов в ответах LLM.
Реализует Human-in-the-loop подход.
"""
import re
from typing import Tuple, List
from dataclasses import dataclass


@dataclass
class DangerSignal:
    """Сигнал опасности."""
    pattern: re.Pattern
    description: str
    severity: str  # "critical", "high", "medium"


# Список паттернов опасности
DANGER_SIGNALS: List[DangerSignal] = [
    DangerSignal(re.compile(r'\brm\b', re.IGNORECASE), "Удаление файлов/контейнеров", "critical"),
    DangerSignal(re.compile(r'\bkill\b', re.IGNORECASE), "Принудительная остановка процессов", "critical"),
    DangerSignal(re.compile(r'docker\s+kill', re.IGNORECASE), "Принудительная остановка контейнера", "critical"),
    DangerSignal(re.compile(r'docker\s+exec', re.IGNORECASE), "Выполнение команд внутри контейнера", "high"),
    DangerSignal(re.compile(r'docker\s+stop', re.IGNORECASE), "Остановка контейнера", "high"),
    DangerSignal(re.compile(r'docker\s+rm', re.IGNORECASE), "Удаление контейнера", "critical"),
    DangerSignal(re.compile(r'docker\s+rmi', re.IGNORECASE), "Удаление образа", "critical"),
    DangerSignal(re.compile(r'\bDROP\b', re.IGNORECASE), "SQL DROP операция", "critical"),
    DangerSignal(re.compile(r'\bDELETE\b', re.IGNORECASE), "SQL DELETE операция", "high"),
    DangerSignal(re.compile(r'--force\b|-f\b', re.IGNORECASE), "Принудительное выполнение", "high"),
    DangerSignal(re.compile(r'\bsudo\b', re.IGNORECASE), "Повышение привилегий", "high"),
    DangerSignal(re.compile(r'chmod\s+[0-7]{3,4}', re.IGNORECASE), "Изменение прав доступа", "medium"),
    DangerSignal(re.compile(r'chown\b', re.IGNORECASE), "Изменение владельца", "medium"),
    DangerSignal(re.compile(r'curl.*\|\s*(ba)?sh', re.IGNORECASE), "Выполнение удалённого скрипта", "critical"),
    DangerSignal(re.compile(r'wget.*\|\s*(ba)?sh', re.IGNORECASE), "Выполнение удалённого скрипта", "critical"),
]


def check_danger(response: str) -> Tuple[bool, str, str]:
    """
    Проверяет ответ LLM на наличие опасных паттернов.

    Args:
        response: Текст ответа от LLM

    Returns:
        tuple: (is_dangerous: bool, description: str, severity: str)
    """
    if not response or not isinstance(response, str):
        return False, "", ""

    for signal in DANGER_SIGNALS:
        if signal.pattern.search(response):
            return True, signal.description, signal.severity

    return False, "", ""


def get_all_dangers(response: str) -> List[Tuple[str, str]]:
    """
    Возвращает все обнаруженные опасные паттерны.

    Returns:
        list: [(description, severity), ...]
    """
    dangers = []
    for signal in DANGER_SIGNALS:
        if signal.pattern.search(response):
            dangers.append((signal.description, signal.severity))
    return dangers


def requires_approval(response: str) -> bool:
    """
    Определяет, требует ли ответ подтверждения пользователем.
    Любая опасность уровня critical или high требует подтверждения.
    """
    is_dangerous, _, severity = check_danger(response)
    if not is_dangerous:
        return False
    return severity in ("critical", "high")
