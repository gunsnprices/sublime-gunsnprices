"""Glue between the text of a document and the gunsnprices parser."""
import re
from typing import List, Optional, Tuple

from ..vendor.gunsnprices import Caliber, ProductInfo, find_calibers, normalize_caliber, parse_title, rounds_per_box
from .extract import Context, extract_candidates


class Row:
    """One parsed title."""

    def __init__(self, line: int, title: str, price: Optional[float], info: ProductInfo):
        self.line = line        # one-based line number in the document
        self.title = title      # the text that was parsed
        self.price = price      # price found in the same record, or None
        self.info = info

    def __repr__(self):
        return "Row(%d, %r, %r)" % (self.line, self.title, self.price)


def score(info: ProductInfo) -> int:
    """How much a parse result looks like a real product title. 0 = nothing recognized."""
    return ((8 if info.model else 0) + (4 if info.calibers else 0)
            + (2 if info.capacity or info.barrel_length or info.rounds else 0))


def _score_text(title: str) -> int:
    return score(parse_title(title))


_PRODUCT_WORDS = re.compile(
    r"\b(\d+\s?gr|grains?|fmj|jhp|jsp|hp|sp|otm|bthp|v-?max|buckshot|birdshot|slugs?|pistols?|rifles?|shotguns?|"
    r"revolvers?|handguns?|carbines?|ammo|ammunition|rounds?|rds?|cartridges?|shells?|bbl|barrel|semi-?auto|"
    r"bolt[\s-]action|pump|o/u|over[\s/-]under|lever[\s-]action|optics? ready|threaded)\b", re.I)


def looks_like_title(info: ProductInfo, text: str) -> bool:
    """True when the text reads like a gun or ammo product title, not just a line with a caliber-like number."""
    if len(text) < 4 or len(text) > 400:
        return False
    if info.model:
        return True
    if not info.calibers:
        return False
    return bool(info.rounds or info.capacity or info.barrel_length or _PRODUCT_WORDS.search(text))


def parse_line(text: str, line_index: int, ctx: Context) -> List[Row]:
    """Parse one line of a document into rows (usually one; several for a JSON array or a SQL INSERT)."""
    rows = []
    for title, price in extract_candidates(text, line_index, ctx, _score_text):
        title = title.strip()
        if title:
            rows.append(Row(line_index + 1, title, price, parse_title(title, price=price)))
    return rows


# words that may appear next to a caliber without making the text "more than a caliber"
_CALIBER_WORDS = set((
    "mm cal caliber calibre x × win winchester rem remington mag magnum wby weatherby spl special spc sprg "
    "springfield spfd government govt gov acp auto automatic s&w sw smith wesson & and blackout blk black out "
    "aac nato creedmoor creed cm crd creedmore parabellum para luger gauge ga gauges bore lr long rifle h&h "
    "holland h&r bm bushmaster bush short colt legend lgnd leg wmr hmr wsm wssm rum ultra super express "
    "nitro lapua norma prc grendel arc sharps carbine m1 +p +p+ ultramag bmg hornet mauser kurz makarov tokarev"
).split())


def caliber_only(text: str) -> Tuple[Optional[Caliber], List[Caliber]]:
    """(caliber, []) when the text is a caliber and nothing else ("9mm Luger", ".223 Rem", "12ga").

    (None, calibers) when it names more than one caliber, (None, []) otherwise.
    """
    t = text.strip()
    if not t or len(t) > 40:
        return None, []
    found = find_calibers(t)
    if len(found) > 1:
        return None, found
    caliber = normalize_caliber(t)
    if not caliber:
        return None, []
    name = caliber.name.lower()
    tokens = [x for x in re.split(r"[\s,/()]+", t.lower()) if x]
    if len(tokens) > 6:
        return None, []
    ok = all(re.search(r"\d", tok) or re.sub(r"^\.|\.$", "", tok) in _CALIBER_WORDS or (len(tok) > 1 and tok in name)
             for tok in tokens)
    return (caliber, []) if ok else (None, [])


def caliber_name(c: Caliber, ascii_names: bool = False) -> str:
    return c.name.replace("×", "x") if ascii_names else c.name


class NormalizeResult:
    def __init__(self):
        self.text = ""          # replacement text (equal to the input when nothing was recognized)
        self.changed = []       # [(original, standard name)]
        self.unknown = []       # values left as they were
        self.ambiguous = []     # values left because they hold more than one caliber, or more than a caliber


_VALUE = re.compile(r"^(\s*)([\"'`]?)([\s\S]*?)\2(\s*)$")


def normalize_caliber_text(text: str, ascii_names: bool = False) -> NormalizeResult:
    """Replace caliber values with their standard names. Each line is one value; whitespace and quotes are kept."""
    result = NormalizeResult()
    parts = re.split(r"(\r?\n)", text)
    out = []
    for i, part in enumerate(parts):
        m = _VALUE.match(part) if i % 2 == 0 else None
        if not m or not m.group(3).strip():
            out.append(part)
            continue
        lead, quote, value, trail = m.groups()
        caliber, multiple = caliber_only(value)
        if not caliber:
            if multiple or normalize_caliber(value):
                result.ambiguous.append(value)
            else:
                result.unknown.append(value)
            out.append(part)
            continue
        name = caliber_name(caliber, ascii_names)
        if name != value:
            result.changed.append((value, name))
        out.append(lead + quote + name + quote + trail)
    result.text = "".join(out)
    return result


def rounds_from(value: str) -> Optional[int]:
    """Round count from a number ("50", "1,000") or from a title ("Federal 9mm 115gr FMJ 50 Rounds")."""
    v = (value or "").strip()
    if re.fullmatch(r"\d[\d,]*", v):
        n = int(v.replace(",", ""))
        return n if n > 0 else None
    return rounds_per_box(v) if v else None
