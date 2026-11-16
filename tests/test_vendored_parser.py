"""The vendored copy of the gunsnprices parser: same answers as the upstream package, and data loading from archives."""
import importlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

import sublime_mock

sublime_mock.install()
gnp = importlib.import_module("GunsNPrices.vendor.gunsnprices")
data_module = importlib.import_module("GunsNPrices.vendor.gunsnprices._data")

HERE = os.path.dirname(os.path.abspath(__file__))
# golden.jsonl is the upstream regression file: 1,150 real store titles with the recorded answers
with open(os.path.join(HERE, "golden.jsonl"), encoding="utf-8") as f:
    CASES = [json.loads(line) for line in f if line.strip()]


def compact(info):
    d = info.to_dict()
    m = d["model"]
    return {"kind": d["kind"], "brand": d["brand"],
            "model": [m["family"], m["model"], m["generation"], m["configs"], m["features"], m["source"]] if m else None,
            "calibers": [c["id"] for c in d["calibers"]], "capacity": d["capacity"], "barrel_length": d["barrel_length"],
            "rounds": d["rounds"], "cost_per_round": d["cost_per_round"]}


class GoldenTest(unittest.TestCase):
    def test_golden_titles(self):
        self.assertEqual(len(CASES), 1150)
        for case in CASES:
            with self.subTest(title=case["args"]["title"]):
                self.assertEqual(compact(gnp.parse_title(**case["args"])), case["expected"])


class ParserTest(unittest.TestCase):
    def test_firearm_title(self):
        info = gnp.parse_title("Glock 19 Gen 5 MOS 9mm 4.02in 15rd Pistol PA195S203MOS")
        self.assertEqual(info.kind, "firearm")
        self.assertEqual(info.model.model, "Glock 19 Gen 5 MOS")
        self.assertEqual(info.caliber.name, "9×19mm Parabellum")
        self.assertEqual((info.capacity, info.barrel_length), (15, 4.02))

    def test_ammo_title_with_price(self):
        info = gnp.parse_title("Federal American Eagle 5.56x45mm 55gr FMJ 1000 Rounds", price=449.99)
        self.assertEqual(info.kind, "ammo")
        self.assertEqual(info.caliber.name, "5.56×45mm NATO")
        self.assertEqual((info.rounds, info.cost_per_round), (1000, 0.45))

    def test_shotgun_gauge_and_barrel(self):
        info = gnp.parse_title('Mossberg 590 Persuader 12/20 BL/SY 3"')
        self.assertEqual(info.barrel_length, 20.0)
        self.assertEqual(info.caliber.name, "12 Gauge")

    def test_calibers(self):
        c = gnp.normalize_caliber("308 WIN (7.62X51 NATO)")
        self.assertEqual((c.id, c.name, c.type), ("308win", ".308 Win", "rifle"))
        self.assertEqual(c.url, "https://gunsnprices.com/ammo/rifle-ammo/308-win")
        self.assertEqual([x.name for x in gnp.find_calibers("Henry Big Boy .44 Mag/.44 Spl 20in")],
                         [".44 Magnum", ".44 S&W Special"])
        self.assertEqual(gnp.find_caliber("Umarex 12g CO2 Cartridges 15 pack"), None)
        self.assertEqual(len(gnp.list_calibers()), 293)

    def test_models(self):
        self.assertEqual(gnp.identify_model("GLOCK 9MM PISTOL 15RD", brand="Glock", mpn="UA4350201").model, "Glock 43")
        self.assertIsNone(gnp.identify_model("Glock 19 holster"))
        self.assertIsNone(gnp.identify_model("Umarex Glock 19 CO2 BB Pistol .177"))
        self.assertEqual(len(gnp.list_brands()), 50)

    def test_version(self):
        self.assertEqual(gnp.__version__, "0.1.2")


class DataLoadingTest(unittest.TestCase):
    """Inside a .sublime-package archive the data files are not on disk."""

    def setUp(self):
        sublime_mock.state.reset()
        self.saved_loader = data_module.__dict__.get("__loader__")

    def tearDown(self):
        data_module.__dict__.pop("open", None)
        data_module.__loader__ = self.saved_loader

    def _no_disk(self):
        def fail(*args, **kwargs):
            raise OSError("not on disk")
        data_module.open = fail

    def test_reads_from_disk(self):
        text = data_module.read_data("calibers.json")
        self.assertEqual(len(json.loads(text)["calibers"]), 293)
        self.assertEqual(sublime_mock.state.resources, [])

    def test_reads_through_the_module_loader(self):
        self._no_disk()
        seen = []

        class ZipLikeLoader(object):
            def get_data(self, path):
                seen.append(path)
                with open(path, "rb") as f:
                    return f.read()

        data_module.__loader__ = ZipLikeLoader()
        text = data_module.read_data("calibers.json")
        self.assertIn('"calibers"', text)
        self.assertTrue(seen[0].endswith(os.path.join("vendor", "gunsnprices", "data", "calibers.json")))
        self.assertEqual(sublime_mock.state.resources, [])

    def test_imports_and_parses_from_a_zip_archive(self):
        """Like an installed .sublime-package: the modules and data files exist only inside a zip file."""
        tmp = tempfile.mkdtemp()
        archive = os.path.join(tmp, "GunsNPrices.sublime-package")
        try:
            with zipfile.ZipFile(archive, "w") as z:
                for folder, _, files in os.walk(os.path.join(sublime_mock.ROOT, "vendor")):
                    for name in files:
                        if not name.endswith(".pyc"):
                            full = os.path.join(folder, name)
                            z.write(full, os.path.relpath(full, sublime_mock.ROOT).replace(os.sep, "/"))
            zipped = None
            for name, path in (("vendor", [archive]), ("vendor.gunsnprices", None)):
                spec = importlib.machinery.PathFinder.find_spec(name, path or zipped.__path__)
                if hasattr(spec.loader, "exec_module"):
                    zipped = importlib.util.module_from_spec(spec)
                    sys.modules[name] = zipped
                    spec.loader.exec_module(zipped)
                else:   # Python 3.8 and 3.9: zipimporter only has the older API
                    zipped = spec.loader.load_module(name)
            self.assertIn(".sublime-package", zipped.__file__)
            self.assertIsNot(zipped, gnp)
            info = zipped.parse_title("Glock 19 Gen 5 MOS 9mm 4.02in 15rd Pistol")
            self.assertEqual((info.model.model, info.caliber.name), ("Glock 19 Gen 5 MOS", "9\u00d719mm Parabellum"))
        finally:
            for name in [m for m in sys.modules if m == "vendor" or m.startswith("vendor.")]:
                del sys.modules[name]
            shutil.rmtree(tmp)

    def test_falls_back_to_sublime_load_resource(self):
        self._no_disk()
        data_module.__loader__ = object()       # a loader without get_data
        text = data_module.read_data("models.json")
        self.assertIn('"dicts"', text)
        self.assertEqual(sublime_mock.state.resources, ["Packages/GunsNPrices/vendor/gunsnprices/data/models.json"])


if __name__ == "__main__":
    unittest.main()
