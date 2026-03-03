FROM python:3.12-slim AS builder

WORKDIR /app

# Create venv inside /app so it is included in the multi-stage COPY
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

RUN pip install --upgrade pip --quiet

# Cache dependency layer — only rebuilds when pyproject.toml changes
COPY pyproject.toml ./
# Stub packages so pip editable install can resolve the project
RUN mkdir -p agents tools && \
    touch agents/__init__.py tools/__init__.py
RUN pip install --no-cache-dir -e .

# Copy full source and re-install (picks up real packages, skips already-installed deps)
COPY . .
RUN pip install --no-cache-dir -e . --no-deps

FROM python:3.12-slim AS runtime

WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
