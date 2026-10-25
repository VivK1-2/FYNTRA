"""
Split extracted pages into search chunks that remember where they came from.

~3200 characters (~800 tokens) per chunk with a small overlap. A new "Item 1A."-style heading starts a new
chunk so risk factors, MD&A etc. do not blend together. Page range and section label travel with each chunk.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

from app.services.documents.extractor import Page

TARGET_CHARS = 3200
OVERLAP_CHARS = 300

# 10-K style headings: "Item 1A. Risk Factors", "ITEM 7. MANAGEMENT'S DISCUSSION..."
_ITEM = re.compile(r"^\s*(item\s+\d{1,2}[a-c]?)\s*[.:\-–—]?\s*(.{0,90})$", re.I)


@dataclass
class Chunk:
    index: int
    text: str
    page_start: Optional[int]
    page_end: Optional[int]
    section: Optional[str]


def _heading(line: str) -> Optional[str]:
    m = _ITEM.match(line)
    if not m:
        return None
    title = m.group(2).strip(" .")
    label = m.group(1).title().replace("  ", " ")
    return f"{label}. {title}".strip(". ") if title else label


def chunk_pages(pages: List[Page]) -> List[Chunk]:
    chunks: List[Chunk] = []
    buf: List[str] = []
    buf_len = 0
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    section: Optional[str] = None
    buf_section: Optional[str] = None
    fresh = 0  # characters added since the last flush (excludes overlap carried over)

    def flush():
        nonlocal buf, buf_len, start_page, end_page, buf_section, fresh
        text = "\n".join(buf).strip()
        if text and fresh > 0:
            chunks.append(Chunk(len(chunks), text, start_page, end_page, buf_section))
        # keep a tail for overlap so sentences cut at a boundary remain findable
        tail = text[-OVERLAP_CHARS:] if text and len(text) > OVERLAP_CHARS else ""
        buf, buf_len = ([tail] if tail else []), len(tail)
        start_page, end_page, buf_section = None, None, section
        fresh = 0

    for page in pages:
        for line in page.text.splitlines():
            line = line.strip()
            if not line:
                continue
            head = _heading(line)
            if head and buf_len > 200:  # heading starts a new section-chunk
                section = head
                flush()
                buf, buf_len = [], 0  # no overlap across a section boundary
            elif head:
                section = head
                buf_section = head
            if start_page is None:
                start_page = page.number
                buf_section = buf_section or section
            end_page = page.number
            buf.append(line)
            buf_len += len(line) + 1
            fresh += len(line) + 1
            if buf_len >= TARGET_CHARS:
                flush()
    flush()
    return [c for c in chunks if len(c.text) > 40]
