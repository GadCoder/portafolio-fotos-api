set dotenv-load := true

# Start the API with auto-reload.
dev:
    uv run uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# Start the API without auto-reload.
serve:
    uv run uvicorn main:app --host 0.0.0.0 --port 8080

# Install dependencies and refresh uv.lock when needed.
install:
    uv sync

# Update all dependencies within the constraints in pyproject.toml.
upgrade:
    uv lock --upgrade
    uv sync
