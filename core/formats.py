"""Output formats: plain text for the output panel, JSON, CSV, popup and annotation HTML."""
import html
import json
from typing import List, Optional

from ..vendor.gunsnprices import Caliber, __version__ as PARSER_VERSION
from .titles import Row, caliber_name


class Options:
    def __init__(self, links: bool = False, ascii_names: bool = False):
        self.links = links              # add GunsNPrices caliber page URLs
        self.ascii_names = ascii_names  # write "×" as "x" in caliber names


def money(n: float) -> str:
    return "${:,.2f}".format(n)


def per_round(n: float, with_cents: bool = False) -> str:
    """"$0.38", or "$0.38 (37.98¢)" with cents."""
    dollars = "${:.2f}".format(n)
    return "{} ({:.2f}¢)".format(dollars, n * 100) if with_cents else dollars


def _num(n) -> str:
    if n is None:
        return ""
    if isinstance(n, float):
        return str(int(n)) if n.is_integer() else repr(n)
    return str(n)


def _caliber_dict(c: Caliber, opts: Options) -> dict:
    out = {"id": c.id, "name": caliber_name(c, opts.ascii_names), "type": c.type}
    if opts.links and c.url:
        out["url"] = c.url
    return out


def row_dict(r: Row, opts: Options) -> dict:
    """The fields of the parser's ProductInfo, plus the source ``line`` and the ``price`` that was found."""
    i = r.info
    m = i.model
    return {
        "line": r.line,
        "title": r.title,
        "kind": i.kind,
        "brand": i.brand,
        "model": None if m is None else {
            "brand": m.brand, "family": m.family, "model": m.model, "generation": m.generation,
            "configs": list(m.configs), "features": list(m.features), "source": m.source,
        },
        "caliber": _caliber_dict(i.caliber, opts) if i.caliber else None,
        "calibers": [_caliber_dict(c, opts) for c in i.calibers],
        "capacity": i.capacity,
        "barrel_length": i.barrel_length,
        "rounds": i.rounds,
        "price": r.price,
        "cost_per_round": i.cost_per_round,
    }


def to_json(rows: List[Row], opts: Options) -> str:
    return json.dumps([row_dict(r, opts) for r in rows], ensure_ascii=False, indent=2) + "\n"


def csv_field(v, delimiter: str = ",") -> str:
    s = _num(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else ("" if v is None else str(v))
    needs_quotes = any(ch in s for ch in ('"', "\r", "\n", delimiter)) or s != s.strip()
    return '"' + s.replace('"', '""') + '"' if needs_quotes else s


# every column a row can have, in the order of "Parse Titles to CSV"
ALL_COLUMNS = ["kind", "brand", "model", "family", "generation", "configs", "features", "caliber", "caliber_type",
               "calibers", "capacity", "barrel_in", "rounds", "price", "cost_per_round", "caliber_url"]


def column_value(r: Row, column: str, opts: Options):
    i = r.info
    m = i.model
    c = i.caliber
    if column == "kind":
        return i.kind
    if column == "brand":
        return i.brand
    if column == "model":
        return m.model if m else ""
    if column == "family":
        return m.family if m else ""
    if column == "generation":
        return m.generation if m else ""
    if column == "configs":
        return "; ".join(m.configs) if m else ""
    if column == "features":
        return "; ".join(m.features) if m else ""
    if column == "caliber":
        return caliber_name(c, opts.ascii_names) if c else ""
    if column == "caliber_type":
        return c.type if c else ""
    if column == "calibers":
        return "; ".join(caliber_name(x, opts.ascii_names) for x in i.calibers)
    if column == "capacity":
        return i.capacity
    if column == "barrel_in":
        return i.barrel_length
    if column == "rounds":
        return i.rounds
    if column == "price":
        return r.price
    if column == "cost_per_round":
        return i.cost_per_round
    if column == "caliber_url":
        return c.url if c else ""
    raise ValueError("unknown column: %s" % column)


def to_csv(rows: List[Row], opts: Options) -> str:
    """CSV (RFC 4180 quoting); several values in one cell are joined with "; "."""
    head = ["line", "title"] + [c for c in ALL_COLUMNS if c != "caliber_url" or opts.links]
    lines = [",".join(head)]
    for r in rows:
        values = [r.line, r.title] + [column_value(r, c, opts) for c in head[2:]]
        lines.append(",".join(csv_field(v) for v in values))
    return "\n".join(lines) + "\n"


def _fields(r: Row) -> List[tuple]:
    """(label, value) pairs for the panel and the popup; the calibers value is a list of Caliber."""
    i = r.info
    out = [("Kind", i.kind)]
    if i.brand:
        out.append(("Brand", i.brand))
    m = i.model
    if m:
        out.append(("Model", m.model))
        if m.family and m.family != m.model:
            out.append(("Family", m.family))
        if m.generation:
            out.append(("Generation", m.generation))
        if m.configs:
            out.append(("Configuration", ", ".join(m.configs)))
        if m.features:
            out.append(("Features", ", ".join(m.features)))
    if i.calibers:
        label = "Caliber" if len(i.calibers) == 1 else "Calibers"
        out.append((label, i.calibers))
    if i.capacity:
        out.append(("Capacity", "%d rounds" % i.capacity))
    if i.barrel_length:
        out.append(("Barrel", "%s in" % _num(i.barrel_length)))
    if i.kind == "ammo" and i.rounds:
        out.append(("Rounds per box", str(i.rounds)))
    if r.price is not None:
        out.append(("Price", money(r.price)))
    if i.cost_per_round is not None:
        out.append(("Cost per round", per_round(i.cost_per_round, True)))
    return out


def to_text(rows: List[Row], opts: Options) -> str:
    """Plain text for the output panel: one block per title."""
    blocks = []
    for r in rows:
        lines = ["Line %d: %s" % (r.line, r.title)]
        for label, value in _fields(r):
            if isinstance(value, list):
                value = ", ".join("%s (%s)" % (caliber_name(c, opts.ascii_names), c.type) for c in value)
                if opts.links:
                    urls = [c.url for c in r.info.calibers if c.url]
                    if urls:
                        value += "  " + " ".join(urls)
            lines.append("  %-15s %s" % (label + ":", value))
        blocks.append("\n".join(lines))
    head = "Parsed %d title%s with the gunsnprices parser %s.\n\n" % (
        len(rows), "" if len(rows) == 1 else "s", PARSER_VERSION)
    return head + "\n\n".join(blocks) + "\n"


def heading(r: Row, opts: Options) -> str:
    """Short name of a parsed title: the model for firearms, "Ammo · caliber · N rounds" for ammo."""
    i = r.info
    if i.kind == "ammo":
        parts = ["Ammo"]
        if i.caliber:
            parts.append(caliber_name(i.caliber, opts.ascii_names))
        if i.rounds:
            parts.append("%d rounds" % i.rounds)
        return " · ".join(parts)
    return i.model.model if i.model else "Firearm"


def popup_html(r: Row, opts: Options) -> str:
    """Minihtml for a popup with the parsed fields of one title, and links to copy them."""
    e = html.escape
    items = []
    for label, value in _fields(r):
        if isinstance(value, list):
            cals = []
            for c in value:
                name = e(caliber_name(c, opts.ascii_names))
                if opts.links and c.url:
                    name = '<a href="%s">%s</a>' % (e(c.url), name)
                cals.append("%s (%s)" % (name, e(c.type)))
            value_html = ", ".join(cals)
        else:
            value_html = e(str(value))
        items.append("<div><span class=\"label\">%s:</span> %s</div>" % (e(label), value_html))
    return (
        "<body id=\"gunsnprices-popup\"><style>"
        "h1 { font-size: 1.1rem; margin: 0 0 0.4rem 0; } .label { color: color(var(--foreground) alpha(0.6)); } "
        ".actions { margin-top: 0.5rem; }"
        "</style>"
        "<h1>%s</h1>%s"
        "<div class=\"actions\"><a href=\"copy:json\">Copy JSON</a> · <a href=\"copy:csv\">Copy CSV</a></div>"
        "</body>" % (e(heading(r, opts)), "".join(items))
    )


def annotation_text(r: Row, opts: Options) -> str:
    """One-line summary for an inline annotation: model or kind, caliber, capacity / rounds, barrel, cost per round."""
    i = r.info
    parts = [i.model.model if i.model else i.kind]
    if i.calibers:
        parts.append(" / ".join(caliber_name(c, opts.ascii_names) for c in i.calibers))
    if i.kind == "ammo":
        if i.rounds:
            parts.append("%d rd" % i.rounds)
        if i.cost_per_round is not None:
            parts.append(per_round(i.cost_per_round) + "/rd")
    else:
        if i.capacity:
            parts.append("%d rd" % i.capacity)
        if i.barrel_length:
            parts.append('%s"' % _num(i.barrel_length))
    return " · ".join(parts)


def cost_text(price: float, rounds: int, cpr: Optional[float]) -> str:
    return "%s for %s rounds = %s per round" % (money(price), "{:,}".format(rounds), per_round(cpr or 0, True))
