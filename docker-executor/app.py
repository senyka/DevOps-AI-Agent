"""
Docker Executor Service - безопасный микросервис для выполнения Docker команд.
Принимает только разрешённые команды через HTTP API.
"""
from flask import Flask, request, jsonify
import subprocess
import shlex
import os
import re

app = Flask(__name__)

# Получаем список разрешённых команд из переменной окружения
ALLOWED_COMMANDS = os.getenv("ALLOWED_COMMANDS", "ps,logs,inspect,version,info").split(",")

# Максимальная длина вывода (защита от DoS)
MAX_OUTPUT_LENGTH = int(os.getenv("MAX_OUTPUT_LENGTH", "100000"))

# Таймаут выполнения команд (секунды)
DEFAULT_TIMEOUT = int(os.getenv("COMMAND_TIMEOUT", "30"))


def validate_command(command_str: str) -> tuple[bool, str, list]:
    """
    Валидирует и разбирает команду.

    Returns:
        tuple: (is_valid, error_message, parts)
    """
    if not command_str or not isinstance(command_str, str):
        return False, "Пустая команда", []

    command_str = command_str.strip()

    # Разбираем команду с учётом кавычек
    try:
        parts = shlex.split(command_str)
    except ValueError as e:
        return False, f"Ошибка разбора команды: {e}", []

    if not parts:
        return False, "Пустая команда", []

    # Проверка что начинается с docker
    if parts[0] != "docker":
        return False, f"Команда должна начинаться с 'docker', получено: {parts[0]}", []

    if len(parts) < 2:
        return False, "Не указана подкоманда", []

    sub_cmd = parts[1]

    # Проверка подкоманды в allowlist
    if sub_cmd not in ALLOWED_COMMANDS:
        return False, f"Команда '{sub_cmd}' не входит в разрешённый список: {ALLOWED_COMMANDS}", []

    # Дополнительная проверка на запрещённые паттерны в аргументах
    forbidden_patterns = [
        r'\brm\b', r'\bkill\b', r'\bstop\b', r'\bexec\b',
        r'\brun\b', r'\bbuild\b', r'\bpush\b', r'\bpull\b',
        r'--force\b', r'\b-f\b', r'\bdelete\b', r'\bremove\b',
    ]

    for part in parts[2:]:
        for pattern in forbidden_patterns:
            if re.search(pattern, part, re.IGNORECASE):
                return False, f"Обнаружена запрещённая подстрока в аргументе: {part}", []

        # Проверка на shell-метасимволы
        if re.search(r'[;&|`$(){}]', part):
            return False, f"Аргумент содержит недопустимые символы: {part}", []

    return True, "", parts


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "allowed_commands": ALLOWED_COMMANDS,
        "max_output_length": MAX_OUTPUT_LENGTH,
        "timeout": DEFAULT_TIMEOUT,
    })


@app.route("/exec", methods=["POST"])
def exec_docker():
    """
    Выполняет Docker команду.

    Ожидает JSON: {"command": "docker ps -a"}
    """
    # Проверка Content-Type
    if not request.is_json:
        return jsonify({"error": "Content-Type должен быть application/json"}), 400

    data = request.get_json()
    if not data or "command" not in data:
        return jsonify({"error": "Отсутствует поле 'command'"}), 400

    command_str = data.get("command", "")

    # Валидация команды
    is_valid, error_msg, parts = validate_command(command_str)
    if not is_valid:
        return jsonify({"error": error_msg}), 400

    # Экранирование аргументов для безопасности
    safe_parts = ["docker"] + parts[1:]  # docker уже проверен

    # Формируем команду для subprocess (без shell=True!)
    timeout = data.get("timeout", DEFAULT_TIMEOUT)

    try:
        result = subprocess.run(
            safe_parts,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,  # Важно: не используем shell!
        )

        output = result.stdout
        stderr = result.stderr

        # Обрезаем вывод если слишком длинный
        if len(output) > MAX_OUTPUT_LENGTH:
            output = output[:MAX_OUTPUT_LENGTH] + "\n... (output truncated)"

        response = {
            "success": result.returncode == 0,
            "output": output,
            "exit_code": result.returncode,
        }

        if stderr:
            response["stderr"] = stderr[:1000]  # Ограничиваем stderr

        return jsonify(response)

    except subprocess.TimeoutExpired:
        return jsonify({"error": f"Command timed out after {timeout}s"}), 504
    except FileNotFoundError as e:
        return jsonify({"error": f"Docker command not found: {str(e)}"}), 500
    except Exception as e:
        # Логирование ошибки (без деталей которые могут содержать секреты)
        app.logger.error(f"Error executing command: {type(e).__name__}")
        return jsonify({"error": "Internal error executing command"}), 500


@app.route("/allowed", methods=["GET"])
def get_allowed_commands():
    """Возвращает список разрешённых команд."""
    return jsonify({
        "allowed_commands": ALLOWED_COMMANDS,
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # Запускаем только на localhost или внутри Docker сети
    host = os.getenv("HOST", "0.0.0.0")

    print(f"Starting Docker Executor on {host}:{port}")
    print(f"Allowed commands: {ALLOWED_COMMANDS}")

    app.run(host=host, port=port, debug=debug)
