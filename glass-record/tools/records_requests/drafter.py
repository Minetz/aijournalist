"""
LLM-powered public records request drafter.

Given a story context and jurisdiction, the LLM:
1. Identifies the most impactful records to request (documents, datasets, correspondence)
2. Drafts a complete, jurisdiction-appropriate formal request letter

The output is a list of RecordsRequestDraft objects, each ready to store in Firestore
and present to a journalist for review before submission.
"""
import json

import structlog
from langchain_core.messages import HumanMessage

from agents.shared.gemini import get_llm_with_fallback
from tools.records_requests.registry import get_registry_entry, get_template

log = structlog.get_logger()

_IDENTIFY_PROMPT = """
You are an investigative journalist editor. An article has been published on the following
investigation. Identify specific official records that, if obtained, would most strengthen
the evidence base for future reporting.

Story: {story_title}

Sub-questions investigated:
{sub_questions}

Key entities and claims from the evidence:
{evidence_summary}

Jurisdiction: {jurisdiction_name}
Legal basis for requests: {legal_basis}

Identify at most {max_requests} distinct records requests. For each, specify:
- A brief title for the request
- The specific records sought (as precise as possible: document types, date ranges,
  named programmes, contract numbers, committee names, etc.)
- The body or agency that would hold these records
- Why obtaining them would materially advance the investigation

Return ONLY valid JSON — no markdown:
{{
  "requests": [
    {{
      "title": "Short descriptive title",
      "records_sought": "Precise description of documents sought",
      "holding_body": "Name of agency/body that holds these records",
      "investigative_value": "Why these records matter"
    }}
  ]
}}
""".strip()

_DRAFT_PROMPT = """
You are a specialist in public records and freedom of information law.

Draft a formal records request letter using the template below as a guide.
Replace all placeholder text with specific, accurate content based on the request details.
The letter must be professional, legally precise, and complete — ready to send.

TEMPLATE (use as structural guide only — adapt language to the specific request):
---
{template_text}
---

REQUEST DETAILS:
Title: {title}
Records sought: {records_sought}
Holding body: {holding_body}
Jurisdiction: {jurisdiction_name}
Legal basis: {legal_basis}
Story context (DO NOT reveal unpublished details): {story_title}
Today's date: {today}

Write the complete letter. Use today's date. Address it to {holding_body}.
Return ONLY the letter text — no commentary, no markdown fences.
""".strip()


class RecordsRequestDraft:
    def __init__(
        self,
        title: str,
        records_sought: str,
        holding_body: str,
        investigative_value: str,
        letter_text: str,
        jurisdiction: str,
    ) -> None:
        self.title = title
        self.records_sought = records_sought
        self.holding_body = holding_body
        self.investigative_value = investigative_value
        self.letter_text = letter_text
        self.jurisdiction = jurisdiction

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "records_sought": self.records_sought,
            "holding_body": self.holding_body,
            "investigative_value": self.investigative_value,
            "letter_text": self.letter_text,
            "jurisdiction": self.jurisdiction,
        }


async def draft_records_requests(
    story_title: str,
    sub_questions: list[str],
    evidence_summary: str,
    jurisdiction: str,
    today: str,
    max_requests: int = 2,
) -> list[RecordsRequestDraft]:
    """
    Identify and draft records requests for a published investigation.

    Returns a list of RecordsRequestDraft objects (may be empty if the LLM
    finds no useful records to request for this jurisdiction/story combination).
    """
    entry = get_registry_entry(jurisdiction)
    template_text = get_template(jurisdiction) or ""

    llm = get_llm_with_fallback(temperature=0.1)

    # Step 1: Identify what to request
    identify_prompt = _IDENTIFY_PROMPT.format(
        story_title=story_title,
        sub_questions="\n".join(f"- {q}" for q in sub_questions),
        evidence_summary=evidence_summary[:3_000],
        jurisdiction_name=entry["name"],
        legal_basis=entry["legal_basis"],
        max_requests=max_requests,
    )
    try:
        id_response = await llm.ainvoke([HumanMessage(content=identify_prompt)])
        raw = id_response.content
        if isinstance(raw, list):
            raw = "".join(p["text"] if isinstance(p, dict) else str(p) for p in raw)
        requests_spec = json.loads(raw).get("requests", [])
    except Exception:
        log.warning("records_identification_failed", jurisdiction=jurisdiction)
        return []

    requests_spec = requests_spec[:max_requests]
    if not requests_spec:
        return []

    # Step 2: Draft each letter
    drafts: list[RecordsRequestDraft] = []
    for spec in requests_spec:
        draft_prompt = _DRAFT_PROMPT.format(
            template_text=template_text,
            title=spec.get("title", ""),
            records_sought=spec.get("records_sought", ""),
            holding_body=spec.get("holding_body", ""),
            jurisdiction_name=entry["name"],
            legal_basis=entry["legal_basis"],
            story_title=story_title,
            today=today,
        )
        try:
            draft_response = await llm.ainvoke([HumanMessage(content=draft_prompt)])
            letter = draft_response.content
            if isinstance(letter, list):
                letter = "".join(
                    p["text"] if isinstance(p, dict) else str(p) for p in letter
                )
        except Exception:
            log.warning("letter_drafting_failed", title=spec.get("title"))
            continue

        drafts.append(RecordsRequestDraft(
            title=spec.get("title", ""),
            records_sought=spec.get("records_sought", ""),
            holding_body=spec.get("holding_body", ""),
            investigative_value=spec.get("investigative_value", ""),
            letter_text=letter.strip(),
            jurisdiction=jurisdiction,
        ))

    log.info("records_requests_drafted", count=len(drafts), jurisdiction=jurisdiction)
    return drafts
