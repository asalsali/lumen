from __future__ import annotations

from typing import Any, Dict, List, Optional

from .http import HttpClient
from .types import Author, PaperRecord


OPENALEX_BASE = "https://api.openalex.org"


def _to_record(work: Dict[str, Any]) -> Optional[PaperRecord]:
    title = work.get("title") or work.get("display_name") or ""
    if not title:
        return None

    abstract = ""
    if isinstance(work.get("abstract_inverted_index"), dict):
        # Reconstruct from inverted index (OpenAlex format)
        inverted = work["abstract_inverted_index"]
        # Concatenate words by their first position ordering
        positions = []
        for token, idxs in inverted.items():
            positions.extend((i, token) for i in idxs)
        positions.sort(key=lambda x: x[0])
        abstract = " ".join(token for _, token in positions)
    else:
        abstract = work.get("abstract") or ""

    # Authors
    authors: List[Author] = []
    for auth in (work.get("authorships") or []):
        for a in auth.get("authors", []) or []:
            name = a.get("display_name") or a.get("name")
            if name:
                authors.append(Author(name=name))

    # Venue
    venue = None
    if work.get("primary_location") and work["primary_location"].get("source"):
        venue = work["primary_location"]["source"].get("display_name")

    # Identifiers
    doi = (work.get("ids") or {}).get("doi")
    url = (work.get("primary_location") or {}).get("landing_page_url") or work.get("landing_page_url")
    pdf_url = (work.get("open_access") or {}).get("oa_url")
    year = work.get("publication_year")
    try:
        year = int(year) if year is not None else None
    except Exception:
        year = None

    topics = []
    if isinstance(work.get("topics"), list):
        topics = [t.get("display_name") for t in work["topics"] if t.get("display_name")]

    return PaperRecord(
        source="openalex",
        source_id=str(work.get("id")),
        title=title,
        abstract=abstract,
        authors=authors,
        year=year,
        venue=venue,
        doi=doi,
        url=url,
        open_access_pdf_url=pdf_url,
        topics=topics,
        raw=work,
    )


async def search_openalex(client: HttpClient, query: str, per_page: int = 25, page: int = 1, mailto: Optional[str] = None) -> List[PaperRecord]:
    url = f"{OPENALEX_BASE}/works"
    params: Dict[str, Any] = {"search": query, "per_page": per_page, "page": page}
    if mailto:
        params["mailto"] = mailto
    data = await client.get_json(url, params=params, headers={"User-Agent": "Lumen/0.2"})
    results: List[PaperRecord] = []
    for work in data.get("results", []) or []:
        rec = _to_record(work)
        if rec:
            results.append(rec)
    return results


async def fetch_openalex_by_id(client: HttpClient, work_id: str, mailto: Optional[str] = None) -> Optional[PaperRecord]:
    url = f"{OPENALEX_BASE}/works/{work_id}"
    params: Dict[str, Any] = {}
    if mailto:
        params["mailto"] = mailto
    work = await client.get_json(url, params=params, headers={"User-Agent": "Lumen/0.2"})
    return _to_record(work)


