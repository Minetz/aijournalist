"""
Jurisdiction registry for public records request templates.
Maps jurisdiction codes to template metadata and filing instructions.
"""

REGISTRY: dict[str, dict] = {
    "US_FEDERAL": {
        "name": "United States Federal (FOIA)",
        "template": "us_federal.txt",
        "filing_url": "https://www.foia.gov/",
        "response_days": 20,
        "automated": False,
    },
    "EU": {
        "name": "European Union (Access to Documents)",
        "template": "eu_gdpr.txt",
        "filing_url": "https://www.asktheeu.org/",
        "response_days": 15,
        "automated": False,
    },
}


def get_template(jurisdiction: str) -> str | None:
    entry = REGISTRY.get(jurisdiction.upper())
    if not entry:
        return None
    template_path = __file__.replace("registry.py", f"templates/{entry['template']}")
    try:
        with open(template_path) as f:
            return f.read()
    except FileNotFoundError:
        return None
