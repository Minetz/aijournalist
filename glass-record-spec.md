# THE GLASS RECORD — Build Spec v0.1
> Autonomous AI Journalism Platform · Human Rights Focus · Radical Transparency

---

## What It Is

An autonomous AI journalist that self-selects stories requiring investigation — specifically human rights implications of institutional decisions (UN, ICJ, ICC, World Bank, EU, NATO, etc.). Every action, every dollar, every reasoning step is public. No editorial capture. No advertisers. No human editor to kill a story.

Each "journalist" is a persistent agent with a public web page showing its live evidence locker, legal case tree, activity log, and funding.

---

## Core Principles

- **Glass box by design** — every agent action is logged and public
- **Mandate-locked** — the research question is set at spawn and cannot drift
- **Structurally fearless** — no revenue model that creates editorial conflicts
- **Non-profit cooperative** — compute costs disclosed, surplus returned to commons

---

## Agent Architecture

```
EDITOR AGENT (orchestrator)
├── Autonomously selects story by human rights urgency
├── Breaks mandate into research sub-questions
├── Spawns RESEARCHER sub-agents (parallel)
├── Runs COMPLIANCE check at each cycle
└── Never accepts external editorial direction

RESEARCHER SUB-AGENTS
├── Web search + scraping
├── Public records request automation (jurisdiction-aware)
├── Document ingestion + analysis
├── Legal tree builder
└── Knowledge graph updater

COMPLIANCE AGENT
├── Mandate drift detection
├── Prompt injection awareness
├── Jurisdiction legality check
└── Every decision logged publicly

COMMENT/VERIFICATION AGENT
├── Reads public tips and corrections
├── Cross-checks against evidence locker
├── Zero influence on editorial direction
└── Responses are public
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Google Gemini 1.5 Pro / Flash (via Vertex AI) |
| Agent orchestration | LangGraph |
| Web interaction | Browser-Use (Playwright) |
| Document processing | Docling |
| Knowledge graph | Neo4j |
| Database / state | Cloud Spanner or Firestore |
| Publishing / CMS | Ghost (self-hosted, API-driven) |
| Frontend dashboard | Next.js |
| Search | Google Search API (Programmable Search) |
| Public records requests | Custom jurisdiction registry (template-based) |

---

## Google Cloud Deployment

```
GCP Services
├── Vertex AI          — Gemini model access, agent runtime
├── Cloud Run          — containerized agent workers (scale to zero)
├── Cloud Scheduler    — daily investigation cycle trigger
├── Firestore          — agent state, compliance logs
├── Cloud Storage      — evidence locker (documents, raw files)
├── Pub/Sub            — agent-to-agent messaging
├── Artifact Registry  — Docker images
└── Firebase Hosting   — public journalist web pages (static + CDN)

Deployment model: each journalist = isolated Cloud Run service
Spawning a journalist = deploying a new Cloud Run job with its mandate baked in
```

### Why Cloud Run
- Scales to zero between daily cycles (cost efficient for free credits)
- Each journalist is fully containerized and isolated
- Easy to spawn N journalists in parallel for paid tier

---

## Data Flow

```
Cloud Scheduler (daily trigger)
  → Pub/Sub topic
    → Editor Agent (Cloud Run)
      → Gemini 1.5 Pro: select story / generate sub-questions
      → Researcher Agents (parallel Cloud Run jobs)
          → Browser-Use: web scraping
          → Google Search API: source discovery
          → Docling: document processing
          → Gemini: analysis + legal tree building
      → Compliance Agent: mandate check
      → Firestore: persist all findings + logs
      → Ghost API: publish story
      → Firebase: update public dashboard
```

---

## Public Web Page (per journalist)

Each journalist gets `journalist.glassrecord.org/[slug]`:

- **MANDATE** — immutable, set at spawn
- **ACTIVITY LOG** — every agent action, timestamped
- **EVIDENCE LOCKER** — all documents, sources, credibility scores
- **KNOWLEDGE GRAPH** — live Neo4j visualization
- **LEGAL CASE TREE** — branches, statutes, precedents, strength scores
- **PUBLISHED STORIES** — full investigation output
- **COMPLIANCE LOG** — every compliance decision
- **TIPS** — public submission form, verified by agent, zero editorial influence
- **COST LEDGER** — compute cost per investigation, fully transparent

---

## Tiers

| | Free | Paid |
|---|---|---|
| Journalists | 1 | Unlimited |
| Jurisdictions | 1 | Multi |
| Research cycle | Daily | Configurable |
| Sub-agents | Sequential | Parallel |
| Legal tree | Basic | Full |
| Public records requests | Manual | Automated |
| API access | No | Yes |

---

## MVP Sequence (Claude Code tasks)

1. **Container scaffold** — LangGraph + Gemini + Cloud Run base
2. **Editor Agent** — story selection via Gemini, jurisdiction-aware
3. **Researcher Agent** — web search + Docling + evidence storage in Firestore
4. **Compliance Agent** — mandate drift detection, logged
5. **Legal Tree Builder** — Gemini structured output → tree JSON
6. **Ghost CMS integration** — auto-publish on cycle completion
7. **Public dashboard** — Next.js, reads Firestore in real time
8. **Cloud Scheduler** — wire daily cycle
9. **Spawn API** — create new journalist via REST call

---

## What VCs Would Never Fund (and why this works)

The product is transparency. Transparency destroys the margins that would make this investable. That's the moat. A cooperative ownership model + Google Cloud free credits bootstraps the infrastructure without needing capital that would corrupt the mandate.

The first investigation the platform publishes should be about itself.

---

## Repo Structure (suggested)

```
glass-record/
├── agents/
│   ├── editor/
│   ├── researcher/
│   ├── compliance/
│   └── legal_tree/
├── tools/
│   ├── search/
│   ├── browser/
│   ├── documents/
│   └── records_requests/
├── graph/          (Neo4j schema + queries)
├── cms/            (Ghost integration)
├── dashboard/      (Next.js public pages)
├── infra/          (Terraform for GCP)
└── docker/         (Dockerfiles per agent)
```

---

*Pass this to Claude Code. Start with `agents/editor/` and `infra/`. All LLM calls go through Vertex AI Gemini. Keep every agent stateless — state lives in Firestore.*
