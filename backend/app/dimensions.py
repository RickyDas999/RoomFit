"""Pattern-matching dimension parser (no LLM). Never guesses.

Returns a structured ParseResult: status "parsed" (w x d [x h] in inches),
"ambiguous" (we found something but can't trust it; `reason` says why), or
"missing" (no measurement at all). Order is always normalized to W x D x H.
"""

import re
from typing import Literal

from pydantic import BaseModel

MAX_INCHES = 300.0  # sanity guard: nothing in a bedroom is 25 ft long
MIN_INCHES = 6.0  # width and depth must be at least this (Ricky, Nov 15)

Reason = Literal[
    "no_dimensions",
    "no_unit",
    "shipping_size",
    "mattress_size",
    "component_only",
    "range",
    "incomplete",
    "multiple_sizes",
    "conflicting_labels",
    "implausible",
    "quantity",
    "too_many_values",
]


class Dimensions(BaseModel):
    w: float
    d: float
    h: float | None = None  # many listings give only width x depth


class ParseResult(BaseModel):
    status: Literal["parsed", "ambiguous", "missing"]
    dimensions: Dimensions | None = None
    source: str | None = None  # matched text from the description
    reason: Reason | None = None
    candidates: list[Dimensions] = []  # filled for multiple_sizes


# --- regex pieces (case-insensitive; written so matches are slices of the original text) ---
_NUM = (
    r"(?<![\d./])(?:"
    r"\d{1,2}['’′]\s*\d{1,2}(?:\.\d{1,3})?(?=\s*(?:''|[\"”″]))"  # 6'2"
    r"|\d{1,4}[ -]\d{1,2}/\d{1,2}"  # 39 1/2
    r"|\d{1,2}/\d{1,2}"  # 1/2
    r"|\d{1,4}(?:\.\d{1,3})?"  # 39, 39.5
    r")(?![\d/])"
)
_UNIT = r"(?:''|[\"”“″]|inches|inch|in\b|cm\b|mm\b|feet\b|ft\b|['’′‘])"
_LABEL = r"(?:wide|width|deep|depth|length|long|height|high|tall|w|d|h|l)(?![a-wyz])"
_ITEM = rf"{_NUM}\s*(?:{_UNIT})?(?:\s*{_LABEL}(?:\s*{_UNIT})?)?"
_SEP = r"\s*(?:[x×✕]|\bby\b)\s*"
_SEQ = re.compile(rf"{_ITEM}(?:{_SEP}{_ITEM}){{1,5}}", re.IGNORECASE)
_ITEM_PARTS = re.compile(
    rf"({_NUM})\s*({_UNIT})?(?:\s*({_LABEL})(?:\s*({_UNIT}))?)?", re.IGNORECASE
)
# "Width: 39 in" and "43" Tall" (a unit is required, so "Height 2 drawers" is ignored)
_PREFIX_LABELED = re.compile(
    rf"(?:\b(wide|width|deep|depth|length|height|tall)\b\s*[:=]?|\b([wdhl])\s*:)\s*({_NUM})\s*({_UNIT})",
    re.IGNORECASE,
)
_SUFFIX_LABELED = re.compile(
    rf"({_NUM})\s*({_UNIT})\s*(wide|deep|tall|high|w|d|h)(?![a-wyz])", re.IGNORECASE
)

_TO_INCHES = {
    "cm": 1 / 2.54,
    "mm": 1 / 25.4,
    "ft": 12.0,
    "feet": 12.0,
    "'": 12.0,
    "’": 12.0,
    "′": 12.0,
    "‘": 12.0,
}
_CANON = {
    "w": "w",
    "wide": "w",
    "width": "w",
    "d": "d",
    "deep": "d",
    "depth": "d",
    "l": "l",
    "length": "l",
    "long": "l",
    "h": "h",
    "high": "h",
    "height": "h",
    "tall": "h",
}

_SHIPPING = re.compile(
    r"package|packaging|packed|carton|shipping|shipped|box size|boxed|gift box|per box",
    re.IGNORECASE,
)
_MATTRESS = re.compile(r"mattress|thick", re.IGNORECASE)
_COMPONENT = re.compile(
    r"drawer|interior|inside|inner|\bseat\b|opening|shel(?:f|ves)|\blegs?\b|tray|keyboard",
    re.IGNORECASE,
)
_ADJUSTABLE = re.compile(r"adjust|from\s*$|between\s*$", re.IGNORECASE)
_RANGE_AFTER = re.compile(r"^\s*(?:to|-|–|—|and)\s*\d", re.IGNORECASE)
_QUANTITY = re.compile(
    r"(?:qty|quantity|buy|pack of|set of|count|pcs|pieces)\W*$", re.IGNORECASE
)
_OVERALL = re.compile(
    r"overall|assembled|product (?:dimension|size)|item (?:dimension|size)",
    re.IGNORECASE,
)


def _number(token: str) -> float:
    """'39', '39.5', '1/2', '39 1/2', "6'2" -> float (feet+inches already in inches)."""
    if "'" in token or "’" in token or "′" in token:
        feet, inches = re.split(r"['’′]\s*", token)
        return int(feet) * 12 + float(inches)
    if "/" in token:
        whole, _, frac = token.replace("-", " ").rpartition(" ")
        num, den = frac.split("/")
        return (float(whole) if whole else 0.0) + int(num) / int(den or 1)
    return float(token)


def _inches(value: str, unit: str | None) -> float:
    if "'" in value or "’" in value or "′" in value:
        return _number(value)  # feet+inches: the number is already in inches
    return _number(value) * _TO_INCHES.get((unit or "in").lower(), 1.0)


def _context_reason(text: str, start: int, end: int, single: bool) -> Reason | None:
    before = text[max(0, start - 40) : start]
    after = re.split(r"[.;\n]", text[end : end + 25])[0]  # same sentence only
    if _QUANTITY.search(before[-15:]):
        return "quantity"
    if _SHIPPING.search(before) or _SHIPPING.search(after[:20]):
        return "shipping_size"
    if _MATTRESS.search(before[-30:]) or _MATTRESS.search(after[:20]):
        return "mattress_size"
    if _COMPONENT.search(before[-25:]):
        return "component_only"
    if single and (_RANGE_AFTER.match(after) or _ADJUSTABLE.search(before[-25:])):
        return "range"
    return None


def _assign(items: list[tuple[str, str | None, str | None]]) -> Dimensions | Reason:
    """items: (number, unit, label). Returns normalized W x D x H, or a reason."""
    if len(items) > 3:
        return "too_many_values"
    units = [u for _, u, _ in items if u]
    if not units:
        return "no_unit"
    values: list[tuple[str | None, float]] = []
    for i, (num, unit, label) in enumerate(items):
        # a missing unit borrows the next stated one, else the last one ("39 x 80 x 14 in")
        unit = unit or next((u for _, u, _ in items[i + 1 :] if u), units[-1])
        values.append((_CANON[label.lower()] if label else None, _inches(num, unit)))
    labels = [lab for lab, _ in values if lab]
    if len(labels) != len(set(labels)):
        return "conflicting_labels"
    slots: dict[str, float] = {lab: v for lab, v in values if lab and lab != "l"}
    length = next((v for lab, v in values if lab == "l"), None)
    if length is not None:  # L fills whichever of W/D is not stated
        if "w" not in slots:
            slots["w"] = length
        elif "d" not in slots:
            slots["d"] = length
        else:
            return "conflicting_labels"
    for lab, v in values:  # unlabeled numbers fill the remaining slots in W, D, H order
        if lab is None:
            free = next((s for s in "wdh" if s not in slots), None)
            if free is None:
                return "conflicting_labels"
            slots[free] = v
    if "w" not in slots or "d" not in slots:
        return "incomplete"
    if any(not MIN_INCHES <= slots[k] <= MAX_INCHES for k in ("w", "d")) or (
        "h" in slots and not 0 < slots["h"] <= MAX_INCHES
    ):
        return "implausible"
    return Dimensions(
        w=round(slots["w"], 2),
        d=round(slots["d"], 2),
        h=round(slots["h"], 2) if "h" in slots else None,
    )


def _same_size(a: Dimensions, b: Dimensions) -> bool:
    """Same size stated twice (e.g. in and cm) rounds to within 1 inch."""
    close = abs(a.w - b.w) <= 1 and abs(a.d - b.d) <= 1
    return close and (a.h is None or b.h is None or abs(a.h - b.h) <= 1)


def parse_dimensions(text: str) -> ParseResult:
    found: list[tuple[Dimensions, str, str]] = []  # (dims, snippet, text before it)
    rejected: list[Reason] = []
    masked = text
    for m in _SEQ.finditer(text):
        masked = masked[: m.start()] + " " * (m.end() - m.start()) + masked[m.end() :]
        reason = _context_reason(text, m.start(), m.end(), single=False)
        if reason is None:
            parts = [
                (n, u or u2 or None, lab or None)
                for n, u, lab, u2 in _ITEM_PARTS.findall(m.group())
            ]
            result = _assign(parts)
            if isinstance(result, Dimensions):
                found.append(
                    (
                        result,
                        m.group().strip(),
                        text[max(0, m.start() - 40) : m.start()],
                    )
                )
                continue
            reason = result
        rejected.append(reason)

    if not found:  # fall back to labeled single values: "Width: 39 in", "43" Tall"
        labeled: list[tuple[str, str | None, str | None]] = []
        pieces: list[str] = []
        for rx in (_PREFIX_LABELED, _SUFFIX_LABELED):
            for m in rx.finditer(masked):
                if rx is _PREFIX_LABELED:
                    label, num, unit = m.group(1) or m.group(2), m.group(3), m.group(4)
                else:
                    num, unit, label = m.group(1), m.group(2), m.group(3)
                reason = _context_reason(text, m.start(), m.end(), single=True)
                if reason:
                    rejected.append(reason)
                else:
                    labeled.append((num, unit, label))
                    pieces.append(m.group().strip())
                masked = (
                    masked[: m.start()]
                    + " " * (m.end() - m.start())
                    + masked[m.end() :]
                )
        if labeled:
            result = _assign(labeled)
            if isinstance(result, Dimensions):
                found.append((result, " … ".join(pieces), ""))
            else:
                rejected.append(result)

    unique: list[tuple[Dimensions, str, str]] = []
    for item in found:
        if all(not _same_size(item[0], u[0]) for u in unique):
            unique.append(item)
    if (
        len(unique) > 1
    ):  # prefer a single "Overall ..." measurement if exactly one is flagged
        overall = [u for u in unique if _OVERALL.search(u[2])]
        if len(overall) == 1:
            unique = overall
    if len(unique) == 1:
        return ParseResult(
            status="parsed", dimensions=unique[0][0], source=unique[0][1]
        )
    if len(unique) > 1:
        return ParseResult(
            status="ambiguous",
            reason="multiple_sizes",
            candidates=[u[0] for u in unique],
        )
    if rejected:
        return ParseResult(status="ambiguous", reason=rejected[0])
    return ParseResult(status="missing", reason="no_dimensions")
