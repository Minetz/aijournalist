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

WRITING RULES:
- Write in clear, factual journalistic prose. No opinion, no speculation.
- Every claim must be traceable to the evidence provided.
- Lead paragraph: who, what, when, where, why — most important fact first.
- Include relevant statute or treaty references where the legal tree supports them.
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
