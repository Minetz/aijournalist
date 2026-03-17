TIMELINE_EXTRACTION_PROMPT = """
You are an investigative journalist's research assistant. Given a set of evidence claims,
extract every discrete, dateable event mentioned and return them as a structured timeline.

EVIDENCE CLAIMS (from evidence_id → claims):
{evidence_claims}

Return ONLY valid JSON — no markdown, no commentary:
{{
  "events": [
    {{
      "event_date": "YYYY-MM-DD or YYYY-MM or YYYY (best approximation from the text)",
      "description": "One-sentence description of what happened",
      "entities": ["Entity Name 1", "Entity Name 2"],
      "evidence_id": "the evidence_id this event came from",
      "source_url": "the source URL for this event"
    }}
  ]
}}

Rules:
- Only include events with an identifiable date (year at minimum). Skip vague references.
- Keep descriptions factual and concise (max 200 chars).
- Multiple events can reference the same evidence_id.
- If no dateable events are found, return {{"events": []}}.
""".strip()

STORY_SYNTHESIS_PROMPT = """
You are an autonomous investigative journalist. Write a complete news article based on the
evidence and legal analysis gathered during this investigation.

STORY TITLE: {story_title}
MANDATE: {mandate}
JURISDICTION: {jurisdiction}

EVIDENCE SUMMARY (ordered by credibility):
{evidence_summary}

LEGAL CASE TREE SUMMARY:
Overall strength: {legal_strength}
{legal_summary}

{contradictions_section}

WRITING RULES:
- Write in clear, factual journalistic prose. No opinion, no speculation.
- Every claim must be traceable to the evidence provided.
- Lead paragraph: who, what, when, where, why — most important fact first.
- Include relevant statute or treaty references where the legal tree supports them.
- If contradictions are listed above, include a "Disputed Claims" section in the article
  that names each contradiction and the resolution suggestion.
- End with a section titled "What We Don't Know Yet" listing gaps in the evidence.
- Do not name individuals as perpetrators without direct evidentiary support.
- Approximate length: 600–1000 words.

FORMAT: Return a JSON object with:
{{
  "headline": "The article headline",
  "standfirst": "One sentence summary for the article subtitle",
  "body_html": "<p>Full article body as valid HTML paragraphs...</p>",
  "tags": ["list", "of", "relevant", "tags"]
}}
""".strip()
