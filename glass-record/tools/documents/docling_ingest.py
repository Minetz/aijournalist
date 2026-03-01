from functools import lru_cache
from pathlib import Path

import structlog

log = structlog.get_logger()


@lru_cache(maxsize=1)
def _get_converter():
    # Import here so the module can be imported without docling installed in test envs
    from docling.document_converter import DocumentConverter
    return DocumentConverter()


def ingest_document(source: str | Path) -> dict:
    """
    Convert a PDF, DOCX, or HTML file (local path or URL) to markdown.
    Returns {source, markdown, metadata}.
    """
    converter = _get_converter()
    result = converter.convert(str(source))
    doc = result.document
    markdown = doc.export_to_markdown()
    metadata = {
        "pages": getattr(doc, "num_pages", None),
        "title": getattr(doc, "title", None),
    }
    log.info("document_ingested", source=str(source), pages=metadata["pages"])
    return {"source": str(source), "markdown": markdown, "metadata": metadata}
