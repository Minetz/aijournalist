FROM python:3.12-slim AS builder

WORKDIR /app

# Create venv inside /app so it is included in the multi-stage COPY
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

RUN pip install --upgrade pip --quiet

# Cache dependency layer — only rebuilds when pyproject.toml changes
COPY pyproject.toml ./
# Stub packages so pip editable install can resolve the project
RUN mkdir -p agents tools cms graph && \
    touch agents/__init__.py tools/__init__.py cms/__init__.py graph/__init__.py
RUN pip install --no-cache-dir -e .

# Store Playwright Chromium inside /app so it survives the multi-stage COPY
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright
RUN playwright install chromium

# Copy full source and re-install (picks up real packages, skips already-installed deps)
COPY . .
RUN pip install --no-cache-dir -e . --no-deps

FROM python:3.12-slim AS runtime

WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/app/.playwright

# Install system libraries required by Chromium in the slim runtime image
RUN playwright install-deps chromium && \
    rm -rf /var/lib/apt/lists/*
