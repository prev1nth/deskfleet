# DeskFleet

AI-powered customer support agent that classifies, researches, and resolves support tickets using a multi-agent LangGraph pipeline backed by OpenAI.

## How it works

A ticket comes in → prompt-injection guard → classifier → researcher (with tool calls to FakeStore API) → responder → reviewer loop. Each step is traced to SQLite for observability.

## Guardrails & validations - for simplicity, implemented basic regex checks and redact keywords.

- **Prompt injection** — rejects tickets containing: "ignore previous instructions", "you are now a/an", "system:", "override instructions", "forget prior", "disregard instructions", "new instructions:", "prompt injection", "act as if/a/an", "pretend you are", "jailbreak", "DAN mode"
- **PII redaction** — emails, phone numbers, SSNs, and credit card numbers are redacted before the ticket hits the LLM and again on the output.

## Project structure

```
app/
  main.py          # FastAPI routes
  graph.py          # LangGraph agent pipeline (classifier → researcher → responder → reviewer)
  tools.py          # FakeStore API integrations (orders, products)
  guardrails.py     # Prompt injection detection + PII redaction
  metrics.py        # Prometheus counters + cost tracking
  storage.py        # SQLite persistence (tickets, traces, metrics)
  quota.py          # OpenAI spend cap enforcement
  model.py          # Pydantic request/response models
  consts.py         # Injection patterns, PII regex, config
  llm_consts.py     # System prompts
static/             # Admin dashboard, metrics UI
tests/              # pytest suite
```

## Running locally

### Option 1: Docker

```bash
cp .env.example .env   # set your OPENAI_API_KEY
docker compose up --build
```

App runs at `http://localhost:8000`.

### Option 2: Direct

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set your OPENAI_API_KEY
uvicorn app.main:app --reload --port 8000
```

## Environment variables

| Variable            | Required | Description                              |
| ------------------- | -------- | ---------------------------------------- |
| `OPENAI_API_KEY`    | Yes      | OpenAI API key                           |
| `DB_PATH`           | No       | SQLite path (default: `deskfleet.db`)    |
| `LANGCHAIN_API_KEY` | No       | LangSmith tracing key                    |
| `LANGSMITH_TRACING` | No       | Enable LangSmith traces (`true`/`false`) |

## Key endpoints

| Method | Path                  | Description                    |
| ------ | --------------------- | ------------------------------ |
| `POST` | `/resolve`            | Submit a ticket for resolution |
| `GET`  | `/health`             | Health check                   |
| `GET`  | `/api/tickets`        | List processed tickets         |
| `GET`  | `/api/tickets/{id}`   | Ticket detail + traces         |
| `GET`  | `/metrics/prometheus` | Prometheus metrics             |
| `GET`  | `/admin`              | Admin dashboard                |

## Tests

```bash
pytest
```
