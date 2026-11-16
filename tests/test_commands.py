"""The Sublime Text commands, run against the mock ``sublime`` / ``sublime_plugin`` modules."""
import html
import importlib
import json
import os
import re
import unittest

import sublime_mock

sublime_mock.install()
plugin = importlib.import_module("GunsNPrices.gunsnprices_plugin")
sublime = sublime_mock.sublime
state = sublime_mock.state

NINE = "9×19mm Parabellum"
NINE_URL = "https://gunsnprices.com/ammo/handgun-ammo/9-19mm-parabellum"
GLOCK = 'Glock 19 Gen 5 MOS 9mm 4.02" 15rd Pistol'
AMMO = "Federal American Eagle 9mm Luger 115gr FMJ 50 Rounds $18.99"


class CommandTestCase(unittest.TestCase):
    def setUp(self):
        state.reset()
        self.background = []
        plugin._busy.clear()
        self.saved_runner = plugin.run_in_background

        def run_now(fn):
            self.background.append(fn)
            fn()

        plugin.run_in_background = run_now

    def tearDown(self):
        plugin.run_in_background = self.saved_runner

    def view(self, text, file_name=None, scope="text.plain"):
        v = sublime.View(text, file_name=file_name, scope=scope, window=state.window)
        state.window.views.append(v)
        return v

    def set(self, **values):
        sublime.load_settings(plugin.SETTINGS_FILE).values.update(values)

    def last_popup(self, view):
        """(content with HTML entities decoded, keyword arguments) of the last popup."""
        self.assertTrue(view.popups, "no popup shown")
        content, kw = view.popups[-1]
        return html.unescape(content), kw


class ParseTitlesTest(CommandTestCase):
    def test_one_title_opens_a_popup_with_copy_links(self):
        v = self.view(GLOCK + "\n" + AMMO)
        v.run_command("gunsnprices_parse_titles")
        content, kw = self.last_popup(v)
        self.assertIn("<h1>Glock 19 Gen 5 MOS</h1>", content)
        self.assertIn(NINE, content)
        self.assertEqual(kw["location"], -1)
        kw["on_navigate"]("copy:json")
        data = json.loads(state.clipboard)
        self.assertEqual((data[0]["line"], data[0]["model"]["model"], data[0]["capacity"]), (1, "Glock 19 Gen 5 MOS", 15))
        self.assertFalse(v.popup_visible)
        kw["on_navigate"]("copy:csv")
        self.assertTrue(state.clipboard.startswith("line,title,kind,"))
        self.assertEqual(state.status[-1], "GunsNPrices: copied the result as CSV.")

    def test_several_lines_go_to_the_output_panel(self):
        v = self.view(GLOCK + "\n" + AMMO + "\n")
        v.select_lines(0, 1)
        v.run_command("gunsnprices_parse_titles", {"output": "auto"})
        self.assertEqual(state.window.shown_panel, "output.gunsnprices")
        panel = state.window.panels["gunsnprices"]
        self.assertTrue(panel.read_only)
        self.assertIn("Line 1: " + GLOCK, panel.text)
        self.assertIn("Line 2: Federal American Eagle 9mm Luger 115gr FMJ 50 Rounds\n", panel.text)
        self.assertIn("Cost per round: $0.38", panel.text)
        self.assertEqual(state.status[-1], "GunsNPrices: parsed 2 titles.")
        # running again replaces the panel text
        v.select(0)
        v.run_command("gunsnprices_parse_titles", {"output": "panel"})
        self.assertNotIn("Line 2:", panel.text)

    def test_selection_ending_at_the_start_of_a_line_does_not_include_it(self):
        v = self.view(GLOCK + "\n" + AMMO)
        v.select((0, v.text_point(1, 0)))
        self.assertEqual(plugin.selected_lines(v), [0])
        v.select((v.text_point(1, 3), 2), (5, 7))
        self.assertEqual(plugin.selected_lines(v), [0, 1])

    def test_json_and_csv_open_new_tabs(self):
        v = self.view(GLOCK + "\n" + AMMO)
        v.select_lines(0, 1)
        v.run_command("gunsnprices_parse_titles", {"output": "json"})
        out = state.window.views[-1]
        self.assertEqual(out.name(), "Parsed titles.json")
        self.assertEqual(out.syntax.scope, "source.json")
        data = json.loads(out.text)
        self.assertEqual([d["kind"] for d in data], ["firearm", "ammo"])
        self.assertEqual(data[1]["price"], 18.99)
        self.assertNotIn("url", data[0]["caliber"])

        self.set(caliber_links=True, ascii_caliber_names=True)
        v.run_command("gunsnprices_parse_titles", {"output": "csv"})
        out = state.window.views[-1]
        self.assertEqual(out.name(), "Parsed titles.csv")
        lines = out.text.split("\n")
        self.assertTrue(lines[0].endswith(",caliber_url"))
        self.assertTrue(lines[1].endswith("," + NINE_URL))
        self.assertIn(",9x19mm Parabellum,", lines[1])

    def test_csv_document_uses_the_header(self):
        v = self.view("id,title,price\n5,PMC Bronze 5.56 NATO 55gr FMJ 20rd,9.99\n", file_name="/feeds/ammo.csv")
        v.select(v.text_point(1, 4))
        v.run_command("gunsnprices_parse_titles")
        content, _ = self.last_popup(v)
        self.assertIn("Ammo · 5.56×45mm NATO · 20 rounds", content)
        self.assertIn("Cost per round:</span> $0.50 (49.95¢)", content)
        # the header row on its own gives nothing
        v.select(1)
        v.run_command("gunsnprices_parse_titles")
        self.assertIn("No product titles found", self.last_popup(v)[0])

    def test_caliber_links_in_the_popup_open_the_browser(self):
        self.set(caliber_links=True)
        opened = []
        saved = plugin.webbrowser.open
        plugin.webbrowser.open = opened.append
        try:
            v = self.view(GLOCK)
            v.run_command("gunsnprices_parse_titles", {"output": "popup"})
            content, kw = self.last_popup(v)
            self.assertIn('<a href="%s">' % NINE_URL, content)
            kw["on_navigate"](NINE_URL)
            kw["on_navigate"]("javascript:alert(1)")
            self.assertEqual(opened, [NINE_URL])
        finally:
            plugin.webbrowser.open = saved

    def test_max_lines_limits_the_selection(self):
        self.set(max_lines=1)
        v = self.view(GLOCK + "\n" + AMMO)
        v.select_lines(0, 1)
        v.run_command("gunsnprices_parse_titles", {"output": "json"})
        self.assertEqual(len(json.loads(state.window.views[-1].text)), 1)
        self.assertIn("Only the first 1 lines were read", state.status[-1])

    def test_large_selection_runs_in_the_background(self):
        v = self.view("\n".join([GLOCK, AMMO] * 200))
        v.select((0, v.size()))
        v.run_command("gunsnprices_parse_titles", {"output": "json"})
        self.assertEqual(len(self.background), 1)
        self.assertEqual(len(json.loads(state.window.views[-1].text)), 400)
        self.assertIn("GunsNPrices: parsing 400 lines...", state.status)
        self.assertFalse(plugin._busy.is_set())

    def test_one_background_job_at_a_time(self):
        plugin._busy.set()
        v = self.view("\n".join([GLOCK] * 400))
        v.select((0, v.size()))
        v.run_command("gunsnprices_parse_titles")
        self.assertEqual(self.background, [])
        self.assertEqual(state.status[-1], "GunsNPrices: still working on the previous command.")

    def test_unknown_output_falls_back_to_auto(self):
        v = self.view(GLOCK)
        v.run_command("gunsnprices_parse_titles", {"output": "xml"})
        self.assertIn("Glock 19 Gen 5 MOS", self.last_popup(v)[0])


class NormalizeCaliberTest(CommandTestCase):
    def test_lines_in_a_selection(self):
        v = self.view("9mm Luger\n12ga\nbar\n")
        v.select((0, v.size()))
        v.run_command("gunsnprices_normalize_caliber")
        self.assertEqual(v.text, "%s\n12 Gauge\nbar\n" % NINE)
        self.assertIn('Not recognized, left as is: "bar"', self.last_popup(v)[0])

    def test_several_selections_and_ascii_names(self):
        self.set(ascii_caliber_names=True)
        v = self.view('caliber: "9mm Luger", alt: "45 auto"')
        a = v.text.index("9mm Luger")
        b = v.text.index("45 auto")
        v.select((a, a + len("9mm Luger")), (b, b + len("45 auto")))
        v.run_command("gunsnprices_normalize_caliber")
        self.assertEqual(v.text, 'caliber: "9x19mm Parabellum", alt: ".45 ACP"')
        self.assertEqual(state.status[-1], "GunsNPrices: normalized 2 calibers.")
        self.assertEqual(v.popups, [])

    def test_one_value(self):
        v = self.view("300 BLK")
        v.select((0, 7))
        v.run_command("gunsnprices_normalize_caliber")
        self.assertEqual(v.text, ".300 AAC Blackout")
        self.assertEqual(state.status[-1], "GunsNPrices: 300 BLK → .300 AAC Blackout.")

    def test_whole_titles_are_left_alone(self):
        v = self.view("Federal 9mm Luger 115gr FMJ 50 Rounds")
        v.select((0, v.size()))
        v.run_command("gunsnprices_normalize_caliber")
        self.assertEqual(v.text, "Federal 9mm Luger 115gr FMJ 50 Rounds")
        self.assertIn("More than one caliber, or more than a caliber", self.last_popup(v)[0])
        self.assertEqual(v.change_count(), 0)

    def test_needs_a_selection(self):
        v = self.view("9mm Luger")
        v.run_command("gunsnprices_normalize_caliber")
        self.assertIn("Select the caliber text to normalize", self.last_popup(v)[0])
        self.assertEqual(v.text, "9mm Luger")


class CostPerRoundTest(CommandTestCase):
    def command(self, view):
        return plugin.GunsnpricesCostPerRoundCommand(view)

    def test_with_arguments(self):
        v = self.view("")
        v.run_command("gunsnprices_cost_per_round", {"price": "$18.99", "rounds": "50"})
        content, kw = self.last_popup(v)
        self.assertIn("$18.99 for 50 rounds = $0.38 (37.98¢) per round", content)
        kw["on_navigate"]("copy")
        self.assertEqual(state.clipboard, "0.3798")
        v.run_command("gunsnprices_cost_per_round", {"price": 289.99, "rounds": "Winchester 9mm 115gr FMJ 1000 Round Case"})
        self.assertIn("$289.99 for 1,000 rounds = $0.29 (29.00¢) per round", self.last_popup(v)[0])

    def test_bad_arguments(self):
        v = self.view("")
        v.run_command("gunsnprices_cost_per_round", {"price": "abc", "rounds": "50"})
        self.assertIn("Not a price: abc", self.last_popup(v)[0])
        v.run_command("gunsnprices_cost_per_round", {"price": "10", "rounds": "Glock 19"})
        self.assertIn('No round count in "Glock 19"', self.last_popup(v)[0])

    def test_input_handlers_are_prefilled_from_the_cursor_line(self):
        v = self.view("x\n" + AMMO)
        v.select(v.text_point(1, 5))
        cmd = self.command(v)
        price = cmd.input({})
        self.assertEqual((price.name(), price.initial_text()), ("price", "18.99"))
        self.assertTrue(price.validate("$18.99"))
        self.assertFalse(price.validate("abc"))
        self.assertEqual(price.preview("1299.5"), "Price: $1,299.50")
        rounds = price.next_input({"price": "18.99"})
        self.assertEqual((rounds.name(), rounds.initial_text()), ("rounds", "50"))
        self.assertTrue(rounds.validate("Box of 20"))
        self.assertFalse(rounds.validate("many"))
        self.assertEqual(rounds.preview("50"), "$18.99 for 50 rounds = $0.38 (37.98¢) per round")
        self.assertIn("Enter a number of rounds", rounds.preview("many"))
        self.assertEqual(cmd.input_description(), "Cost per Round")

    def test_input_handlers_for_missing_arguments(self):
        v = self.view("Glock 19")
        cmd = self.command(v)
        self.assertIsNone(cmd.input({"price": "1", "rounds": "2"}))
        price = cmd.input({"rounds": "50"})
        self.assertEqual(price.initial_text(), "")
        self.assertIsNone(price.next_input({"price": "10", "rounds": "50"}))
        rounds = cmd.input({"price": "10"})
        self.assertEqual(rounds.name(), "rounds")
        self.assertEqual(rounds.preview("40"), "$10.00 for 40 rounds = $0.25 (25.00¢) per round")


class AnnotateTest(CommandTestCase):
    def test_whole_file_and_clear(self):
        v = self.view(GLOCK + "\nhello world 380 people\n" + AMMO)
        v.run_command("gunsnprices_annotate_lines")
        regions, kw = v.regions[plugin.REGION_KEY]
        self.assertEqual(regions, [v.line(0), v.line(v.text_point(2, 0))])
        self.assertEqual(kw["annotations"], ['Glock 19 Gen 5 MOS · %s · 15 rd · 4.02&quot;' % NINE,
                                             "ammo · %s · 50 rd · $0.38/rd" % NINE])
        self.assertEqual(kw["flags"], sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE)
        self.assertIn("annotated 2 of 3 lines", state.status[-1])
        v.run_command("gunsnprices_clear_annotations")
        self.assertNotIn(plugin.REGION_KEY, v.regions)

    def test_selected_lines_only(self):
        v = self.view(GLOCK + "\n" + AMMO)
        v.select((v.text_point(1, 0), v.text_point(1, 4)))
        v.run_command("gunsnprices_annotate_lines")
        regions, _ = v.regions[plugin.REGION_KEY]
        self.assertEqual(regions, [v.line(v.text_point(1, 0))])

    def test_nothing_found(self):
        v = self.view("just some text\nmore text")
        v.run_command("gunsnprices_annotate_lines")
        self.assertIn("No gun or ammo titles found in 2 lines", self.last_popup(v)[0])

    def test_large_file_in_the_background(self):
        v = self.view("\n".join([GLOCK, "nothing here"] * 300))
        v.run_command("gunsnprices_annotate_lines")
        self.assertEqual(len(self.background), 1)
        self.assertEqual(len(v.regions[plugin.REGION_KEY][0]), 300)

    def test_closed_view_is_skipped(self):
        v = self.view("\n".join([GLOCK] * 400))
        v.valid = False
        v.run_command("gunsnprices_annotate_lines")
        self.assertNotIn(plugin.REGION_KEY, v.regions)


class AddColumnsTest(CommandTestCase):
    CSV = "sku,title,price\nA1,Glock 19 Gen 5 9mm 4.02in 15rd,529.99\n\nA2,\"Federal 9mm 115gr FMJ, 50 Rounds\",18.99\n"

    def test_appends_columns_to_every_row(self):
        v = self.view(self.CSV, file_name="/feeds/feed.csv")
        v.run_command("gunsnprices_add_columns")
        lines = v.text.split("\n")
        self.assertEqual(lines[0], "sku,title,price,parsed_kind,parsed_brand,parsed_model,parsed_caliber,"
                                   "parsed_capacity,parsed_barrel_in,parsed_rounds,parsed_cost_per_round")
        self.assertEqual(lines[1], "A1,Glock 19 Gen 5 9mm 4.02in 15rd,529.99,firearm,Glock,Glock 19 Gen 5,%s,15,4.02,,"
                         % NINE)
        self.assertEqual(lines[2], "")
        self.assertEqual(lines[3], 'A2,"Federal 9mm 115gr FMJ, 50 Rounds",18.99,ammo,,,%s,,,50,0.3798' % NINE)
        self.assertEqual(lines[4], "")
        self.assertEqual(state.status[-1], "GunsNPrices: added 8 columns to 2 rows.")
        # a second run is refused and changes nothing
        before = v.text
        v.run_command("gunsnprices_add_columns")
        self.assertEqual(v.text, before)
        self.assertIn("already has the parsed_kind columns", self.last_popup(v)[0])

    def test_untitled_csv_with_a_header_and_custom_columns(self):
        self.set(spec_columns=["caliber", "caliber_type"])
        v = self.view("name\tprice\nHornady Critical Defense 380 ACP 90gr FTX 25rd\t24.99")
        v.run_command("gunsnprices_add_columns")
        self.assertEqual(v.text, "name\tprice\tparsed_caliber\tparsed_caliber_type\n"
                                 "Hornady Critical Defense 380 ACP 90gr FTX 25rd\t24.99\t.380 ACP\thandgun")

    def test_plain_text_is_refused(self):
        v = self.view(GLOCK + "\n" + AMMO, file_name="/x/titles.txt")
        v.run_command("gunsnprices_add_columns")
        self.assertEqual(v.text, GLOCK + "\n" + AMMO)
        self.assertIn("works on CSV and TSV files", self.last_popup(v)[0])

    def test_too_many_lines(self):
        self.set(max_lines=2)
        v = self.view(self.CSV, file_name="feed.csv")
        v.run_command("gunsnprices_add_columns")
        self.assertIn("more than max_lines", self.last_popup(v)[0])
        self.assertEqual(v.change_count(), 0)

    def test_file_changed_while_parsing(self):
        v = self.view(self.CSV, file_name="feed.csv")
        v.run_command("gunsnprices_append_to_lines", {"suffixes": [[0, ",x"]], "change_count": 5})
        self.assertEqual(v.text, self.CSV)
        self.assertIn("The file changed while it was being parsed", self.last_popup(v)[0])

    def test_large_file_in_the_background(self):
        body = "\n".join("%d,Federal 9mm 115gr FMJ 50 Rounds,18.99" % i for i in range(400))
        v = self.view("id,title,price\n" + body, file_name="feed.csv")
        v.run_command("gunsnprices_add_columns")
        self.assertEqual(len(self.background), 1)
        self.assertTrue(all(line.endswith(",ammo,,,%s,,,50,0.3798" % NINE) for line in v.text.split("\n")[1:]))


def _json_with_comments(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return json.loads(text)


class PackageFilesTest(unittest.TestCase):
    ROOT = sublime_mock.ROOT

    def path(self, *parts):
        return os.path.join(self.ROOT, *parts)

    def test_command_palette_entries_point_to_commands(self):
        entries = _json_with_comments(self.path("Default.sublime-commands"))
        known = set(sublime_mock.sublime_plugin.commands["text"])
        for e in entries:
            if e["command"] == "edit_settings":
                self.assertEqual(e["caption"], "Preferences: GunsNPrices Settings")
                self.assertEqual(e["args"]["base_file"], "${packages}/GunsNPrices/GunsNPrices.sublime-settings")
            else:
                self.assertTrue(e["caption"].startswith("GunsNPrices: "), e)
                self.assertIn(e["command"], known)
                self.assertIn(e.get("args", {}).get("output", "auto"), plugin.OUTPUTS)
        # every public command is in the palette; the internal ones are not
        used = {e["command"] for e in entries}
        self.assertEqual(known - used, {"gunsnprices_append_to_lines", "gunsnprices_set_text"})

    def test_all_commands_share_one_prefix(self):
        for name in sublime_mock.sublime_plugin.commands["text"]:
            self.assertTrue(name.startswith("gunsnprices_"), name)

    def test_settings_menu(self):
        menu = _json_with_comments(self.path("Main.sublime-menu"))
        prefs = [m for m in menu if m["id"] == "preferences"][0]
        pkg = [m for m in prefs["children"] if m.get("id") == "package-settings"][0]
        ours = [m for m in pkg["children"] if m["caption"] == "GunsNPrices"][0]
        item = ours["children"][0]
        self.assertEqual((item["caption"], item["command"]), ("Settings", "edit_settings"))
        self.assertEqual(item["args"]["base_file"], "${packages}/GunsNPrices/GunsNPrices.sublime-settings")

    def test_default_settings(self):
        s = _json_with_comments(self.path("GunsNPrices.sublime-settings"))
        self.assertEqual(s, {"ascii_caliber_names": False, "caliber_links": False,
                             "spec_columns": plugin.DEFAULT_COLUMNS, "max_lines": 20000})

    def test_messages(self):
        messages = _json_with_comments(self.path("messages.json"))
        self.assertEqual(list(messages), ["install"])
        for name in messages.values():
            self.assertTrue(os.path.isfile(self.path(*name.split("/"))), name)

    def test_layout(self):
        with open(self.path(".python-version")) as f:
            self.assertEqual(f.read().strip(), "3.8")
        root_py = sorted(n for n in os.listdir(self.ROOT) if n.endswith(".py"))
        self.assertEqual(root_py, ["gunsnprices_plugin.py"])
        for name in ("LICENSE", "LICENSE-DATA", "README.md"):
            self.assertTrue(os.path.isfile(self.path(name)), name)
        for name in ("LICENSE", "LICENSE-DATA", "SOURCE.txt", "data/calibers.json", "data/models.json"):
            self.assertTrue(os.path.isfile(self.path("vendor", "gunsnprices", *name.split("/"))), name)


if __name__ == "__main__":
    unittest.main()
