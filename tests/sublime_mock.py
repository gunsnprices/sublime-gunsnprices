"""Small stand-ins for Sublime Text's ``sublime`` and ``sublime_plugin`` modules, enough to run the commands in tests.

Only what the package uses is implemented. Text positions, lines and rows behave like Sublime Text's: a buffer uses
"\\n" line endings, ``line(pt)`` excludes the newline, ``rowcol``/``text_point`` are zero-based.
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sublime = types.ModuleType("sublime")
sublime_plugin = types.ModuleType("sublime_plugin")

HIDE_ON_MOUSE_MOVE_AWAY = 2
DRAW_NO_FILL = 32
DRAW_NO_OUTLINE = 256


class Region(object):
    def __init__(self, a, b=None):
        self.a = a
        self.b = a if b is None else b

    def begin(self):
        return min(self.a, self.b)

    def end(self):
        return max(self.a, self.b)

    def empty(self):
        return self.a == self.b

    def size(self):
        return self.end() - self.begin()

    def __eq__(self, other):
        return isinstance(other, Region) and (self.a, self.b) == (other.a, other.b)

    def __repr__(self):
        return "Region(%d, %d)" % (self.a, self.b)


class Selection(list):
    def add(self, region):
        self.append(region if isinstance(region, Region) else Region(region))

    def clear(self):
        del self[:]


class Settings(object):
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class Edit(object):
    pass


class Syntax(object):
    def __init__(self, path, scope):
        self.path = path
        self.scope = scope


class View(object):
    def __init__(self, text="", file_name=None, scope="text.plain", window=None):
        self.text = text
        self._file_name = file_name
        self._name = ""
        self.scope = scope
        self._window = window
        self._sel = Selection([Region(0)])
        self._settings = Settings()
        self.read_only = False
        self.syntax = None
        self.popups = []            # [(html, kwargs)]
        self.popup_visible = False
        self.regions = {}           # key -> (regions, kwargs)
        self._change_count = 0
        self.valid = True

    # --- text and positions
    def is_valid(self):
        return self.valid

    def size(self):
        return len(self.text)

    def substr(self, x):
        if isinstance(x, Region):
            return self.text[x.begin():x.end()]
        return self.text[x:x + 1]

    def _line_bounds(self, pt):
        pt = max(0, min(pt, len(self.text)))
        start = self.text.rfind("\n", 0, pt) + 1
        end = self.text.find("\n", pt)
        return start, (len(self.text) if end < 0 else end)

    def line(self, x):
        if isinstance(x, Region):
            return Region(self._line_bounds(x.begin())[0], self._line_bounds(x.end())[1])
        return Region(*self._line_bounds(x))

    def rowcol(self, pt):
        pt = max(0, min(pt, len(self.text)))
        row = self.text.count("\n", 0, pt)
        return row, pt - (self.text.rfind("\n", 0, pt) + 1)

    def text_point(self, row, col):
        lines = self.text.split("\n")
        if row >= len(lines):
            return len(self.text)
        return sum(len(x) + 1 for x in lines[:row]) + min(col, len(lines[row]))

    def sel(self):
        return self._sel

    def select(self, *regions):
        """Test helper: set the selection to ``(a, b)`` tuples or points."""
        self._sel.clear()
        for r in regions:
            self._sel.add(Region(*r) if isinstance(r, tuple) else Region(r))

    def select_lines(self, first, last):
        """Test helper: select whole lines first..last (inclusive), like dragging over them."""
        self.select((self.text_point(first, 0), self.line(self.text_point(last, 0)).end()))

    # --- metadata
    def scope_name(self, pt):
        return self.scope + " "

    def file_name(self):
        return self._file_name

    def name(self):
        return self._name

    def set_name(self, name):
        self._name = name

    def window(self):
        return self._window

    def settings(self):
        return self._settings

    def set_read_only(self, value):
        self.read_only = value

    def assign_syntax(self, syntax):
        self.syntax = syntax

    def change_count(self):
        return self._change_count

    def style_for_scope(self, scope):
        return {"foreground": "#808080"}

    # --- UI
    def show_popup(self, content, flags=0, location=-1, max_width=320, max_height=240, on_navigate=None,
                   on_hide=None):
        self.popups.append((content, {"flags": flags, "location": location, "on_navigate": on_navigate}))
        self.popup_visible = True

    def hide_popup(self):
        self.popup_visible = False

    def add_regions(self, key, regions, scope="", icon="", flags=0, annotations=None, annotation_color=""):
        self.regions[key] = (list(regions), {"scope": scope, "flags": flags, "annotations": list(annotations or []),
                                             "annotation_color": annotation_color})

    def get_regions(self, key):
        return self.regions.get(key, ([], {}))[0]

    def erase_regions(self, key):
        self.regions.pop(key, None)

    # --- editing
    def _check_edit(self, edit):
        if not isinstance(edit, Edit):
            raise ValueError("edit object required")
        if self.read_only:
            raise ValueError("view is read-only")

    def replace(self, edit, region, text):
        self._check_edit(edit)
        self.text = self.text[:region.begin()] + text + self.text[region.end():]
        self._change_count += 1

    def insert(self, edit, pt, text):
        self._check_edit(edit)
        self.text = self.text[:pt] + text + self.text[pt:]
        self._change_count += 1
        return len(text)

    def run_command(self, name, args=None):
        cls = _commands["text"].get(name)
        if cls is None:
            raise KeyError("no text command %r" % name)
        cls(self).run(Edit(), **(args or {}))


class Window(object):
    def __init__(self):
        self.views = []
        self.panels = {}
        self.shown_panel = None

    def new_file(self):
        v = View(window=self)
        self.views.append(v)
        return v

    def create_output_panel(self, name, unlisted=False):
        if name not in self.panels:
            self.panels[name] = View(window=self)
        return self.panels[name]

    def find_output_panel(self, name):
        return self.panels.get(name)

    def active_view(self):
        return self.views[-1] if self.views else None

    def run_command(self, name, args=None):
        if name == "show_panel":
            self.shown_panel = (args or {}).get("panel")
        else:
            raise KeyError("no window command %r" % name)


# --- module-level state and functions of ``sublime``

class State(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.settings = {}
        self.status = []
        self.clipboard = ""
        self.window = Window()
        self.resources = []


state = State()


def load_settings(name):
    return state.settings.setdefault(name, Settings())


def status_message(text):
    state.status.append(text)


def set_timeout(fn, delay=0):
    fn()


def set_timeout_async(fn, delay=0):
    fn()


def set_clipboard(text):
    state.clipboard = text


def get_clipboard():
    return state.clipboard


def active_window():
    return state.window


def find_syntax_for_file(path, first_line=""):
    if path.endswith(".json"):
        return Syntax("Packages/JSON/JSON.sublime-syntax", "source.json")
    return Syntax("Packages/Text/Plain text.tmLanguage", "text.plain")


def load_resource(name):
    """Packages/GunsNPrices/<path> is read from the repository."""
    state.resources.append(name)
    prefix = "Packages/GunsNPrices/"
    if not name.startswith(prefix):
        raise IOError("resource not found: " + name)
    with open(os.path.join(ROOT, *name[len(prefix):].split("/")), encoding="utf-8") as f:
        return f.read()


for _name, _value in list(globals().items()):
    if _name in ("Region", "Selection", "Settings", "Edit", "Syntax", "View", "Window", "load_settings",
                 "status_message", "set_timeout", "set_timeout_async", "set_clipboard", "get_clipboard",
                 "active_window", "find_syntax_for_file", "load_resource", "HIDE_ON_MOUSE_MOVE_AWAY",
                 "DRAW_NO_FILL", "DRAW_NO_OUTLINE", "state"):
        setattr(sublime, _name, _value)


# --- ``sublime_plugin``

_commands = {"text": {}, "window": {}, "application": {}}


def command_name(class_name):
    """The command name Sublime Text derives from a command class name (same algorithm as sublime_plugin.py)."""
    name = class_name[0].lower()
    last_upper = False
    for c in class_name[1:]:
        if c.isupper() and not last_upper:
            name += "_" + c.lower()
        else:
            name += c
        last_upper = c.isupper()
    if name.endswith("_command"):
        name = name[:-8]
    return name


class Command(object):
    kind = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.kind and cls.__module__ != __name__ and cls.__name__.endswith("Command"):
            _commands[cls.kind][command_name(cls.__name__)] = cls

    def name(self):
        return command_name(self.__class__.__name__)


class TextCommand(Command):
    kind = "text"

    def __init__(self, view):
        self.view = view


class WindowCommand(Command):
    kind = "window"

    def __init__(self, window):
        self.window = window


class ApplicationCommand(Command):
    kind = "application"


class TextInputHandler(object):
    def name(self):
        return None

    def placeholder(self):
        return ""

    def initial_text(self):
        return ""

    def validate(self, text):
        return True

    def preview(self, text):
        return ""

    def next_input(self, args):
        return None


class EventListener(object):
    pass


for _name in ("TextCommand", "WindowCommand", "ApplicationCommand", "TextInputHandler", "EventListener",
              "command_name"):
    setattr(sublime_plugin, _name, globals()[_name])
sublime_plugin.commands = _commands


def install():
    """Register the mock modules and a ``GunsNPrices`` package rooted at the repository, as Sublime Text does."""
    sys.modules.setdefault("sublime", sublime)
    sys.modules.setdefault("sublime_plugin", sublime_plugin)
    if "GunsNPrices" not in sys.modules:
        pkg = types.ModuleType("GunsNPrices")
        pkg.__path__ = [ROOT]
        pkg.__package__ = "GunsNPrices"
        sys.modules["GunsNPrices"] = pkg
