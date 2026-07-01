venv:
    uv sync
    cp -n .env.example .env 2>/dev/null || true

venv-dev:
    uv sync --group dev
    uv run prek install
    @echo "Dev environment ready"

docs:
    uv run --group docs mkdocs serve

test-fedotmas:
    uv run pytest packages/fedotmas/tests

test-fedotmas-llm:
    uv run pytest packages/fedotmas-llm/tests
