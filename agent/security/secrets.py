"""
Модуль для безопасного чтения секретов.
Поддерживает Docker Secrets и переменные окружения.
"""
import os
from typing import Optional


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Читает секрет из Docker secret (файл) или переменной окружения.
    
    Приоритет:
    1. Docker Secret (файл по пути {KEY}_FILE)
    2. Переменная окружения {KEY}
    3. Значение по умолчанию
    
    Args:
        key: Имя секрета/переменной
        default: Значение по умолчанию
        
    Returns:
        str или None: Значение секрета
    """
    # Попытка прочитать из Docker Secret
    file_path = os.environ.get(f"{key}_FILE")
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except (IOError, OSError) as e:
            # Логирование ошибки (без вывода значения!)
            print(f"Warning: Cannot read secret file {file_path}: {e}")
            # Не возвращаем ошибку, пробуем fallback
    
    # Fallback на переменную окружения
    return os.environ.get(key, default)


def get_required_secret(key: str) -> str:
    """
    Получает обязательный секрет.
    
    Raises:
        ValueError: Если секрет не найден
    """
    value = get_secret(key)
    if value is None:
        raise ValueError(
            f"Required secret '{key}' not found. "
            f"Set {key} environment variable or provide {key}_FILE path."
        )
    return value


def validate_secrets_config() -> tuple[bool, list[str]]:
    """
    Проверяет конфигурацию секретов.
    
    Returns:
        tuple: (is_valid: bool, errors: list[str])
    """
    errors = []
    
    # Список обязательных секретов для проверки
    required_secrets = [
        "GITLAB_TOKEN",
        "POSTGRES_PASSWORD",
        "NEO4J_PASSWORD",
    ]
    
    for secret in required_secrets:
        value = get_secret(secret)
        if value is None:
            errors.append(f"Missing required secret: {secret}")
        elif len(value) < 8:
            errors.append(f"Secret {secret} is too short (min 8 characters)")
    
    # Проверка на типичные ошибки (дефолтные значения)
    dangerous_defaults = ["password", "secret", "changeme", "admin", "123456"]
    for secret in required_secrets:
        value = get_secret(secret, "").lower()
        if value in dangerous_defaults:
            errors.append(f"Secret {secret} has a weak default value")
    
    return len(errors) == 0, errors
