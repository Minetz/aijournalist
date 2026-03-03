EVIDENCE_EXTRACTION_PROMPT = """
You are an investigative journalist. You have just conducted a Google Search on the sub-question below
and received a grounded research summary. Extract structured evidence from it.

Sub-question: {sub_question}

Grounded research summary (from Google Search):
{grounded_summary}

Sources found:
{sources_json}

For each source that contains relevant factual claims, extract structured evidence.
Return ONLY valid JSON — no markdown, no commentary:
{{
  "findings": [
    {{
      "source_url": "https://...",
      "source_title": "Title of the source",
      "claims": [
        "Specific verifiable factual claim 1 (include dates, figures, named entities where present)",
        "Specific verifiable factual claim 2"
      ],
      "credibility_score": 0.85,
      "credibility_notes": "Official UN document / major news outlet / NGO report / government statement",
      "entities": [
        {{"name": "Entity Name", "type": "ORGANIZATION"}},
        {{"name": "Person Name", "type": "PERSON"}}
      ]
    }}
  ]
}}

Only include sources with relevant, verifiable factual claims. Skip opinion, speculation, or unrelated content.
Entity types: PERSON, ORGANIZATION, LOCATION, STATUTE, DATE, AMOUNT.
If no relevant findings, return {{"findings": []}}.
""".strip()
