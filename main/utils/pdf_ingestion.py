import httpx
import logging

logger = logging.getLogger(__name__)


def download_pdf(url: str, timeout: int = 30) -> bytes | None:
    """Download PDF from URL. Returns bytes or None on failure."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Lumen/0.2"})
            if resp.status_code == 200 and len(resp.content) > 100:
                return resp.content
    except Exception as e:
        logger.warning(f"PDF download failed for {url}: {e}")
    return None


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pypdf."""
    from io import BytesIO
    from pypdf import PdfReader
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            try:
                text = page.extract_text()
                if text:
                    pages.append(text)
            except Exception:
                continue
        return "\n\n".join(pages)
    except Exception as e:
        logger.warning(f"PDF text extraction failed: {e}")
        return ""


def ingest_literature_pdf(literature_id: int) -> bool:
    """Download PDF for a Literature record and extract full text.

    Tries the literature's url field. If the URL points to arXiv abstract,
    converts to PDF URL. Stores extracted text in literature.full_text.
    Returns True if text was extracted.
    """
    from main.models import Literature

    try:
        lit = Literature.objects.get(pk=literature_id)
    except Literature.DoesNotExist:
        return False

    if lit.full_text and len(lit.full_text) > 100:
        return True  # Already ingested

    url = lit.url or ''

    # Convert arXiv abstract URLs to PDF URLs
    if 'arxiv.org/abs/' in url:
        url = url.replace('/abs/', '/pdf/') + '.pdf'
    elif lit.arxiv_id and not url:
        url = f"https://arxiv.org/pdf/{lit.arxiv_id}.pdf"

    if not url:
        return False

    pdf_bytes = download_pdf(url)
    if not pdf_bytes:
        return False

    text = extract_text_from_pdf_bytes(pdf_bytes)
    if not text:
        return False

    lit.full_text = text
    lit.save(update_fields=['full_text', 'updated_at'])
    logger.info(f"Ingested {len(text)} chars for literature #{literature_id}: {lit.title[:50]}")
    return True
