"""Read the data files that ship with this copy of the parser.

Sublime Text packages are usually installed as ``.sublime-package`` zip archives, where the files are not on disk and
``importlib.resources.files`` (Python 3.9+) is not available on the 3.8 plugin host. The files are read from disk when
the package is unpacked (and in tests), otherwise through the module loader or ``sublime.load_resource``.
"""
import os

__all__ = ["read_data"]


def read_data(name):
    """Text of ``data/<name>`` next to this module."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "data", name)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        pass
    loader = globals().get("__loader__")
    get_data = getattr(loader, "get_data", None)
    if get_data is not None:
        try:
            return get_data(path).decode("utf-8")
        except (OSError, TypeError, ValueError, AttributeError, KeyError):
            pass
    # Packages/<Package>/<subpackage path>/data/<name>; __package__ is "<Package>.vendor.gunsnprices"
    import sublime  # only reached inside Sublime Text, when the package is a zip archive

    resource = "/".join(["Packages"] + (__package__ or "").split(".") + ["data", name])
    return sublime.load_resource(resource)
