"""
Safe document download.

Filing URLs come from external systems, so we treat them as untrusted:
- https only, host must be on an allowlist (prevents SSRF to internal addresses)
- streamed with a hard size cap
- content must look like a PDF or HTML document (not an error page or an executable)
- stored under a path built from sanitized parts, never from the URL
"""
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.core.config import settings

ALLOWED_HOST_SUFFIXES = (
    "sec.gov",
    "nseindia.com",
    "bseindia.com",
)
MAX_BYTES = 120 * 1024 * 1024  # 120 MB; large Indian annual reports can be 20-60 MB


class DownloadError(Exception):
    pass


@dataclass
class Downloaded:
    path: Path
    sha256: str
    mime: str  # "application/pdf" | "text/html"
    size: int


def validate_url(url: str) -> None:
    parts = urlparse(url)
    if parts.scheme != "https":
        raise DownloadError("Only https URLs are allowed")
    host = (parts.hostname or "").lower()
    if not any(host == s or host.endswith("." + s) for s in ALLOWED_HOST_SUFFIXES):
        raise DownloadError(f"Host not allowed: {host}")


def _safe(part: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", part)[:80] or "x"


def build_path(ticker: str, accession: str, ext: str) -> Path:
    base = Path(settings.STORAGE_DIR).resolve()
    target = (base / _safe(ticker.upper()) / f"{_safe(accession)}.{ext}").resolve()
    if base not in target.parents:
        raise DownloadError("Unsafe storage path")
    return target


def sniff_mime(head: bytes) -> Optional[str]:
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    lowered = head[:2048].lower()
    if b"<html" in lowered or b"<!doctype html" in lowered or b"<?xml" in lowered and b"<html" in lowered:
        return "text/html"
    return None


async def download_document(
    url: str,
    ticker: str,
    accession: str,
    headers: Optional[dict] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Downloaded:
    validate_url(url)
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=60.0, follow_redirects=False)
    try:
        # Follow redirects manually so every hop is re-validated against the allowlist.
        current = url
        for _ in range(4):
            validate_url(current)
            async with client.stream("GET", current, headers=headers or {}) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    current = str(httpx.URL(current).join(resp.headers.get("location", "")))
                    continue
                if resp.status_code != 200:
                    raise DownloadError(f"Download failed with HTTP {resp.status_code}")
                declared = resp.headers.get("content-length")
                if declared and int(declared) > MAX_BYTES:
                    raise DownloadError("File too large")

                tmp: Optional[Path] = None
                sha = hashlib.sha256()
                size = 0
                mime: Optional[str] = None
                handle = None
                try:
                    async for chunk in resp.aiter_bytes(65536):
                        if mime is None:
                            mime = sniff_mime(chunk)
                            if mime is None:
                                raise DownloadError("Unrecognised file type (not PDF or HTML)")
                            final = build_path(ticker, accession, "pdf" if mime == "application/pdf" else "html")
                            final.parent.mkdir(parents=True, exist_ok=True)
                            tmp = final.with_suffix(final.suffix + ".part")
                            handle = open(tmp, "wb")
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise DownloadError("File too large")
                        sha.update(chunk)
                        handle.write(chunk)
                    if mime is None or handle is None:
                        raise DownloadError("Empty response")
                    handle.close()
                    handle = None
                    tmp.replace(final)  # atomic: no half-written file is ever visible
                    return Downloaded(path=final, sha256=sha.hexdigest(), mime=mime, size=size)
                except BaseException:
                    if handle:
                        handle.close()
                    if tmp and tmp.exists():
                        tmp.unlink()
                    raise
        raise DownloadError("Too many redirects")
    finally:
        if own_client:
            await client.aclose()
