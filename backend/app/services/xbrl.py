"""
Inline XBRL (iXBRL) fact extraction from a downloaded 10-K HTML file.

SEC filers tag every reported number in the filing itself (<ix:nonFraction>). This reads those tags with their
context (period, dimensions), unit, scale and sign, so every line item in the filing can be listed, not just the
dozen we use for the headline financials. Nothing is guessed: values are exactly what the filer tagged.
"""
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

_WORDS = {"no": 0, "none": 0, "zero": 0, "nil": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
          "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


@dataclass
class Fact:
    concept: str
    label: str
    value: float
    unit: str
    decimals: Optional[str]
    period_type: str            # instant | duration | unknown
    start: Optional[str]
    end: Optional[str]
    dimensions: List[str]


@dataclass
class XbrlDoc:
    facts: List[Fact] = field(default_factory=list)
    document: Dict[str, str] = field(default_factory=dict)


def humanize(concept: str) -> str:
    local = concept.split(":", 1)[-1]
    return _CAMEL.sub(" ", local)


def _parse_number(raw: str, fmt: str) -> Optional[float]:
    s = raw.strip()
    f = fmt.lower()
    if "numwordsen" in f:
        return _WORDS.get(s.lower())
    if "zerodash" in f or "fixed-zero" in f or "fixedzero" in f or s in {"", "-", "—", "–"}:
        return 0.0
    if "comma-decimal" in f or "commadecimal" in f:
        s = s.replace(".", "").replace(" ", "").replace(" ", "").replace(",", ".")
    else:
        s = s.replace(",", "").replace(" ", "").replace(" ", "")
    s = re.sub(r"[^0-9.]", "", s)
    if not s or s == ".":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _unit_label(u) -> str:
    def strip(m: str) -> str:
        return m.split(":", 1)[-1]
    if u.find("xbrli:divide"):
        num = [strip(m.get_text(strip=True)) for m in u.find("xbrli:unitnumerator").find_all("xbrli:measure")]
        den = [strip(m.get_text(strip=True)) for m in u.find("xbrli:unitdenominator").find_all("xbrli:measure")]
        return f"{'*'.join(num)}/{'*'.join(den)}"
    return "*".join(strip(m.get_text(strip=True)) for m in u.find_all("xbrli:measure"))


def parse_ixbrl(path: Path) -> XbrlDoc:
    soup = BeautifulSoup(path.read_bytes(), "lxml")

    contexts: Dict[str, Tuple[str, Optional[str], Optional[str], List[str]]] = {}
    for c in soup.find_all("xbrli:context"):
        period = c.find("xbrli:period")
        inst = period.find("xbrli:instant") if period else None
        st = period.find("xbrli:startdate") if period else None
        en = period.find("xbrli:enddate") if period else None
        dims = [f"{m.get('dimension')}={m.get_text(strip=True)}"
                for m in c.find_all(["xbrldi:explicitmember", "xbrldi:typedmember"])]
        if inst:
            contexts[c.get("id")] = ("instant", None, inst.get_text(strip=True), dims)
        elif st and en:
            contexts[c.get("id")] = ("duration", st.get_text(strip=True), en.get_text(strip=True), dims)
        else:
            contexts[c.get("id")] = ("unknown", None, None, dims)

    units = {u.get("id"): _unit_label(u) for u in soup.find_all("xbrli:unit")}

    doc = XbrlDoc()
    for t in soup.find_all("ix:nonnumeric"):
        name = t.get("name", "")
        if name.startswith("dei:") and name not in doc.document:
            text = t.get_text(" ", strip=True)
            if text and len(text) <= 200:
                doc.document[name] = text

    seen = set()
    for t in soup.find_all("ix:nonfraction"):
        if (t.get("xsi:nil") or "").lower() == "true":
            continue
        name, ctx = t.get("name"), t.get("contextref")
        if not name or ctx not in contexts:
            continue
        value = _parse_number(t.get_text(strip=True), t.get("format") or "")
        if value is None:
            continue
        try:
            value *= 10 ** int(t.get("scale") or 0)
        except ValueError:
            pass
        if t.get("sign") == "-":
            value = -value
        key = (name, ctx, t.get("unitref"), value)
        if key in seen:  # the same fact is often repeated in notes and tables
            continue
        seen.add(key)
        ptype, start, end, dims = contexts[ctx]
        doc.facts.append(Fact(
            concept=name, label=humanize(name), value=value, unit=units.get(t.get("unitref"), t.get("unitref") or ""),
            decimals=t.get("decimals"), period_type=ptype, start=start, end=end, dimensions=dims,
        ))
    return doc


_SKIP_NS = ("http://www.xbrl.org/2003/instance", "http://www.xbrl.org/2003/linkbase", "http://xbrl.org/2006/xbrldi",
            "http://www.xbrl.org/2003/XLink", "http://www.w3.org/1999/xlink")


def parse_instance(path: Path) -> XbrlDoc:
    """Classic XBRL instance (.xml), as NSE publishes for Indian results filings: facts are direct children of the root."""
    from lxml import etree

    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, recover=True)
    root = etree.fromstring(path.read_bytes(), parser)
    if root is None:
        return XbrlDoc()
    X = "{http://www.xbrl.org/2003/instance}"
    D = "{http://xbrl.org/2006/xbrldi}"

    contexts: Dict[str, Tuple[str, Optional[str], Optional[str], List[str]]] = {}
    for c in root.iter(X + "context"):
        period = c.find(X + "period")
        inst = period.findtext(X + "instant") if period is not None else None
        st = period.findtext(X + "startDate") if period is not None else None
        en = period.findtext(X + "endDate") if period is not None else None
        dims = [f"{m.get('dimension')}={(m.text or '').strip()}" for m in c.iter(D + "explicitMember", D + "typedMember")]
        if inst:
            contexts[c.get("id")] = ("instant", None, inst.strip(), dims)
        elif st and en:
            contexts[c.get("id")] = ("duration", st.strip(), en.strip(), dims)
        else:
            contexts[c.get("id")] = ("unknown", None, None, dims)

    units: Dict[str, str] = {}
    for u in root.iter(X + "unit"):
        if u.find(X + "divide") is not None:
            num = [(m.text or "").split(":")[-1] for m in u.find(X + "divide").find(X + "unitNumerator").iter(X + "measure")]
            den = [(m.text or "").split(":")[-1] for m in u.find(X + "divide").find(X + "unitDenominator").iter(X + "measure")]
            units[u.get("id")] = f"{'*'.join(num)}/{'*'.join(den)}"
        else:
            units[u.get("id")] = "*".join((m.text or "").split(":")[-1] for m in u.iter(X + "measure"))

    doc = XbrlDoc()
    seen = set()
    for el in root:
        if not isinstance(el.tag, str) or el.get("contextRef") is None:
            continue
        ns, _, local = el.tag[1:].partition("}") if el.tag.startswith("{") else ("", "", el.tag)
        if ns in _SKIP_NS:
            continue
        ctx = el.get("contextRef")
        text = (el.text or "").strip()
        if ctx not in contexts or not text:
            continue
        if el.get("unitRef") is None:
            # text fact (entity name, dates, remarks): keep a few short ones as document info
            if len(text) <= 120 and local not in doc.document and len(doc.document) < 12:
                doc.document[local] = text
            continue
        value = _parse_number(text, "")
        if value is None:
            continue
        if text.lstrip().startswith("-"):
            value = -abs(value)
        key = (local, ctx, el.get("unitRef"), value)
        if key in seen:
            continue
        seen.add(key)
        ptype, start, end, dims = contexts[ctx]
        prefix = el.prefix or "xbrl"
        doc.facts.append(Fact(
            concept=f"{prefix}:{local}", label=humanize(local), value=value,
            unit=units.get(el.get("unitRef"), el.get("unitRef") or ""), decimals=el.get("decimals"),
            period_type=ptype, start=start, end=end, dimensions=dims,
        ))
    return doc


# small cache so paging/filtering the same filing does not re-parse a multi-MB file
_cache: "OrderedDict[Tuple[str, float], XbrlDoc]" = OrderedDict()
_lock = threading.Lock()


def load_doc(path: Path) -> XbrlDoc:
    key = (str(path), path.stat().st_mtime)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    with open(path, "rb") as fh:
        head = fh.read(4096).lower()
    is_instance = b"<xbrli:xbrl" in head or b"<xbrl " in head or b"<xbrl>" in head
    doc = parse_instance(path) if is_instance and b"<html" not in head else parse_ixbrl(path)
    with _lock:
        _cache[key] = doc
        while len(_cache) > 3:
            _cache.popitem(last=False)
    return doc


def clear_cache() -> int:
    with _lock:
        n = len(_cache)
        _cache.clear()
        return n


def cache_size() -> int:
    return len(_cache)


def filter_facts(doc: XbrlDoc, q: Optional[str], dimensional: bool) -> List[Fact]:
    out = doc.facts
    if not dimensional:
        out = [f for f in out if not f.dimensions]
    if q:
        needle = q.lower().strip()
        out = [f for f in out if needle in f.concept.lower() or needle in f.label.lower()]
    return out


def fact_to_dict(f: Fact) -> Dict[str, Any]:
    return {
        "concept": f.concept, "label": f.label, "value": f.value, "unit": f.unit, "decimals": f.decimals,
        "period_type": f.period_type, "start": f.start, "end": f.end, "dimensions": f.dimensions,
    }
