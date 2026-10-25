"""
Turn a stored PDF/HTML filing into a list of pages with text.

PDF  -> real page numbers (PyMuPDF). Average text per page below a threshold => likely scanned => needs OCR.
HTML -> SEC filings have no real pages. We split on explicit page-break styles when present and flag
        has_page_numbers=False otherwise, so citations say "section" instead of inventing a page.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import fitz  # PyMuPDF
from bs4 import BeautifulSoup

EXTRACTION_VERSION = 1
MIN_CHARS_PER_PAGE_FOR_TEXT_PDF = 80  # below this on average => treat as scanned


class ExtractionError(Exception):
    pass


@dataclass
class Page:
    number: Optional[int]  # None when the source has no reliable pages
    text: str


@dataclass
class Extracted:
    pages: List[Page]
    page_count: int
    has_page_numbers: bool
    needs_ocr: bool


def extract_pdf(path: Path) -> Extracted:
    try:
        doc = fitz.open(path)
    except Exception as e:  # noqa: BLE001
        raise ExtractionError(f"Cannot open PDF: {e}") from e
    if doc.needs_pass:
        raise ExtractionError("PDF is password protected")
    pages: List[Page] = []
    total_chars = 0
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        total_chars += len(text)
        pages.append(Page(number=i, text=text))
    count = len(pages)
    doc.close()
    if count == 0:
        raise ExtractionError("PDF has no pages")
    needs_ocr = (total_chars / count) < MIN_CHARS_PER_PAGE_FOR_TEXT_PDF
    return Extracted(pages=pages, page_count=count, has_page_numbers=True, needs_ocr=needs_ocr)


_BREAK_STYLE = re.compile(r"page-break-(before|after)\s*:\s*always|break-(before|after)\s*:\s*page", re.I)


def extract_html(path: Path) -> Extracted:
    raw = path.read_bytes()
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    # Inline XBRL hidden facts add noise
    for tag in soup.select("ix\\:header"):
        tag.decompose()

    # Insert a sentinel at explicit page breaks, then split on it.
    sentinel = "\n\u0000PAGEBREAK\u0000\n"
    found_break = False
    for tag in soup.find_all(style=_BREAK_STYLE):
        style = tag.get("style", "")
        marker = soup.new_string(sentinel)
        if re.search(r"(before)\s*:\s*always|break-before\s*:\s*page", style, re.I):
            tag.insert_before(marker)
        else:
            tag.insert_after(marker)
        found_break = True

    text = soup.get_text(separator="\n")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    if found_break:
        parts = [p.strip() for p in text.split("\u0000PAGEBREAK\u0000")]
        parts = [p for p in parts if p]
        pages = [Page(number=i, text=p) for i, p in enumerate(parts, start=1)]
        return Extracted(pages=pages, page_count=len(pages), has_page_numbers=True, needs_ocr=False)

    text = text.replace("\u0000PAGEBREAK\u0000", "").strip()
    if not text:
        raise ExtractionError("HTML contained no text")
    return Extracted(
        pages=[Page(number=None, text=text)], page_count=1, has_page_numbers=False, needs_ocr=False
    )


def extract(path: Path, mime: str) -> Extracted:
    if mime == "application/pdf":
        return extract_pdf(path)
    if mime == "text/html":
        return extract_html(path)
    raise ExtractionError(f"Unsupported type {mime}")
