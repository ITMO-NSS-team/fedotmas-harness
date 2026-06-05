venv:
    uv sync
    cp -n .env.example .env 2>/dev/null || true

venv-dev:
    uv sync --group dev
    uv run prek install
    @echo "Dev environment ready"
