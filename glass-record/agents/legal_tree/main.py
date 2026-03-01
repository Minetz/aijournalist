# Legal Tree Builder — stub for MVP 5
# Will build structured legal case trees from evidence using Gemini structured output.
from fastapi import FastAPI

app = FastAPI(title="glass-record-legal-tree", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
