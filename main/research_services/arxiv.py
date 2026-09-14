from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from .http import HttpClient
from .types import Author, PaperRecord


ARXIV_API_URL = "https://export.arxiv.org/api/query"


def _strip_ns(tag: str) -> str:
    return tag.split('}', 1)[-1] if '}' in tag else tag


def _text(elem: Optional[ET.Element]) -> str:
    return (elem.text or "").strip() if elem is not None else ""


def _parse_arxiv_id(id_url: str) -> str:
    # Examples: http://arxiv.org/abs/1234.5678v1 → 1234.5678v1
    return id_url.rsplit('/', 1)[-1]


def _find_pdf_link(entry: ET.Element) -> Optional[str]:
    for link in entry.findall('{http://www.w3.org/2005/Atom}link'):
        if link.attrib.get('type') == 'application/pdf':
            return link.attrib.get('href')
    return None


def _parse_entry(entry: ET.Element) -> PaperRecord:
    # Title & abstract
    title = _text(entry.find('{http://www.w3.org/2005/Atom}title'))
    abstract = _text(entry.find('{http://www.w3.org/2005/Atom}summary'))

    # Identity
    id_url = _text(entry.find('{http://www.w3.org/2005/Atom}id'))
    arxiv_id = _parse_arxiv_id(id_url)

    # Authors
    authors: List[Author] = []
    for a in entry.findall('{http://www.w3.org/2005/Atom}author'):
        name = _text(a.find('{http://www.w3.org/2005/Atom}name'))
        if name:
            authors.append(Author(name=name))

    # Dates
    published = _text(entry.find('{http://www.w3.org/2005/Atom}published'))
    year = None
    if published:
        m = re.match(r"(\d{4})-", published)
        if m:
            try:
                year = int(m.group(1))
            except ValueError:
                year = None

    pdf_url = _find_pdf_link(entry)

    record = PaperRecord(
        source="arxiv",
        source_id=arxiv_id,
        title=title,
        abstract=abstract,
        authors=authors,
        year=year,
        published_date=published or None,
        venue="arXiv",
        arxiv_id=arxiv_id,
        url=f"https://arxiv.org/abs/{arxiv_id}",
        open_access_pdf_url=pdf_url,
        raw={},
    )
    return record


async def search_arxiv(client: HttpClient, query: str, start: int = 0, max_results: int = 25, sort_by: str = "relevance", sort_order: str = "descending") -> List[PaperRecord]:
    params: Dict[str, Any] = {
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }
    # arXiv returns Atom XML
    text = await client.get_text(ARXIV_API_URL, params=params, headers={"User-Agent": "Lumen/0.2 (mailto:contact@example.com)"})
    root = ET.fromstring(text)
    results: List[PaperRecord] = []
    for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
        try:
            results.append(_parse_entry(entry))
        except Exception:
            # Skip malformed entries
            continue
    return results


async def fetch_arxiv_by_id(client: HttpClient, arxiv_id: str) -> Optional[PaperRecord]:
    # Use id_list param to request specific entries
    params: Dict[str, Any] = {
        "id_list": arxiv_id,
        "max_results": 1,
    }
    text = await client.get_text(ARXIV_API_URL, params=params, headers={"User-Agent": "Lumen/0.2 (mailto:contact@example.com)"})
    root = ET.fromstring(text)
    entry = root.find('{http://www.w3.org/2005/Atom}entry')
    if entry is None:
        return None
    return _parse_entry(entry)


