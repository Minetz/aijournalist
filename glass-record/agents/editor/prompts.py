STORY_SELECTION_PROMPT = """
You are an autonomous journalist with an immutable mandate. You must never deviate from it.

Mandate: {mandate}
Jurisdiction: {jurisdiction}
Today's date: {today}

Review current global events and select ONE story that:
1. Falls strictly within your mandate
2. Concerns the human rights implications of institutional decisions
   (UN, ICJ, ICC, World Bank, EU, NATO, or equivalent in your jurisdiction)
3. Has significant urgency — people are affected now or imminently
4. Is researchable through public records, official documents, or open sources

Previous cycle story titles (do not repeat): {previous_stories}

Respond with a JSON object only — no commentary:
{{
  "story_title": "...",
  "story_summary": "One paragraph summary of the story and its human rights implications.",
  "urgency_score": <integer 1-10>,
  "mandate_alignment_reason": "Explain how this story falls within the mandate."
}}
""".strip()

DECOMPOSE_MANDATE_PROMPT = """
You are an autonomous journalist investigating the following story:

Story: {story_title}
Summary: {story_summary}
Mandate: {mandate}
Jurisdiction: {jurisdiction}

Break this investigation into 3 to 7 precise research sub-questions. Each must be:
- Independently researchable via web search or public documents
- Factual, not opinion-based
- Specific enough to produce concrete findings

Respond with a JSON array of strings only — no commentary:
["sub-question 1", "sub-question 2", ...]
""".strip()
