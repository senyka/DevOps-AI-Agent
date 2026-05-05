### `worker/Dockerfile`
```dockerfile
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Пользователь без root
RUN useradd -m -u 1000 worker && chown -R worker:worker /app
USER worker

CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "--concurrency=2"]
```

---
