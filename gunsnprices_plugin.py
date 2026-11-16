"""GunsNPrices for Sublime Text: parse gun and ammo product titles, normalize calibers, cost per round.

Everything runs locally. The parser and its data are vendored in ``vendor/gunsnprices``; the editor-independent logic
is in ``core`` and has its own tests.
"""
import html
import threading
import webbrowser

import sublime
import sublime_plugin

from .core.columns import DEFAULT_COLUMNS, add_spec_columns, annotate_lines
from .core.extract import language_for, make_context, parse_price
from .core.formats import Options, cost_text, popup_html, to_csv, to_json, to_text
from .core.titles import normalize_caliber_text, parse_line, rounds_from
from .vendor.gunsnprices import cost_per_round

SETTINGS_FILE = "GunsNPrices.sublime-settings"
PANEL = "gunsnprices"
REGION_KEY = "gunsnprices_annotations"
# selections with more lines than this are parsed in a worker thread, with progress in the status bar
BACKGROUND_LINES = 300
OUTPUTS = ("auto", "popup", "panel", "json", "csv")

_busy = threading.Event()


# ---------------------------------------------------------------------------------------------------------------------
# helpers

def settings():
    return sublime.load_settings(SETTINGS_FILE)


def options():
    s = settings()
    return Options(links=bool(s.get("caliber_links", False)), ascii_names=bool(s.get("ascii_caliber_names", False)))


def max_lines():
    try:
        return max(1, int(settings().get("max_lines", 20000)))
    except (TypeError, ValueError):
        return 20000


def status(text):
    sublime.status_message("GunsNPrices: " + text)


def notify(view, text):
    """Show a message in the status bar and in a small popup at the cursor, so it is not missed."""
    status(text)
    if view is not None and view.is_valid():
        body = html.escape(text[:1].upper() + text[1:])
        view.show_popup("<body id=\"gunsnprices-message\"><div>%s</div></body>" % body,
                        flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY, location=-1, max_width=640)


def document_name(view):
    return view.file_name() or view.name() or ""


def context_for(view):
    first = view.substr(view.line(0)) if view.size() else ""
    return make_context(language_for(view.scope_name(0), document_name(view)), document_name(view), first)


def line_count(view):
    return view.rowcol(view.size())[0] + 1


def selected_lines(view):
    """Zero-based line numbers covered by the selections; the cursor line for an empty selection."""
    rows = set()
    for r in view.sel():
        begin_row = view.rowcol(r.begin())[0]
        end_row, end_col = view.rowcol(r.end())
        if not r.empty() and end_col == 0 and end_row > begin_row:
            end_row -= 1
        rows.update(range(begin_row, end_row + 1))
    return sorted(rows)


def has_selection(view):
    return any(not r.empty() for r in view.sel())


def read_lines(view, rows):
    """[(row, text)] for the given zero-based rows, read with one API call."""
    if not rows:
        return []
    start = view.text_point(rows[0], 0)
    end = view.line(view.text_point(rows[-1], 0)).end()
    chunk = view.substr(sublime.Region(start, end)).split("\n")
    first = rows[0]
    return [(r, chunk[r - first] if r - first < len(chunk) else "") for r in rows]


def run_in_background(fn):
    t = threading.Thread(target=fn, name="GunsNPrices")
    t.daemon = True
    t.start()


def run_job(view, count, work, done):
    """Run ``work(progress)`` and pass its result to ``done`` on the main thread.

    Small jobs run right away; large ones in a worker thread, one at a time, with progress in the status bar.
    """
    if count <= BACKGROUND_LINES:
        done(work(lambda k: None))
        return
    if _busy.is_set():
        status("still working on the previous command.")
        return
    _busy.set()
    status("parsing %s lines..." % "{:,}".format(count))

    def progress(k):
        if k and k % 2000 == 0:
            status("parsed %s of %s lines..." % ("{:,}".format(k), "{:,}".format(count)))

    def worker():
        try:
            result = work(progress)
        except Exception as e:  # report instead of failing silently in the thread
            _busy.clear()
            message = "parsing failed: %s" % e
            sublime.set_timeout(lambda: notify(view, message), 0)
            raise
        _busy.clear()
        sublime.set_timeout(lambda: done(result), 0)

    run_in_background(worker)


def parse_rows(texts, ctx, progress):
    rows = []
    for k, (row, text) in enumerate(texts):
        if len(text) <= 100000:
            rows.extend(parse_line(text, row, ctx))
        progress(k)
    return rows


def _number(n):
    return ("%.4f" % n).rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------------------------------------------------
# results

def show_popup_for(view, row, opts):
    def on_navigate(href):
        if href == "copy:json":
            sublime.set_clipboard(to_json([row], opts))
            view.hide_popup()
            status("copied the result as JSON.")
        elif href == "copy:csv":
            sublime.set_clipboard(to_csv([row], opts))
            view.hide_popup()
            status("copied the result as CSV.")
        elif href.startswith("https://"):
            webbrowser.open(href)

    view.show_popup(popup_html(row, opts), flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY, location=-1, max_width=640,
                    on_navigate=on_navigate)


def show_panel(window, text):
    panel = window.create_output_panel(PANEL)
    panel.settings().set("word_wrap", False)
    panel.set_read_only(False)
    panel.run_command("gunsnprices_set_text", {"text": text})
    panel.set_read_only(True)
    window.run_command("show_panel", {"panel": "output." + PANEL})


def open_result(window, text, ext):
    view = window.new_file()
    syntax = sublime.find_syntax_for_file("parsed." + ext)
    if syntax is not None:
        view.assign_syntax(syntax)
    view.set_name("Parsed titles." + ext)
    view.run_command("gunsnprices_set_text", {"text": text})
    return view


def show_rows(view, rows, output, note=""):
    opts = options()
    if not rows:
        notify(view, "no product titles found in the selected lines." + note)
        return
    window = view.window() or sublime.active_window()
    if output == "json":
        open_result(window, to_json(rows, opts), "json")
    elif output == "csv":
        open_result(window, to_csv(rows, opts), "csv")
    elif output == "popup" or (output == "auto" and len(rows) == 1):
        show_popup_for(view, rows[0], opts)
    else:
        show_panel(window, to_text(rows, opts))
    status("parsed %d title%s.%s" % (len(rows), "" if len(rows) == 1 else "s", note))


# ---------------------------------------------------------------------------------------------------------------------
# commands

class GunsnpricesParseTitlesCommand(sublime_plugin.TextCommand):
    """Parse the selected lines (or the cursor line).

    ``output``: "auto" (a popup for one title, the output panel for several), "popup", "panel", "json" or "csv"
    (a new tab).
    """

    def run(self, edit, output="auto"):
        if output not in OUTPUTS:
            output = "auto"
        view = self.view
        rows = selected_lines(view)
        limit = max_lines()
        note = ""
        if len(rows) > limit:
            note = " Only the first %s lines were read (setting max_lines)." % "{:,}".format(limit)
            rows = rows[:limit]
        texts = read_lines(view, rows)
        ctx = context_for(view)
        run_job(view, len(texts), lambda progress: parse_rows(texts, ctx, progress),
                lambda result: show_rows(view, result, output, note))


class GunsnpricesNormalizeCaliberCommand(sublime_plugin.TextCommand):
    """Replace each selected caliber (one per line or per selection) with its standard name."""

    def run(self, edit):
        view = self.view
        regions = [r for r in view.sel() if not r.empty()]
        if not regions:
            notify(view, "select the caliber text to normalize, for example 9mm Luger.")
            return
        ascii_names = options().ascii_names
        changed, unknown, ambiguous = [], [], []
        for r in reversed(regions):
            res = normalize_caliber_text(view.substr(r), ascii_names)
            changed[:0] = res.changed
            unknown[:0] = res.unknown
            ambiguous[:0] = res.ambiguous
            if res.changed:
                view.replace(edit, r, res.text)
        parts = []
        if len(changed) == 1:
            parts.append("%s → %s." % changed[0])
        elif changed:
            parts.append("normalized %d calibers." % len(changed))
        if unknown:
            parts.append("Not recognized, left as is: %s." % _quote_list(unknown))
        if ambiguous:
            parts.append("More than one caliber, or more than a caliber, left as is: %s. Select just the caliber."
                         % _quote_list(ambiguous))
        if not parts:
            parts.append("already normalized.")
        text = " ".join(parts)
        if unknown or ambiguous:
            notify(view, text)
        else:
            status(text)


def _quote_list(values):
    shown = ['"%s"' % (v if len(v) <= 40 else v[:37] + "...") for v in values[:5]]
    return ", ".join(shown) + (" and %d more" % (len(values) - 5) if len(values) > 5 else "")


class _PriceInput(sublime_plugin.TextInputHandler):
    def __init__(self, view, initial_price, initial_rounds, need_rounds):
        self.view = view
        self.initial_price = initial_price
        self.initial_rounds = initial_rounds
        self.need_rounds = need_rounds

    def name(self):
        return "price"

    def placeholder(self):
        return "Price of the box or case, e.g. 18.99"

    def initial_text(self):
        return self.initial_price

    def validate(self, text):
        return parse_price(text) is not None

    def preview(self, text):
        p = parse_price(text)
        return "Price: %s" % ("${:,.2f}".format(p) if p is not None else "enter a price, for example 18.99")

    def next_input(self, args):
        if self.need_rounds:
            return _RoundsInput(self.view, self.initial_rounds, parse_price(args.get("price")))
        return None


class _RoundsInput(sublime_plugin.TextInputHandler):
    def __init__(self, view, initial_rounds, price):
        self.view = view
        self.initial_rounds = initial_rounds
        self.price = price

    def name(self):
        return "rounds"

    def placeholder(self):
        return "Rounds in the box (50), or the product title"

    def initial_text(self):
        return self.initial_rounds

    def validate(self, text):
        return rounds_from(text) is not None

    def preview(self, text):
        n = rounds_from(text)
        if n is None:
            return 'Enter a number of rounds, or a title that has one ("50 Rounds", "20/box").'
        if self.price:
            return cost_text(self.price, n, cost_per_round(self.price, n))
        return "%d rounds" % n


class GunsnpricesCostPerRoundCommand(sublime_plugin.TextCommand):
    """Cost per round from a price and a round count (or a title with the count in it).

    From the Command Palette it asks for both, prefilled from the cursor line.
    """

    def run(self, edit, price=None, rounds=None):
        p = parse_price(price)
        n = rounds_from(str(rounds)) if rounds is not None else None
        if p is None:
            notify(self.view, "not a price: %s" % price)
            return
        if not n:
            notify(self.view, 'no round count in "%s". Enter a number, for example 50.' % rounds)
            return
        cpr = cost_per_round(p, n)
        text = cost_text(p, n, cpr)
        status(text)

        def on_navigate(href):
            if href == "copy":
                sublime.set_clipboard(_number(cpr))
                self.view.hide_popup()
                status("copied %s." % _number(cpr))

        self.view.show_popup(
            "<body id=\"gunsnprices-cost\"><div>%s</div><div><a href=\"copy\">Copy %s</a></div></body>"
            % (html.escape(text), _number(cpr)),
            flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY, location=-1, max_width=640, on_navigate=on_navigate)

    def input(self, args):
        if "price" in args and "rounds" in args:
            return None
        price, rounds = "", ""
        view = self.view
        if len(view.sel()):
            row = view.rowcol(view.sel()[0].begin())[0]
            found = parse_line(read_lines(view, [row])[0][1], row, context_for(view))
            if found:
                if found[0].price:
                    price = _number(found[0].price)
                if found[0].info.rounds:
                    rounds = str(found[0].info.rounds)
        if "price" not in args:
            return _PriceInput(view, price, rounds, "rounds" not in args)
        return _RoundsInput(view, rounds, parse_price(args["price"]))

    def input_description(self):
        return "Cost per Round"


class GunsnpricesAnnotateLinesCommand(sublime_plugin.TextCommand):
    """Show the parsed specs at the end of each selected line, or of every line when nothing is selected."""

    def run(self, edit):
        view = self.view
        total = line_count(view)
        limit = max_lines()
        rows = selected_lines(view) if has_selection(view) else list(range(total))
        note = ""
        if len(rows) > limit:
            note = " Only the first %s lines were read (setting max_lines)." % "{:,}".format(limit)
            rows = rows[:limit]
        texts = read_lines(view, rows)
        ctx = context_for(view)
        opts = options()

        def work(progress):
            out = []
            for k in range(0, len(texts), 500):
                out.extend(annotate_lines(texts[k:k + 500], ctx, opts))
                progress(k + 500)
            return out

        def done(notes):
            if not view.is_valid():
                return
            regions = [view.line(view.text_point(row, 0)) for row, _ in notes]
            color = view.style_for_scope("comment").get("foreground", "")
            view.add_regions(REGION_KEY, regions, scope="comment",
                             flags=sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE,
                             annotations=[html.escape(t) for _, t in notes], annotation_color=color)
            if notes:
                status("annotated %d of %d lines. Run GunsNPrices: Clear Annotations to remove them.%s"
                       % (len(notes), len(texts), note))
            else:
                notify(view, "no gun or ammo titles found in %d lines.%s" % (len(texts), note))

        run_job(view, len(texts), work, done)


class GunsnpricesClearAnnotationsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.erase_regions(REGION_KEY)
        status("annotations cleared.")


class GunsnpricesAddColumnsCommand(sublime_plugin.TextCommand):
    """Append parsed spec columns (setting spec_columns) to every row of a CSV or TSV file."""

    def run(self, edit):
        view = self.view
        total = line_count(view)
        limit = max_lines()
        if total > limit:
            notify(view, "the file has %s lines, more than max_lines (%s). Raise max_lines in the settings to add "
                         "columns to all rows." % ("{:,}".format(total), "{:,}".format(limit)))
            return
        lines = [t for _, t in read_lines(view, list(range(total)))]
        ctx = context_for(view)
        columns = settings().get("spec_columns") or DEFAULT_COLUMNS
        opts = options()
        change_count = view.change_count()

        def done(res):
            if res.error:
                notify(view, res.error)
                return
            view.run_command("gunsnprices_append_to_lines", {"suffixes": res.suffixes, "change_count": change_count})
            status("added %d columns to %d rows%s." % (
                len(columns), res.rows, (" (%d rows without a title got empty cells)" % res.empty) if res.empty else ""))

        run_job(view, total, lambda progress: add_spec_columns(lines, ctx, columns, opts), done)


class GunsnpricesAppendToLinesCommand(sublime_plugin.TextCommand):
    """Internal: append text to the end of lines, as one undo step. Used by Add Spec Columns."""

    def run(self, edit, suffixes, change_count=None):
        view = self.view
        if change_count is not None and view.change_count() != change_count:
            notify(view, "the file changed while it was being parsed. Run the command again.")
            return
        for row, text in sorted(suffixes, reverse=True):
            view.insert(edit, view.line(view.text_point(row, 0)).end(), text)


class GunsnpricesSetTextCommand(sublime_plugin.TextCommand):
    """Internal: replace the whole text of a result view or the output panel."""

    def run(self, edit, text):
        self.view.replace(edit, sublime.Region(0, self.view.size()), text)
