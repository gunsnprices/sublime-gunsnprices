"""Find the product title (and a price, if there is one) in a line of CSV, TSV, JSON, SQL, a Markdown table or plain
text. Nothing here imports Sublime Text, so it is unit tested on its own.
"""
import json
import re
from typing import Callable, List, Optional, Tuple

DELIMITERS = ["\t", ",", ";", "|"]
JSON_LANGS = {"json", "jsonl"}


class Context:
    """What is known about a document: its language, cell delimiter and the columns of its header row."""

    def __init__(self, language="plaintext", delimiter=None, columns=None, header_line=None):
        self.language = language            # "plaintext", "csv", "tsv", "json", "jsonl", "sql" or "markdown"
        self.delimiter = delimiter          # cell delimiter when the document is delimited (CSV, TSV)
        self.columns = columns              # (title index, price index or None) from a header row
        self.header_line = header_line      # zero-based line of that header row

    def __repr__(self):
        return "Context(%r, %r, %r, %r)" % (self.language, self.delimiter, self.columns, self.header_line)


class Cell:
    """A cell of a delimited line: unquoted, trimmed text and the offsets of the raw cell."""

    def __init__(self, text, start, end):
        self.text = text
        self.start = start
        self.end = end


def _norm_name(name: str) -> str:
    return re.sub(r"[\s_-]+", "_", name.strip().lower())


def title_rank(name: str) -> int:
    """Rank of a column or key name as the product title: 0 = not a title."""
    n = _norm_name(name)
    if re.search(r"(^|_)title$", n):
        return 3
    if re.fullmatch(r"((product|item|offer|listing)_)?name", n) or n in ("productname", "itemname"):
        return 2
    if re.fullmatch(r"product|item|listing|offer|description|product_description|short_description", n):
        return 1
    return 0


def price_rank(name: str) -> int:
    """Rank of a column or key name as the price: 0 = not a price."""
    n = _norm_name(name)
    if re.fullmatch(r"(sale|our|current|special|final|offer)_?price(_usd)?", n):
        return 3
    if re.fullmatch(r"price(_usd)?", n):
        return 2
    if re.fullmatch(r"(regular|retail|list|unit|base)_?price(_usd)?|cost|amount", n):
        return 1
    return 0


def _best_index(names, rank) -> Optional[int]:
    best, best_rank = None, 0
    for i, name in enumerate(names):
        r = rank(name)
        if r > best_rank:
            best, best_rank = i, r
    return best


def header_columns(names: List[str]) -> Optional[Tuple[int, Optional[int]]]:
    """(title index, price index or None) of a header row, or None when the row is not a header with a title column."""
    if len(names) < 2 or any(len(s) > 60 or re.fullmatch(r"\$?[\d.,]+", s) for s in names):
        return None
    title = _best_index(names, title_rank)
    if title is None:
        return None
    return title, _best_index(names, price_rank)


def split_cells(line: str, delimiter: str, quote: str = '"') -> List[Cell]:
    """Split a delimited line into cells. Handles quoted cells, doubled quotes and (for SQL) backslash escapes."""
    cells = []
    n = len(line)
    i = 0
    while True:
        start = i
        j = i
        while j < n and (line[j] == " " or (line[j] == "\t" and delimiter != "\t")):
            j += 1
        if j < n and line[j] == quote:
            j += 1
            buf = []
            while j < n:
                ch = line[j]
                if ch == "\\" and quote == "'" and j + 1 < n:
                    buf.append(line[j + 1])
                    j += 2
                    continue
                if ch == quote:
                    if j + 1 < n and line[j + 1] == quote:
                        buf.append(quote)
                        j += 2
                        continue
                    j += 1
                    break
                buf.append(ch)
                j += 1
            while j < n and line[j] != delimiter:
                j += 1
            text = "".join(buf).strip()
        else:
            while j < n and line[j] != delimiter:
                j += 1
            text = line[start:j].strip()
        cells.append(Cell(text, start, j))
        if j >= n:
            break
        i = j + 1
    return cells


def detect_delimiter(line: str) -> Optional[str]:
    """The delimiter that occurs most often outside quotes, or None."""
    counts = {}
    in_quote = False
    for ch in line:
        if ch == '"':
            in_quote = not in_quote
        elif not in_quote and ch in DELIMITERS:
            counts[ch] = counts.get(ch, 0) + 1
    best, best_count = None, 0
    for d in DELIMITERS:
        c = counts.get(d, 0)
        if c > best_count:
            best, best_count = d, c
    return best


def parse_price(value) -> Optional[float]:
    """A price from a cell value or a number: "$1,299.99", "18.99", 18.99, "18.99 USD"."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 and value == value and value != float("inf") else None
    if not isinstance(value, str):
        return None
    s = re.sub(r"^usd\s*|\s*usd$", "", value.strip(), flags=re.I)
    s = re.sub(r"^\$\s*", "", s)
    s = re.sub(r",(?=\d{3}\b)", "", s)
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    n = float(s)
    return n if n > 0 else None


# a cell that holds nothing but a price: "18.99", "$18.99", "$18", "1,299.99"
_PRICE_CELL = re.compile(r"^(\$\s?\d{1,3}(,\d{3})*(\.\d{1,2})?|\$\s?\d+(\.\d{1,2})?|\d{1,3}(,\d{3})*\.\d{2}|\d+\.\d{2})$")

# a price inside free text: "$18.99", "USD 18.99", "18.99 USD"
_PRICE_IN_TEXT = re.compile(
    r"(?:^|[\s(@:,;|-])(\$\s?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?|USD\s?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?"
    r"|(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}\s?USD)(?=$|[\s),;|])", re.I)


def find_price_in_text(text: str) -> Tuple[Optional[float], str]:
    """(price, text without the price) for a price written in free text; (None, text) when there is none."""
    m = _PRICE_IN_TEXT.search(text)
    if not m:
        return None, text
    rest = text[:m.start(1)] + text[m.end(1):]
    rest = re.sub(r"[(\[]\s*[-|@:,;]?\s*[)\]]", "", rest)
    rest = re.sub(r"\s*[-|@:,;]\s*$", "", rest)
    rest = re.sub(r"\s{2,}", " ", rest).strip()
    return parse_price(m.group(1)), rest


def strip_list_marker(s: str) -> str:
    return re.sub(r"^\s*(?:[-*+•]|\d{1,4}[.)])\s+", "", s).strip()


def _is_header_row(cells: List[str]) -> bool:
    return any(title_rank(c) > 0 for c in cells) and not any(re.search(r"\d", c) for c in cells)


def is_title_candidate(s: str) -> bool:
    return (3 <= len(s) <= 400 and bool(re.search(r"[a-z]", s, re.I)) and not re.match(r"(https?://|www\.)", s, re.I)
            and not s.startswith("<") and not re.search(r"\.(jpe?g|png|gif|webp|svg)(\?.*)?$", s, re.I))


Candidate = Tuple[str, Optional[float]]     # (title, price)


def pick_from_cells(cells: List[str], score: Callable[[str], int], columns=None) -> Optional[Candidate]:
    """The title and price in the cells of one record.

    With known columns they are used. Otherwise the price is the first cell that is only a price, and the title is the
    best of the three longest text cells, as judged by ``score``.
    """
    price = None
    price_index = -1
    if columns is not None and columns[1] is not None and columns[1] < len(cells):
        price_index = columns[1]
        price = parse_price(cells[price_index])
    else:
        for i, c in enumerate(cells):
            if _PRICE_CELL.match(c):
                price_index = i
                price = parse_price(c)
                break
    title = None
    if columns is not None and columns[0] < len(cells):
        title = cells[columns[0]]
    else:
        options = [(text, i) for i, text in enumerate(cells) if i != price_index and is_title_candidate(text)]
        options.sort(key=lambda o: (-len(o[0]), o[1]))
        best = -1
        for text, _ in options[:3]:
            s = score(text)
            if s > best:
                best, title = s, text
    if not title:
        return None
    if price is None:
        found, rest = find_price_in_text(title)
        if found is not None:
            return rest, found
    return title, price


_JSON_STRING = r'"(?:[^"\\]|\\.)*"'
_JSON_PROPERTY = re.compile(r"^(" + _JSON_STRING + r")\s*:\s*(.*?)\s*,?$")
_JSON_BARE_STRING = re.compile(r"^(" + _JSON_STRING + r")\s*,?$")


def _from_object(o: dict) -> Optional[Candidate]:
    keys = list(o)
    string_keys = [k for k in keys if isinstance(o[k], str)]
    tk = _best_index(string_keys, title_rank)
    if tk is not None:
        title = o[string_keys[tk]]
    else:
        texts = sorted((o[k] for k in string_keys if is_title_candidate(o[k])), key=len, reverse=True)
        title = texts[0] if texts else None
    if not title:
        return None
    pk = _best_index(keys, price_rank)
    return title, (parse_price(o[keys[pk]]) if pk is not None else None)


def _json_candidates(line: str, is_json_doc: bool) -> Optional[List[Candidate]]:
    s = re.sub(r",$", "", line.strip())
    if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
        try:
            v = json.loads(s)
        except ValueError:
            v = None        # not a complete JSON value on this line
        else:
            out = []
            for item in (v if isinstance(v, list) else [v]):
                if isinstance(item, str):
                    out.append((item, None))
                elif isinstance(item, dict):
                    c = _from_object(item)
                    if c:
                        out.append(c)
            return out
    prop = _JSON_PROPERTY.match(s)
    if prop:
        try:
            key = json.loads(prop.group(1))
            value = prop.group(2)
            if title_rank(key) > 0 and value.startswith('"'):
                return [(json.loads(value), None)]
        except ValueError:
            pass
        return []
    bare = _JSON_BARE_STRING.match(s)
    if bare:
        try:
            return [(json.loads(bare.group(1)), None)]
        except ValueError:
            return []
    return [] if is_json_doc else None


def _sql_groups(line: str) -> List[str]:
    """Top-level parenthesized groups of a SQL line: "(1,'Glock 19',549.99),(2,...)"."""
    groups = []
    depth = 0
    start = -1
    quote = ""
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                if i + 1 < n and line[i + 1] == quote:
                    i += 1
                else:
                    quote = ""
        elif ch in "'\"`":
            quote = ch
        elif ch == "(":
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                groups.append(line[start:i])
        i += 1
    return groups


def _sql_candidates(line: str, score) -> List[Candidate]:
    groups = _sql_groups(line)
    if not groups:
        # UPDATE ... SET title = '...': take the quoted strings
        strings = [m.group(1).replace("''", "'") for m in re.finditer(r"'((?:[^'\\]|\\.|'')*)'", line)]
        strings = [re.sub(r"\\(.)", r"\1", s) for s in strings]
        c = pick_from_cells(strings, score)
        return [c] if c else []
    out = []
    columns = None
    for g in groups:
        cells = [c.text for c in split_cells(g, ",", "'")]
        if "'" not in g:
            # column list: INSERT INTO products (id, title, price) VALUES ...
            names = [re.sub(r'[`"\[\]]', "", c) for c in cells]
            if all(re.fullmatch(r"[a-z_][\w ]*", n, re.I) for n in names):
                columns = header_columns(names)
                continue
        c = pick_from_cells(cells, score, columns)
        if c:
            out.append(c)
    return out


def _markdown_cells(line: str) -> List[Cell]:
    cells = []
    start = 0
    for i in range(len(line) + 1):
        if i == len(line) or (line[i] == "|" and (i == 0 or line[i - 1] != "\\")):
            cells.append(Cell(line[start:i].replace("\\|", "|").strip(), start, i))
            start = i + 1
    # drop the empty cells before the leading pipe and after the trailing one
    if cells and cells[0].text == "" and re.match(r"^\s*\|", line):
        cells.pop(0)
    if cells and cells[-1].text == "" and re.search(r"\|\s*$", line):
        cells.pop()
    return cells


def _is_markdown_table_row(trimmed: str) -> bool:
    return trimmed.startswith("|") and trimmed.find("|", 1) > 0


def language_for(scope: str = "", file_name: Optional[str] = None) -> str:
    """Language of a view from its base scope ("source.json", "text.html.markdown") and file name."""
    ext = ""
    m = re.search(r"\.([a-z0-9]+)$", file_name or "", re.I)
    if m:
        ext = m.group(1).lower()
    scope = (scope or "").split(" ")[0].lower()
    if ext in ("tsv", "tab") or "tsv" in scope:
        return "tsv"
    if ext in ("csv", "psv") or "csv" in scope:
        return "csv"
    if ext in ("jsonl", "ndjson"):
        return "jsonl"
    if ext in ("json", "json5", "jsonc") or scope.startswith("source.json"):
        return "json"
    if ext == "sql" or scope.startswith("source.sql"):
        return "sql"
    if ext in ("md", "markdown") or scope.startswith("text.html.markdown"):
        return "markdown"
    return "plaintext"


def make_context(language: str, file_name: Optional[str], first_line: Optional[str]) -> Context:
    """Context of a document: whether it is delimited, and the title and price columns of its header row."""
    m = re.search(r"\.([a-z0-9]+)$", file_name or "", re.I)
    ext = m.group(1).lower() if m else ""
    ctx = Context(language)
    delimiter = None
    if language == "tsv" or ext in ("tsv", "tab"):
        delimiter = "\t"
    elif language == "csv" or ext in ("csv", "psv"):
        delimiter = (first_line and detect_delimiter(first_line)) or ("|" if ext == "psv" else ",")
    if first_line and language not in JSON_LANGS and language != "sql" and not _is_markdown_table_row(first_line.strip()):
        d = delimiter or detect_delimiter(first_line)
        if d:
            columns = header_columns([c.text for c in split_cells(first_line, d)])
            if columns:
                delimiter = d
                ctx.columns = columns
                ctx.header_line = 0
    ctx.delimiter = delimiter
    return ctx


def extract_candidates(line: str, line_index: int, ctx: Context, score: Callable[[str], int]) -> List[Candidate]:
    """The records of one line, each as (title, price).

    ``score`` rates how much a text looks like a product title; it picks the title cell when there is no header.
    """
    trimmed = line.strip()
    if not re.search(r"[a-z0-9]", trimmed, re.I) or ctx.header_line == line_index:
        return []

    if ctx.delimiter:
        cells = [c.text for c in split_cells(line, ctx.delimiter)]
        if _is_header_row(cells):
            return []
        c = pick_from_cells(cells, score, ctx.columns)
        return [c] if c else []

    is_json_doc = ctx.language in JSON_LANGS
    if is_json_doc or trimmed[:1] in ("{", "[", '"'):
        found = _json_candidates(trimmed, is_json_doc)
        if found is not None:
            return found

    if "'" in trimmed and (ctx.language == "sql" or re.match(r"(insert|replace)\s+into\b|values\b|\(", trimmed, re.I)):
        return _sql_candidates(trimmed, score)

    if _is_markdown_table_row(trimmed):
        if re.match(r"^\|?\s*:?-{3,}", trimmed):
            return []
        cells = [c.text for c in _markdown_cells(line)]
        if _is_header_row(cells):
            return []
        c = pick_from_cells(cells, score)
        return [c] if c else []

    if "\t" in line:
        c = pick_from_cells([c.text for c in split_cells(line, "\t")], score)
        return [c] if c else []

    price, rest = find_price_in_text(strip_list_marker(trimmed))
    return [(rest, price)] if rest else []
