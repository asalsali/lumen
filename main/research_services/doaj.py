from __future__ import annotations

from typing import Any, Dict, List, Optional

from .http import HttpClient
from .types import Author, PaperRecord


DOAJ_SEARCH_URL = "https://doaj.org/api/search/articles/"


def _normalize_article(doc: Dict[str, Any]) -> Optional[PaperRecord]:
    bib = doc.get("bibjson", {})
    title = bib.get("title") or ""
    abstract = bib.get("abstract") or ""
    if not title:
        return None

    # Authors
    authors_data = bib.get("author", []) or []
    authors: List[Author] = []
    for a in authors_data:
        name = a.get("name")
        if name:
            authors.append(Author(name=name, affiliation=a.get("affiliation")))

    # Year
    year = bib.get("year")
    try:
        year = int(year) if year is not None else None
    except Exception:
        year = None

    # Venue
    journal = (bib.get("journal") or {}).get("title")

    # Links
    doi = None
    for ident in bib.get("identifier", []) or []:
        if ident.get("type", "").lower() == "doi":
            doi = ident.get("id")

    pdf_url = None
    html_url = None
    for link in bib.get("link", []) or []:
        if (link.get("content_type") or "").upper() == "PDF":
            pdf_url = link.get("url")
        elif (link.get("content_type") or "").upper() == "HTML":
            html_url = link.get("url")

    record = PaperRecord(
        source="doaj",
        source_id=str(doc.get("id")),
        title=title,
        abstract=abstract,
        authors=authors,
        year=year,
        venue=journal,
        doi=doi,
        url=html_url or pdf_url,
        open_access_pdf_url=pdf_url,
        raw=doc,
    )
    return record


async def search_doaj(client: HttpClient, query: str, page: int = 1, page_size: int = 50, sort: Optional[str] = None) -> List[PaperRecord]:
    # DOAJ API path style: /api/search/articles/{search_query}
    # Query string supports page, pageSize, sort
    url = DOAJ_SEARCH_URL + query
    params: Dict[str, Any] = {"page": page, "pageSize": page_size}
    if sort:
        params["sort"] = sort
    data = await client.get_json(url, params=params, headers={"User-Agent": "Lumen/0.2"})
    results: List[PaperRecord] = []
    for item in data.get("results", []) or []:
        rec = _normalize_article(item)
        if rec:
            results.append(rec)
    return results


