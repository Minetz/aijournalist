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
        "legal_basis": "Freedom of Information Act, 5 U.S.C. § 552",
        "automated": False,
    },
    "EU": {
        "name": "European Union (Access to Documents)",
        "template": "eu_gdpr.txt",
        "filing_url": "https://www.asktheeu.org/",
        "response_days": 15,
        "legal_basis": "Regulation (EC) No 1049/2001",
        "automated": False,
    },
    "UN": {
        "name": "United Nations (Access to Official Documents)",
        "template": "un.txt",
        "filing_url": "https://documents.un.org/",
        "response_days": 20,
        "legal_basis": "UN Secretary-General's Bulletin ST/SGB/2007/6",
        "automated": False,
    },
}

# Fallback for unknown jurisdictions — uses US FOIA structure as a baseline
_FALLBACK = {
    "name": "Generic Public Records Request",
    "template": "us_federal.txt",
    "filing_url": "",
    "response_days": 20,
    "legal_basis": "Applicable freedom of information legislation",
    "automated": False,
}


def get_registry_entry(jurisdiction: str) -> dict:
    return REGISTRY.get(jurisdiction.upper(), _FALLBACK)


def get_template(jurisdiction: str) -> str | None:
    entry = get_registry_entry(jurisdiction)
    template_path = __file__.replace("registry.py", f"templates/{entry['template']}")
    try:
        with open(template_path) as f:
            return f.read()
    except FileNotFoundError:
        return None
