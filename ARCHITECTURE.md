# 🏗️ Архитектура DevOps-AI-Agent

> **Статус**: 🟡 Активная разработка | **Обновлено**: Май 2026  
> Документ описывает высокоуровневую архитектуру, границы компонентов, потоки данных и принципы безопасности системы.

---

## 📖 Введение

DevOps-AI-Agent — это автономный ассистент для диагностики, исправления и предотвращения инцидентов в DevOps-инфраструктуре. Система построена на базе **LangGraph** (управляемый граф состояний), использует **гибридную память** (граф + вектор) и следует принципу **Zero-Trust Execution**: ни один деструктивный запрос не выполняется без валидации и явного подтверждения.

---

## 🧩 Детальное описание компонентов

### 1. 👤 Пользовательский слой
| Файл/Модуль | Назначение |
|-------------|------------|
| `CLI (agent/cli/)` | Интерфейс взаимодействия: `ask`, `fix`, `memory`. Поддерживает интерактивный режим и batch-обработку. |
| `API (опционально)` | REST/gRPC эндпоинты для интеграции с CI/CD пайплайнами, Slack, Jira. |

**Принцип**: Минимальная задержка, стандартизированные входные схемы (Pydantic), поддержка контекстных сессий.

---

### 2. 🤖 Ядро агента (`agent/`)
| Файл | Роль в архитектуре |
|------|---------------------|
| `main.py` | Точка входа. Инициализирует окружение, загружает конфиги, запускает LangGraph цикл. |
| `graph.py` | Определение графа состояний. Узлы: `parse_intent` → `retrieve_context` → `generate_plan` → `execute` → `reflect`. |
| `llm.py` | Абстракция над LLM-провайдерами. Поддерживает OpenAI, vLLM, локальные модели. Управляет temperature, max_tokens, streaming. |
| `memory.py` | Гибридная память:<br>• **Neo4j**: граф инцидентов, связей сервисов, истории действий.<br>• **Qdrant**: семантический поиск по документации, логам, Runbooks.<br>• **In-memory**: краткосрочный контекст сессии. |
| `tools.py` | Реестр инструментов: `kubectl`, `docker`, `git`, `curl`, `grep`, `systemctl`. Все инструменты асинхронны, возвращают структурированный `ToolResponse`. |
| `schemas.py` | Pydantic-модели: `AgentState`, `ToolInput`, `AuditRecord`. Гарантируют типобезопасность на всех этапах графа. |

---

### 3. 🔐 Модуль безопасности (`agent/security/`)
| Файл | Механизм защиты |
|------|-----------------|
| `approval.py` | Human-in-the-Loop. Блокирует действия с флагами `dangerous: true` до получения явного подтверждения пользователя. |
| `docker_validator.py` | Allowlist Docker-команд. Запрещает `--privileged`, монтирование хост-путей, использование `root` в контейнерах. |
| `cypher_sanitizer.py` | Валидация Cypher-запросов к Neo4j. Предотвращает injection через параметризованные запросы и whitelist-операторы. |
| `secrets.py` | Управление секретами. Загружает токены из Docker Secrets / `.env`, маскирует в логах, ротация по TTL. |
| `logging.py` | Аудит-логирование. Все действия записываются в `audit.jsonl` с HMAC-подписью для предотвращения tampering. |

---

### 4. 🐳 Изолированный исполнитель (`docker-executor/`)
Архитектурное решение, исключающее прямой доступ агента к Docker-сокету хоста.

| Компонент | Описание |
|-----------|----------|
| `app.py` | FastAPI-сервер. Принимает JSON-задачи, валидирует, выполняет в изолированном контейнере, возвращает stdout/stderr/exit_code. |
| `Dockerfile` | Минималистичный образ на основе `docker:dind` или `alpine`. Не содержит shell по умолчанию, ограниченные capabilities. |
| `requirements.txt` | Зависимости: `fastapi`, `uvicorn`, `docker`, `pydantic`, `aiohttp`. |

**Поток**: `Agent → HTTP POST /execute → Validator → subprocess.run(docker ...) → JSON Response`

---

### 5. 💾 Слой данных и хранилищ
| Хранилище | Роль | Конфигурация |
|-----------|------|--------------|
| **Neo4j** | Граф знаний: сервисы, зависимости, инциденты, действия агента. | `config/neo4j.conf`, инициализация через `init/01_schema.sql` |
| **Qdrant** | Векторное хранилище для RAG: документация, логи, ошибки, best practices. | `config/qdrant.yaml`, коллекции с HNSW индексом |
| **PostgreSQL** | Реляционные данные: пользователи, настройки, сессии, метрики. | `init/02_indexes.sql`, GIN для полнотекстового поиска |
| **LoRA Adapters** | Доменная адаптация LLM под DevOps-контекст (K8s, Terraform, CI/CD). | `lora_adapters/devops_v1/`, подгружаются динамически |

---

### 6. 🌍 Внешние интеграции
Агент взаимодействует с инфраструктурой через официальные API/CLI:
- **Kubernetes API**: чтение логов, событий, состояния подов/нод.
- **GitLab/GitHub API**: анализ MR, pipeline status, issue tracking.
- **Docker Registry**: проверка образов, тегов, уязвимостей.
- **Prometheus/Alertmanager**: получение метрик и алертов в реальном времени.

Все вызовы проходят через `tools.py` с автоматическим retry, rate-limiting и circuit breaker.

---

### 7. 📊 Наблюдаемость и защита
| Компонент | Назначение |
|-----------|------------|
| `config/guardrails/` | NeMo Guardrails: фильтрация prompt injection, jailbreak, токсичных запросов. |
| `logs/audit.jsonl` | Неизменяемый журнал действий. Формат: `{timestamp, user, action, params, result, signature}`. |
| `monitoring/dashboards/` | Grafana-дашборды (в разработке): latency, tool usage, approval rate, error budget. |

---

## 🔄 Жизненный цикл запроса

```mermaid
sequenceDiagram
    participant U as User
    participant C as CLI
    participant A as Agent Core
    participant S as Security
    participant E as Executor
    participant D as Data Layer
    participant X as External

    U->>C: ask "почему упал pod?"
    C->>A: init State
    A->>A: parse_intent()
    A->>D: retrieve_context(Neo4j+Qdrant)
    D-->>A: related incidents + docs
    A->>A: generate_plan(tools=[k8s_logs])
    A->>S: check_action(k8s_logs)
    S-->>A: ✅ auto-approve (read-only)
    A->>E: POST /execute {cmd: "kubectl logs..."}
    E->>E: validate_command()
    E->>X: kubectl → K8s API
    X-->>E: logs output
    E-->>A: HTTP 200 + result
    A->>S: audit_log(action, result)
    S->>D: CREATE (:Audit)
    A->>C: format_response()
    C-->>U: answer + recommendations
