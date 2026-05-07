"""
Модуль для валидации Cypher-запросов к Neo4j.
Проверяет запросы на наличие разрушительных операций.
"""
import re
from typing import Tuple, List


# Запрещённые Cypher паттерны (разрушительные операции)
FORBIDDEN_CYPHER_PATTERNS: List[Tuple[str, str]] = [
    (r'\bDETACH\s+DELETE\b', "DETACH DELETE операция"),
    (r'\bDELETE\b', "DELETE операция"),
    (r'\bDROP\b', "DROP операция"),
    (r'\bREMOVE\b', "REMOVE операция"),
    (r'\bCALL\s+apoc\.do\b', "Вызов процедур изменения данных APOC"),
    (r'\bCALL\s+apoc\.create\b', "Вызов процедур создания APOC"),
]

# Разрешённые операции только для чтения
READ_ONLY_OPERATIONS = [
    r'^\s*(MATCH|OPTIONAL MATCH|RETURN|WITH|UNWIND|LOAD\s+CSV)\b',
]


def is_cypher_safe(query: str) -> Tuple[bool, str]:
    """
    Проверяет, что Cypher-запрос не содержит потенциально разрушительных операций.

    Args:
        query: Cypher-запрос

    Returns:
        tuple: (is_safe: bool, error_message: str)
    """
    if not query or not isinstance(query, str):
        return False, "Пустой или некорректный запрос"

    upper_query = query.upper()

    # Проверка на запрещённые паттерны
    for pattern, description in FORBIDDEN_CYPHER_PATTERNS:
        if re.search(pattern, upper_query, re.IGNORECASE):
            return False, f"Запрещённая операция: {description}"

    # Проверка что используются только READ-операции
    is_read_only = False
    for pattern in READ_ONLY_OPERATIONS:
        if re.match(pattern, upper_query, re.IGNORECASE):
            is_read_only = True
            break

    if not is_read_only:
        # Допускаем также WITH в начале для цепочек запросов
        if not upper_query.strip().startswith('WITH'):
            return False, "Разрешены только операции чтения (MATCH, RETURN, WITH, UNWIND)"

    # Дополнительная проверка: запрет на использование SET без явного разрешения
    # SET может использоваться для обновления свойств, что опасно
    if re.search(r'\bSET\b', upper_query):
        return False, "Операция SET запрещена (изменение данных)"

    # Проверка на множественные точки с запятой (попытка инъекции)
    if query.count(';') > 1:
        return False, "Обнаружено несколько операторов в запросе"

    return True, ""


def sanitize_cypher_identifier(identifier: str) -> str:
    """
    Санитизирует идентификатор Cypher (имена узлов, свойства).
    Оставляет только безопасные символы.
    """
    # Разрешены только alphanumeric и подчёркивание
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '', identifier)
    if not sanitized:
        raise ValueError("Идентификатор не может быть пустым после санитизации")
    # Экранирование обратными кавычками если содержит спецсимволы
    if sanitized != identifier:
        return f"`{sanitized}`"
    return sanitized


def validate_cypher_params(params: dict) -> Tuple[bool, str]:
    """
    Валидирует параметры для Cypher-запроса.
    """
    if not isinstance(params, dict):
        return False, "Параметры должны быть словарём"

    for key, value in params.items():
        # Ключи должны быть строками
        if not isinstance(key, str):
            return False, f"Ключ параметра должен быть строкой: {key}"

        # Проверка ключей на инъекции
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', key):
            return False, f"Недопустимый ключ параметра: {key}"

        # Значения не должны содержать опасные паттерны
        if isinstance(value, str):
            if re.search(r'[;{}]', value):
                return False, f"Параметр '{key}' содержит недопустимые символы"

    return True, ""
