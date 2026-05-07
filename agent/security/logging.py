"""
Модуль для безопасного логирования.
Фильтрует конфиденциальные данные из логов.
"""
import re
import logging
import json
from typing import Any, Dict, Set


# Ключи которые нужно маскировать
SENSITIVE_KEYS: Set[str] = {
    "token", "password", "secret", "authorization", "api_key", "apikey",
    "private_key", "access_token", "refresh_token", "credentials", "passwd",
    "gitlab_token", "neo4j_password", "postgres_password", "qdrant_api_key",
}

# Паттерны для поиска чувствительных данных
SENSITIVE_PATTERNS = [
    (re.compile(r'(bearer\s+)[a-zA-Z0-9\-_.]+', re.IGNORECASE), r'\1****'),
    (re.compile(r'(glpat-[a-zA-Z0-9\-_]{20,})'), '****'),
    (re.compile(r'(ghp_[a-zA-Z0-9]{36})'), '****'),
    (re.compile(r'(xox[baprs]-[a-zA-Z0-9\-]{10,})'), '****'),
    (re.compile(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'), r'****@****.***'),
    (re.compile(r'(password\s*[=:]\s*)([^\s,;]+)', re.IGNORECASE), r'\1****'),
    (re.compile(r'(secret\s*[=:]\s*)([^\s,;]+)', re.IGNORECASE), r'\1****'),
    (re.compile(r'(key\s*[=:]\s*)([a-zA-Z0-9\-_]{16,})', re.IGNORECASE), r'\1****'),
]

MASK_VALUE = "****"


class SensitiveDataFilter(logging.Filter):
    """
    Фильтр для маскировки конфиденциальных данных в логах.
    """

    def __init__(self, name: str = ""):
        super().__init__(name)
        self._json_pattern = re.compile(
            r'("(' + '|'.join(SENSITIVE_KEYS) + r')"\s*:\s*")([^"]+)(")',
            re.IGNORECASE
        )

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Маскирует конфиденциальные данные в сообщении лога.
        """
        # Конвертируем сообщение в строку
        msg = str(record.msg)

        # Маскировка в JSON-подобных структурах
        msg = self._json_pattern.sub(r'\1' + MASK_VALUE + r'\4', msg)

        # Маскировка по паттернам
        for pattern, replacement in SENSITIVE_PATTERNS:
            msg = pattern.sub(replacement, msg)

        # Также обрабатываем аргументы форматирования
        if record.args:
            try:
                if isinstance(record.args, dict):
                    record.args = {
                        k: self._mask_value(v) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
                elif isinstance(record.args, (list, tuple)):
                    record.args = tuple(
                        self._mask_value(v) if isinstance(v, str) else v
                        for v in record.args
                    )
            except (TypeError, AttributeError):
                pass

        record.msg = msg
        return True

    def _mask_value(self, value: str) -> str:
        """Маскирует значение."""
        result = value
        for pattern, replacement in SENSITIVE_PATTERNS:
            result = pattern.sub(replacement, result)
        return result


def mask_sensitive_data(data: Any) -> Any:
    """
    Рекурсивно маскирует конфиденциальные данные в структуре данных.

    Args:
        data: Любая структура данных (dict, list, str, etc.)

    Returns:
        Структура данных с замаскированными чувствительными полями
    """
    if isinstance(data, dict):
        return {
            k: MASK_VALUE if k.lower() in SENSITIVE_KEYS else mask_sensitive_data(v)
            for k, v in data.items()
        }
    elif isinstance(data, (list, tuple)):
        return type(data)(mask_sensitive_data(item) for item in data)
    elif isinstance(data, str):
        result = data
        for pattern, replacement in SENSITIVE_PATTERNS:
            result = pattern.sub(replacement, result)
        return result
    else:
        return data


def setup_secure_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Настраивает безопасное логирование с фильтрацией чувствительных данных.

    Returns:
        Logger: Настроенный логгер
    """
    logger = logging.getLogger("secure")
    logger.setLevel(level)

    # Создаём handler если ещё нет
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)

        # Форматтер с JSON
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)

        # Добавляем фильтр
        handler.addFilter(SensitiveDataFilter())

        logger.addHandler(handler)

    # Не распространять на корневой логгер (чтобы избежать дублирования)
    logger.propagate = False

    return logger
