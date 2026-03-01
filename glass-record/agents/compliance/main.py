# Compliance Agent — stub for MVP 4
# Will implement mandate drift detection and prompt injection awareness.
from fastapi import FastAPI

app = FastAPI(title="glass-record-compliance", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
