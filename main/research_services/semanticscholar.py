from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .http import HttpClient
from .types import Author, PaperRecord


S2_BASE = "https://api.semanticscholar.org/graph/v1"
S2_DEFAULT_FIELDS = (
    "title,abstract,venue,year,authors,externalIds,url,isOpenAccess,openAccessPdf,"
    "citationCount,referenceCount,fieldsOfStudy"
)


def _headers() -> Dict[str, str]:
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    headers = {"User-Agent": "Lumen/0.2"}
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _to_record(p: Dict[str, Any]) -> Optional[PaperRecord]:
    title = p.get("title") or ""
    if not title:
        return None
    abstract = p.get("abstract") or ""
    venue = p.get("venue")
    year = p.get("year")
    try:
        year = int(year) if year is not None else None
    except Exception:
        year = None
    external = p.get("externalIds") or {}
    doi = external.get("DOI") or external.get("doi")
    arxiv_id = external.get("ArXiv") or external.get("arXiv")
    url = p.get("url")
    is_oa = p.get("isOpenAccess")
    open_pdf = (p.get("openAccessPdf") or {}).get("url")
    fields = p.get("fieldsOfStudy") or []
    citations = p.get("citationCount")
    references = p.get("referenceCount")

    authors_raw = p.get("authors") or []
    authors: List[Author] = []
    for a in authors_raw:
        name = a.get("name")
        if name:
            authors.append(Author(name=name))

    record = PaperRecord(
        source="semanticscholar",
        source_id=str(p.get("paperId")),
        title=title,
        abstract=abstract,
        authors=authors,
        year=year,
        venue=venue,
        doi=doi,
        arxiv_id=arxiv_id,
        url=url,
        open_access_pdf_url=open_pdf if is_oa else None,
        fields_of_study=fields,
        citations_count=citations,
        references_count=references,
        raw=p,
    )
    return record


async def search_semantic_scholar(client: HttpClient, query: str, limit: int = 20, fields: str = S2_DEFAULT_FIELDS) -> List[PaperRecord]:
    url = f"{S2_BASE}/paper/search"
    params: Dict[str, Any] = {"query": query, "limit": limit, "fields": fields}
    data = await client.get_json(url, params=params, headers=_headers())
    papers = data.get("data") or []
    results: List[PaperRecord] = []
    for p in papers:
        rec = _to_record(p)
        if rec:
            results.append(rec)
    return results


async def fetch_semantic_scholar_by_id(client: HttpClient, paper_id: str, fields: str = S2_DEFAULT_FIELDS) -> Optional[PaperRecord]:
    url = f"{S2_BASE}/paper/{paper_id}"
    params: Dict[str, Any] = {"fields": fields}
    p = await client.get_json(url, params=params, headers=_headers())
    return _to_record(p)


