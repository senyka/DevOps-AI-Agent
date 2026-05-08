"""
Docker Executor Service - безопасный микросервис для выполнения Docker команд.
Принимает только разрешённые команды через HTTP API.
Zero-Trust Execution: все команды валидируются по белому списку.
"""
from flask import Flask, request, jsonify
import subprocess
import shlex
import os
import re
from enum import Enum
from typing import List, Set

app = Flask(__name__)

# === Zero-Trust Allowlist ===

class AllowedCommand(str, Enum):
    """Разрешённые Docker команды (синхронизировано с agent/security/docker_validator.py)"""
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

# Максимальная длина вывода (защита от DoS)
MAX_OUTPUT_LENGTH = int(os.getenv("MAX_OUTPUT_LENGTH", "100000"))

# Таймаут выполнения команд (секунды)
DEFAULT_TIMEOUT = int(os.getenv("COMMAND_TIMEOUT", "30"))


def validate_command(command_str: str) -> tuple[bool, str, list]:
    """
    Валидирует Docker команду по белому списку (Zero-Trust).
    Использует общую функцию из agent.shared.docker_commands.
    Returns:
        tuple: (is_valid, error_message, parts)
    """
    # Используем единую функцию валидации из общего модуля
    is_valid, error_msg, args = parse_docker_command(command_str)
    if not is_valid:
        return False, error_msg, []
    return True, "", ["docker"] + args


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "allowed_commands": list(ALLOWED_DOCKER_COMMANDS),
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
        "allowed_commands": list(ALLOWED_DOCKER_COMMANDS),
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # Запускаем только на localhost или внутри Docker сети
    host = os.getenv("HOST", "0.0.0.0")

    print(f"Starting Docker Executor on {host}:{port}")
    print(f"Allowed commands: {list(ALLOWED_DOCKER_COMMANDS)}")

    app.run(host=host, port=port, debug=debug)
