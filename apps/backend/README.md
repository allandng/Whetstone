# Whetstone Backend

FastAPI backend for Whetstone. Orchestrates SQLite persistence (via
SQLModel) and the three local loopback services: Psirver (C++ code
execution), llama-server (LLM), and whisper-server (speech-to-text).

## Layout

```
main.py        app factory, mounts routers
db.py          SQLite engine + session factory
models.py      SQLModel table stubs
config.py      pydantic-settings configuration
routers/       sessions, cells, ai, spec
services/      psirver / llm / stt HTTP client stubs
```

## Run

```sh
cd apps/backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn main:app --reload
```

The API serves on `http://127.0.0.1:8000` with docs at `/docs`.
