# The Glass Record — Implementation Plan

> Initial development setup and first three MVP features

---

## 1. Repository and Project Structure

```
/home/user/aijournalist/
└── glass-record/
    ├── pyproject.toml               # Root project config (uv workspace root)
    ├── uv.lock                      # Pinned lockfile
    ├── .python-version              # "3.12"
    ├── .env.example                 # All required env vars with dummy values
    ├── .gitignore
    ├── docker-compose.yml           # Local dev: Neo4j + Firestore emulator + Ghost
    │
    ├── agents/
    │   ├── __init__.py
    │   ├── shared/
    │   │   ├── __init__.py
    │   │   ├── base_agent.py        # Abstract BaseAgent, Firestore log helpers
    │   │   ├── state.py             # Shared LangGraph TypedDicts
    │   │   └── gemini.py            # Gemini client factory (Vertex AI)
    │   ├── editor/
    │   │   ├── __init__.py
    │   │   ├── graph.py             # Editor StateGraph definition
    │   │   ├── nodes.py             # select_story, decompose_mandate, spawn_researchers
    │   │   ├── prompts.py           # Prompt templates for Gemini calls
    │   │   └── main.py             # Cloud Run entry point (FastAPI)
    │   ├── researcher/
    │   │   ├── __init__.py
    │   │   ├── graph.py             # Researcher StateGraph
    │   │   ├── nodes.py             # search, scrape, ingest_doc, store_evidence
    │   │   ├── prompts.py
    │   │   └── main.py
    │   ├── compliance/
    │   │   ├── __init__.py
    │   │   ├── graph.py
    │   │   ├── nodes.py             # check_mandate_drift, log_decision
    │   │   ├── prompts.py
    │   │   └── main.py
    │   └── legal_tree/
    │       ├── __init__.py
    │       ├── graph.py
    │       ├── nodes.py             # build_tree (structured Gemini output)
    │       ├── schemas.py           # Pydantic models for tree JSON
    │       └── main.py
    │
    ├── tools/
    │   ├── __init__.py
    │   ├── search/
    │   │   ├── __init__.py
    │   │   └── google_search.py     # Programmable Search Engine wrapper
    │   ├── browser/
    │   │   ├── __init__.py
    │   │   └── scraper.py           # Playwright wrapper (browser-use for interactive)
    │   ├── documents/
    │   │   ├── __init__.py
    │   │   └── docling_ingest.py    # Docling DocumentConverter wrapper
    │   └── records_requests/
    │       ├── __init__.py
    │       ├── registry.py          # Jurisdiction registry (JSON-backed)
    │       └── templates/
    │           ├── us_federal.txt
    │           └── eu_gdpr.txt
    │
    ├── graph/
    │   ├── schema.cypher            # Neo4j node/relationship definitions
    │   ├── queries.py               # Cypher query library
    │   └── client.py               # Async Neo4j driver factory
    │
    ├── cms/
    │   ├── __init__.py
    │   └── ghost.py                 # Ghost Admin API client
    │
    ├── dashboard/                   # Next.js app (separate npm workspace)
    │   ├── package.json
    │   ├── next.config.js
    │   └── src/
    │       ├── app/
    │       │   ├── layout.tsx
    │       │   ├── page.tsx         # Landing / journalist index
    │       │   └── [slug]/
    │       │       └── page.tsx     # Per-journalist live page
    │       └── lib/
    │           └── firestore.ts     # Firebase JS SDK, real-time listeners
    │
    ├── infra/
    │   ├── main.tf
    │   ├── variables.tf
    │   ├── outputs.tf
    │   ├── modules/
    │   │   ├── cloud_run/
    │   │   ├── pubsub/
    │   │   ├── scheduler/
    │   │   └── artifact_registry/
    │   └── envs/
    │       ├── dev.tfvars
    │       └── prod.tfvars
    │
    └── docker/
        ├── base.Dockerfile          # Shared Python 3.12 + uv + Playwright layer
        ├── editor.Dockerfile
        ├── researcher.Dockerfile
        ├── compliance.Dockerfile
        └── legal_tree.Dockerfile
```

---

## 2. Python Environment and Dependency Setup

### Toolchain: uv

Use `uv` as the package manager. Install:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Initialise the project:

```bash
cd /home/user/aijournalist/glass-record
uv init --python 3.12
```

### `pyproject.toml`

```toml
[project]
name = "glass-record"
version = "0.1.0"
description = "Autonomous AI journalism platform"
requires-python = ">=3.12"

dependencies = [
    # LLM & orchestration
    "langgraph>=0.2",
    "langchain-core>=0.3",
    "langchain-google-genai>=4.0",
    "google-genai>=1.0",

    # GCP / Firestore
    "google-cloud-firestore>=2.23",
    "google-cloud-storage>=2.16",
    "google-cloud-pubsub>=2.21",

    # Web browsing / search
    "browser-use>=0.1",
    "playwright>=1.44",

    # Document processing
    "docling>=2.70",

    # Knowledge graph
    "neo4j>=5.28",

    # HTTP / serving
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",

    # Data / validation
    "pydantic>=2.7",
    "pydantic-settings>=2.3",

    # Utilities
    "tenacity>=8.3",
    "structlog>=24.1",
    "python-dotenv>=1.0",
    "pyjwt>=2.8",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.14",
    "ruff>=0.4",
    "mypy>=1.10",
    "pre-commit>=3.7",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

After editing:

```bash
uv sync
uv run playwright install chromium
```

### `.env.example`

```bash
# Google Cloud
GOOGLE_CLOUD_PROJECT=glass-record-dev
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Gemini
GEMINI_MODEL=gemini-1.5-pro-002

# Neo4j (local: bolt://localhost:7687, prod: Aura URI)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=devpassword

# Firestore emulator (local only)
FIRESTORE_EMULATOR_HOST=localhost:8080
FIRESTORE_PROJECT_ID=glass-record-dev

# Ghost CMS
GHOST_ADMIN_URL=http://localhost:2368
GHOST_ADMIN_API_KEY=<id>:<secret>

# Google Search
GOOGLE_SEARCH_API_KEY=...
GOOGLE_SEARCH_ENGINE_ID=...

# Cloud Storage (evidence locker)
GCS_EVIDENCE_BUCKET=glass-record-evidence-dev
```

---

## 3. Local Development Environment

### `docker-compose.yml`

```yaml
version: "3.9"

services:

  neo4j:
    image: neo4j:5.20-community
    ports:
      - "7474:7474"   # Browser UI
      - "7687:7687"   # Bolt
    environment:
      NEO4J_AUTH: neo4j/devpassword
      NEO4J_PLUGINS: '["apoc"]'
    volumes:
      - neo4j_data:/data
      - ./graph/schema.cypher:/docker-entrypoint-initdb.d/schema.cypher
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "devpassword", "RETURN 1"]
      interval: 10s
      retries: 5

  firestore:
    image: mtlynch/firestore-emulator:latest
    ports:
      - "8080:8080"
    environment:
      FIRESTORE_PROJECT_ID: glass-record-dev
      PORT: 8080
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/"]
      interval: 10s
      retries: 5

  ghost_db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ghostpassword
      MYSQL_DATABASE: ghost
    volumes:
      - ghost_db_data:/var/lib/mysql

  ghost:
    image: ghost:5-alpine
    ports:
      - "2368:2368"
    environment:
      NODE_ENV: development
      database__client: mysql
      database__connection__host: ghost_db
      database__connection__user: root
      database__connection__password: ghostpassword
      database__connection__database: ghost
      url: http://localhost:2368
    depends_on:
      - ghost_db
    volumes:
      - ghost_data:/var/lib/ghost/content

volumes:
  neo4j_data:
  ghost_db_data:
  ghost_data:
```

Start with: `docker compose up -d`

The `google-cloud-firestore` Python client automatically detects `FIRESTORE_EMULATOR_HOST` and redirects to the local emulator.

Boot sequence:
1. `docker compose up -d`
2. Wait for healthchecks (Neo4j ~20s, Ghost ~30s for DB migration)
3. Apply Neo4j schema: `uv run cypher-shell -f graph/schema.cypher`
4. Register Ghost custom integration at `http://localhost:2368/ghost`, copy Admin API key to `.env`
5. `uv run uvicorn agents.editor.main:app --reload --port 8000`

---

## 4. First Three MVP Features

### MVP 1 — Container Scaffold

**Goal:** Working Cloud Run-compatible container that boots FastAPI, loads Gemini via Vertex AI, and accepts a JSON trigger payload.

#### `agents/shared/gemini.py`

```python
from functools import lru_cache
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    gemini_model: str = "gemini-1.5-pro-002"
    google_cloud_project: str = "glass-record-dev"
    google_genai_use_vertexai: bool = True

@lru_cache
def get_settings() -> Settings:
    return Settings()

@lru_cache
def get_llm(temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    s = get_settings()
    return ChatGoogleGenerativeAI(
        model=s.gemini_model,
        temperature=temperature,
        project=s.google_cloud_project,
        vertexai=s.google_genai_use_vertexai,
    )
```

#### `agents/shared/state.py`

```python
import operator
from typing import Annotated, TypedDict
from pydantic import BaseModel
from langgraph.graph.message import add_messages

class JournalistConfig(BaseModel):
    journalist_id: str
    mandate: str          # immutable, set at spawn
    jurisdiction: str     # e.g. "UN", "EU", "US_FEDERAL"
    tier: str = "free"    # "free" | "paid"

class EditorState(TypedDict):
    config: JournalistConfig
    selected_story: str
    sub_questions: list[str]
    researcher_results: Annotated[list[dict], operator.add]
    compliance_passed: bool
    cycle_id: str
    messages: Annotated[list, add_messages]

class ResearcherState(TypedDict):
    config: JournalistConfig
    sub_question: str
    search_results: list[dict]
    scraped_content: list[dict]
    ingested_docs: list[dict]
    evidence_ids: list[str]
    messages: Annotated[list, add_messages]
```

#### `agents/editor/main.py` (Cloud Run entry point pattern)

```python
import asyncio, uuid, structlog
from fastapi import FastAPI, HTTPException
from agents.editor.graph import build_graph
from agents.shared.state import JournalistConfig, EditorState

app = FastAPI(title="glass-record-editor")
log = structlog.get_logger()

@app.post("/run")
async def run_cycle(config: JournalistConfig):
    cycle_id = str(uuid.uuid4())
    log.info("cycle_start", journalist_id=config.journalist_id, cycle_id=cycle_id)
    graph = build_graph()
    initial_state = EditorState(
        config=config,
        selected_story="",
        sub_questions=[],
        researcher_results=[],
        compliance_passed=False,
        cycle_id=cycle_id,
        messages=[],
    )
    try:
        final_state = await graph.ainvoke(initial_state)
        return {"status": "ok", "cycle_id": cycle_id, "story": final_state["selected_story"]}
    except Exception as exc:
        log.error("cycle_failed", error=str(exc), cycle_id=cycle_id)
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/health")
def health():
    return {"status": "ok"}
```

#### `docker/base.Dockerfile`

```dockerfile
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

RUN /app/.venv/bin/playwright install chromium --with-deps

COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
```

Agent-specific Dockerfile example (`docker/editor.Dockerfile`):

```dockerfile
FROM glass-record/base:latest
ENV PORT=8080
CMD ["uvicorn", "agents.editor.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

### MVP 2 — Editor Agent

**Goal:** LangGraph graph that selects a story via Gemini, decomposes it into sub-questions, logs to Firestore, and fans out to researcher workers.

#### `agents/shared/base_agent.py`

```python
import datetime, structlog
from google.cloud import firestore

log = structlog.get_logger()

async def log_action(
    db: firestore.AsyncClient,
    journalist_id: str,
    cycle_id: str,
    action: str,
    data: dict,
) -> None:
    entry = {
        "journalist_id": journalist_id,
        "cycle_id": cycle_id,
        "action": action,
        "data": data,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
    await (
        db.collection("journalists")
          .document(journalist_id)
          .collection("activity_log")
          .add(entry)
    )
    log.info("action_logged", action=action, journalist_id=journalist_id)
```

#### `agents/editor/prompts.py`

```python
STORY_SELECTION_PROMPT = """
You are an autonomous journalist. Your immutable mandate is:
{mandate}

Your jurisdiction is: {jurisdiction}
Today's date: {today}

Select ONE story with significant human rights urgency that falls within your mandate.

Respond with JSON:
{{
  "story_title": "...",
  "story_summary": "...",
  "urgency_score": <1-10>,
  "mandate_alignment_reason": "..."
}}
"""

DECOMPOSE_MANDATE_PROMPT = """
You are an autonomous journalist investigating: "{story_title}"

Break this into 3-7 precise, independently researchable sub-questions traceable
to public records or documents.

Respond as a JSON array of strings.
"""
```

#### `agents/editor/nodes.py`

```python
import json, datetime
from langgraph.types import Send
from langchain_core.messages import HumanMessage
from agents.shared.gemini import get_llm
from agents.shared.base_agent import log_action
from agents.shared.state import EditorState, ResearcherState
from agents.editor.prompts import STORY_SELECTION_PROMPT, DECOMPOSE_MANDATE_PROMPT
from google.cloud import firestore

async def select_story(state: EditorState) -> dict:
    llm = get_llm(temperature=0.3)
    prompt = STORY_SELECTION_PROMPT.format(
        mandate=state["config"].mandate,
        jurisdiction=state["config"].jurisdiction,
        today=datetime.date.today().isoformat(),
    )
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    story_data = json.loads(response.content)
    db = firestore.AsyncClient()
    await log_action(db, state["config"].journalist_id, state["cycle_id"],
                     "story_selected", story_data)
    return {"selected_story": story_data["story_title"]}

async def decompose_mandate(state: EditorState) -> dict:
    llm = get_llm(temperature=0.1)
    prompt = DECOMPOSE_MANDATE_PROMPT.format(story_title=state["selected_story"])
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    sub_questions = json.loads(response.content)
    db = firestore.AsyncClient()
    await log_action(db, state["config"].journalist_id, state["cycle_id"],
                     "mandate_decomposed", {"sub_questions": sub_questions})
    return {"sub_questions": sub_questions}

def spawn_researchers(state: EditorState) -> list[Send]:
    """Fan-out: one researcher worker per sub-question."""
    return [
        Send("researcher_worker", ResearcherState(
            config=state["config"],
            sub_question=q,
            search_results=[],
            scraped_content=[],
            ingested_docs=[],
            evidence_ids=[],
            messages=[],
        ))
        for q in state["sub_questions"]
    ]

async def synthesise_results(state: EditorState) -> dict:
    return {"compliance_passed": True}  # wired fully in MVP 4
```

#### `agents/editor/graph.py`

```python
from langgraph.graph import StateGraph, START, END
from agents.shared.state import EditorState
from agents.editor.nodes import select_story, decompose_mandate, spawn_researchers, synthesise_results
from agents.researcher.graph import build_researcher_graph

def build_graph() -> StateGraph:
    researcher_graph = build_researcher_graph()

    g = StateGraph(EditorState)
    g.add_node("select_story", select_story)
    g.add_node("decompose_mandate", decompose_mandate)
    g.add_node("researcher_worker", researcher_graph)
    g.add_node("synthesise_results", synthesise_results)

    g.add_edge(START, "select_story")
    g.add_edge("select_story", "decompose_mandate")
    g.add_conditional_edges("decompose_mandate", spawn_researchers, ["researcher_worker"])
    g.add_edge("researcher_worker", "synthesise_results")
    g.add_edge("synthesise_results", END)

    return g.compile()
```

**Local vs Cloud Run dispatch:** Use `RESEARCHER_MODE=local` (default) to run researchers as LangGraph subgraphs in the same process. Set `RESEARCHER_MODE=pubsub` in Cloud Run to publish one Pub/Sub message per sub-question instead.

---

### MVP 3 — Researcher Agent

**Goal:** For a given sub-question, run web search, scrape top results with Playwright, ingest documents with Docling, and store structured evidence in Firestore with raw files in Cloud Storage.

#### `tools/search/google_search.py`

```python
import httpx
from pydantic_settings import BaseSettings

class SearchSettings(BaseSettings):
    google_search_api_key: str
    google_search_engine_id: str

async def web_search(query: str, num: int = 10) -> list[dict]:
    s = SearchSettings()
    params = {
        "key": s.google_search_api_key,
        "cx": s.google_search_engine_id,
        "q": query,
        "num": num,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://www.googleapis.com/customsearch/v1", params=params)
        r.raise_for_status()
    items = r.json().get("items", [])
    return [{"title": i["title"], "url": i["link"], "snippet": i["snippet"]} for i in items]
```

#### `tools/browser/scraper.py`

```python
from playwright.async_api import async_playwright

async def scrape_url(url: str) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (compatible; GlassRecord/1.0)"
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=20_000)
            title = await page.title()
            body_text = await page.inner_text("body")
            return {"url": url, "title": title, "text": body_text[:50_000], "error": None}
        except Exception as e:
            return {"url": url, "title": "", "text": "", "error": str(e)}
        finally:
            await browser.close()
```

#### `tools/documents/docling_ingest.py`

```python
from docling.document_converter import DocumentConverter
from pathlib import Path

_converter = DocumentConverter()  # module-level singleton

def ingest_document(source: str | Path) -> dict:
    result = _converter.convert(str(source))
    doc = result.document
    return {
        "source": str(source),
        "markdown": doc.export_to_markdown(),
        "metadata": {
            "pages": getattr(doc, "num_pages", None),
            "title": getattr(doc, "title", None),
        },
    }
```

#### `agents/researcher/nodes.py`

```python
import hashlib, json, datetime
from google.cloud import firestore, storage
from agents.shared.state import ResearcherState
from agents.shared.base_agent import log_action
from agents.shared.gemini import get_llm
from tools.search.google_search import web_search
from tools.browser.scraper import scrape_url
from pydantic_settings import BaseSettings
from langchain_core.messages import HumanMessage

class StorageSettings(BaseSettings):
    gcs_evidence_bucket: str = "glass-record-evidence-dev"
    google_cloud_project: str = "glass-record-dev"

async def search_node(state: ResearcherState) -> dict:
    results = await web_search(state["sub_question"])
    db = firestore.AsyncClient()
    await log_action(db, state["config"].journalist_id, state["sub_question"][:40],
                     "search_complete", {"query": state["sub_question"], "result_count": len(results)})
    return {"search_results": results}

async def scrape_node(state: ResearcherState) -> dict:
    import asyncio
    tasks = [scrape_url(r["url"]) for r in state["search_results"][:5]]
    scraped = await asyncio.gather(*tasks)
    return {"scraped_content": [s for s in scraped if not s["error"]]}

async def analyse_and_store_evidence(state: ResearcherState) -> dict:
    llm = get_llm(temperature=0.0)
    ss = StorageSettings()
    db = firestore.AsyncClient()
    gcs = storage.Client(project=ss.google_cloud_project)
    bucket = gcs.bucket(ss.gcs_evidence_bucket)
    evidence_ids = []
    journalist_id = state["config"].journalist_id

    for page in state["scraped_content"]:
        prompt = f"""
Sub-question: {state['sub_question']}
Source URL: {page['url']}
Content:
{page['text'][:8000]}

Extract factual claims directly relevant to the sub-question.
Respond as JSON:
{{
  "relevant": true/false,
  "claims": ["..."],
  "credibility_notes": "...",
  "credibility_score": <0.0-1.0>
}}
"""
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        try:
            analysis = json.loads(response.content)
        except json.JSONDecodeError:
            continue

        if not analysis.get("relevant", False):
            continue

        evidence_id = hashlib.sha256(page["url"].encode()).hexdigest()[:16]

        blob = bucket.blob(f"{journalist_id}/evidence/{evidence_id}.txt")
        blob.upload_from_string(page["text"], content_type="text/plain")

        evidence_doc = {
            "evidence_id": evidence_id,
            "journalist_id": journalist_id,
            "sub_question": state["sub_question"],
            "source_url": page["url"],
            "source_title": page["title"],
            "claims": analysis.get("claims", []),
            "credibility_score": analysis.get("credibility_score", 0.5),
            "credibility_notes": analysis.get("credibility_notes", ""),
            "gcs_path": f"{journalist_id}/evidence/{evidence_id}.txt",
            "collected_at": datetime.datetime.utcnow().isoformat(),
        }
        await (
            db.collection("journalists")
              .document(journalist_id)
              .collection("evidence_locker")
              .document(evidence_id)
              .set(evidence_doc)
        )
        evidence_ids.append(evidence_id)

    await log_action(db, journalist_id, state["sub_question"][:40],
                     "evidence_stored", {"count": len(evidence_ids)})
    return {"evidence_ids": evidence_ids}
```

#### `agents/researcher/graph.py`

```python
from langgraph.graph import StateGraph, START, END
from agents.shared.state import ResearcherState
from agents.researcher.nodes import search_node, scrape_node, analyse_and_store_evidence

def build_researcher_graph() -> StateGraph:
    g = StateGraph(ResearcherState)
    g.add_node("search", search_node)
    g.add_node("scrape", scrape_node)
    g.add_node("analyse_store", analyse_and_store_evidence)

    g.add_edge(START, "search")
    g.add_edge("search", "scrape")
    g.add_edge("scrape", "analyse_store")
    g.add_edge("analyse_store", END)

    return g.compile()
```

---

## 5. Key Design Decisions

### 5.1 State Lives in Firestore, Not LangGraph Checkpoints

All agents are stateless between Cloud Run invocations. Every meaningful state mutation is written to Firestore immediately. This means:
- Any Cloud Run instance can be killed and the investigation resumes from Firestore
- The public dashboard can read live state without an additional API layer
- Compliance auditing is a Firestore query, not a graph replay

**Firestore schema:**

```
/journalists/{journalist_id}/
    mandate               (immutable string, set at spawn)
    jurisdiction
    created_at
    tier
    /activity_log/{log_id}        action, data, timestamp
    /evidence_locker/{evidence_id} source_url, claims[], credibility_score, gcs_path
    /compliance_log/{log_id}       check_type, passed, reasoning, timestamp
    /stories/{story_id}            title, ghost_post_id, published_at, cycle_id
```

### 5.2 Mandate Immutability

`JournalistConfig.mandate` is written once to Firestore at spawn and never updated. The Compliance Agent (MVP 4) always reads the original mandate from Firestore — not from the request payload — to prevent prompt injection from overwriting it.

### 5.3 Structured Gemini Output via Pydantic

For JSON-requiring nodes, use `llm.with_structured_output(PydanticModel)` rather than `json.loads`:

```python
from pydantic import BaseModel

class StorySelection(BaseModel):
    story_title: str
    story_summary: str
    urgency_score: int
    mandate_alignment_reason: str

structured_llm = get_llm().with_structured_output(StorySelection)
story = await structured_llm.ainvoke([HumanMessage(content=prompt)])
# story is a StorySelection instance, fully validated
```

### 5.4 Neo4j Schema (`graph/schema.cypher`)

```cypher
CREATE CONSTRAINT journalist_id_unique IF NOT EXISTS
  FOR (j:Journalist) REQUIRE j.journalist_id IS UNIQUE;

CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
  FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE;

// Node labels: Journalist, Story, Entity, Evidence, Claim
// Entity types: PERSON | ORG | LOCATION | STATUTE
// Relationships:
// (:Journalist)-[:INVESTIGATED]->(:Story)
// (:Story)-[:SUPPORTED_BY]->(:Evidence)
// (:Evidence)-[:CONTAINS]->(:Claim)
// (:Claim)-[:MENTIONS]->(:Entity)
// (:Entity)-[:RELATED_TO]->(:Entity)
```

### 5.5 Ghost CMS Interface (`cms/ghost.py`)

```python
import jwt, time, httpx
from pydantic_settings import BaseSettings

class GhostSettings(BaseSettings):
    ghost_admin_url: str
    ghost_admin_api_key: str  # format: "id:secret"

class GhostClient:
    def __init__(self):
        s = GhostSettings()
        self.base_url = s.ghost_admin_url.rstrip("/") + "/ghost/api/admin"
        key_id, key_secret = s.ghost_admin_api_key.split(":")
        self._key_id = key_id
        self._key_secret = bytes.fromhex(key_secret)

    def _make_token(self) -> str:
        iat = int(time.time())
        payload = {"iat": iat, "exp": iat + 300, "aud": "/admin/"}
        return jwt.encode(payload, self._key_secret, algorithm="HS256",
                          headers={"kid": self._key_id})

    async def create_post(self, title: str, html: str,
                          status: str = "published",
                          tags: list[str] | None = None) -> dict:
        headers = {"Authorization": f"Ghost {self._make_token()}"}
        payload = {"posts": [{"title": title, "html": html, "status": status,
                               "tags": [{"name": t} for t in (tags or [])]}]}
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{self.base_url}/posts/", json=payload, headers=headers)
            r.raise_for_status()
        return r.json()["posts"][0]
```

---

## 6. Build Sequence

| Step | What | Key files |
|------|------|-----------|
| 1 | `pyproject.toml`, `.env.example`, `docker-compose.yml` | project root |
| 2 | `agents/shared/` — Gemini factory, Firestore logger, TypedDicts | `shared/` |
| 3 | `docker/base.Dockerfile` — verify build and uvicorn start | `docker/` |
| 4 | `agents/editor/` — all nodes + graph + main.py | `agents/editor/` |
| 5 | `tools/search/`, `tools/browser/`, `tools/documents/` | `tools/` |
| 6 | `agents/researcher/` — all nodes + graph + main.py | `agents/researcher/` |
| 7 | Integration test: POST to editor, verify evidence in Firestore emulator | `tests/integration/` |
| 8 | `agents/compliance/`, `agents/legal_tree/` | MVPs 4 & 5 |
| 9 | `cms/ghost.py` + Ghost integration | MVP 6 |
| 10 | `dashboard/` Next.js | MVP 7 |
| 11 | `infra/` Terraform | MVPs 8 & 9 |

### Testing

```
tests/
├── unit/
│   ├── test_gemini_mock.py
│   ├── test_evidence_storage.py
│   └── test_search.py
├── integration/
│   ├── test_editor_graph.py
│   └── test_researcher_graph.py
└── conftest.py
```

Run with:

```bash
FIRESTORE_EMULATOR_HOST=localhost:8080 uv run pytest tests/ -v
```
