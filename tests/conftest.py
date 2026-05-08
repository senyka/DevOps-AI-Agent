# tests/conftest.py
import pytest
import os
import sys
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Устанавливаем тестовые переменные окружения"""
    # Переопределяем критические переменные для тестов
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-test-token-12345")
    monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("AGENT_MODE", "advisory")  # Безопасный режим для тестов
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.9")  # Высокий порог
    
    yield
    
    # Cleanup после теста (опционально)

@pytest.fixture
def mock_httpx_client():
    """Мокированный httpx.AsyncClient для тестов"""
    import httpx
    from unittest.mock import AsyncMock, MagicMock
    
    client = httpx.AsyncClient()
    client.post = AsyncMock()
    client.get = AsyncMock()
    return client
