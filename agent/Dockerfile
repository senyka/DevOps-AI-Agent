### `agent/Dockerfile`
**Назначение:** Сборка контейнера для основного приложения агента.

```dockerfile
FROM python:3.11-slim-bookworm

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential libpq-dev postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копирование зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY . .

# Создание пользователя без прав root (безопасность)
RUN useradd -m -u 1000 agent && chown -R agent:agent /app
USER agent

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Порт по умолчанию
EXPOSE 8080 9090

# Точка входа
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---
