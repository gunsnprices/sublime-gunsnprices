"""Editor-independent logic: finding titles and prices in lines, output formats, calibers, spec columns."""
import importlib
import json
import unittest

import sublime_mock

sublime_mock.install()
extract = importlib.import_module("GunsNPrices.core.extract")
titles = importlib.import_module("GunsNPrices.core.titles")
formats = importlib.import_module("GunsNPrices.core.formats")
columns = importlib.import_module("GunsNPrices.core.columns")

NINE = "9×19mm Parabellum"
NINE_URL = "https://gunsnprices.com/ammo/handgun-ammo/9-19mm-parabellum"
PLAIN = extract.make_context("plaintext", None, "Glock 19 Gen 5 9mm")


def rows(line, ctx=PLAIN, index=3):
    return titles.parse_line(line, index, ctx)


class ExtractTest(unittest.TestCase):
    def one(self, line, ctx=PLAIN):
        r = rows(line, ctx)
        self.assertEqual(len(r), 1, line)
        return r[0]

    def test_plain_title(self):
        r = self.one('Glock 19 Gen 5 MOS 9mm 4.02" 15rd Pistol PA195S203MOS')
        self.assertEqual(r.line, 4)
        self.assertEqual(r.info.kind, "firearm")
        self.assertEqual(r.info.model.model, "Glock 19 Gen 5 MOS")
        self.assertEqual(r.info.model.generation, "5")
        self.assertEqual(r.info.caliber.name, NINE)
        self.assertEqual((r.info.capacity, r.info.barrel_length, r.price), (15, 4.02, None))

    def test_price_in_text_is_used_and_removed(self):
        r = self.one("Federal American Eagle 9mm Luger 115gr FMJ 50 Rounds $18.99")
        self.assertEqual(r.title, "Federal American Eagle 9mm Luger 115gr FMJ 50 Rounds")
        self.assertEqual((r.price, r.info.rounds, r.info.cost_per_round), (18.99, 50, 0.3798))
        self.assertEqual(self.one("- Winchester 9mm 115gr FMJ 1000 Round Case - $1,289.99").price, 1289.99)
        self.assertEqual(self.one("CCI Blazer 9mm 124gr 50rd 15.49 USD").price, 15.49)

    def test_empty_lines(self):
        for line in ("", "   ", "},", "|---|---:|"):
            self.assertEqual(rows(line), [], line)

    def test_csv_with_header(self):
        header = "sku,product_name,brand,sale_price,price"
        ctx = extract.make_context("plaintext", None, header)
        self.assertEqual((ctx.delimiter, ctx.columns, ctx.header_line), (",", (1, 3), 0))
        self.assertEqual(titles.parse_line(header, 0, ctx), [])
        r = titles.parse_line('A1,"Glock 19 Gen 5, 9mm, 15rd",Glock,529.99,549.99', 1, ctx)[0]
        self.assertEqual((r.title, r.price, r.info.model.model), ("Glock 19 Gen 5, 9mm, 15rd", 529.99, "Glock 19 Gen 5"))

    def test_csv_without_header(self):
        line = "1001,Hornady Critical Defense 380 ACP 90gr FTX 25rd,24.99,090255900904"
        ctx = extract.make_context("csv", "/feeds/ammo.csv", line)
        self.assertEqual((ctx.delimiter, ctx.columns), (",", None))
        r = titles.parse_line(line, 0, ctx)[0]
        self.assertEqual(r.title, "Hornady Critical Defense 380 ACP 90gr FTX 25rd")
        self.assertEqual((r.price, r.info.rounds, r.info.cost_per_round), (24.99, 25, 0.9996))

    def test_tsv(self):
        ctx = extract.make_context("plaintext", "/x/feed.tsv", "id\ttitle\tprice")
        self.assertEqual((ctx.delimiter, ctx.columns), ("\t", (1, 2)))
        self.assertEqual(titles.parse_line("7\tCCI Mini-Mag 22 LR 40gr 100 Rounds\t8.99", 1, ctx)[0].price, 8.99)
        r = self.one("123\tCCI Mini-Mag 22 LR 40gr 100 Rounds\t8.99")
        self.assertEqual((r.title, r.price), ("CCI Mini-Mag 22 LR 40gr 100 Rounds", 8.99))

    def test_semicolon_csv(self):
        ctx = extract.make_context("csv", None, "Name;Price")
        self.assertEqual(ctx.delimiter, ";")
        r = titles.parse_line('Ruger 10/22 Carbine .22 LR 18.5" 10rd;349,00', 1, ctx)[0]
        self.assertEqual(r.info.model.model, "Ruger 10/22 Carbine")

    def test_json(self):
        r = self.one('{"sku":"A1","title":"PMC Bronze 5.56 NATO 55gr FMJ 20rd","price":"9.99"},')
        self.assertEqual((r.title, r.price), ("PMC Bronze 5.56 NATO 55gr FMJ 20rd", 9.99))
        ctx = extract.make_context("json", None, "[")
        self.assertEqual(self.one('  "name": "Ruger 10/22 Carbine .22 LR 18.5\\" 10rd",', ctx).title,
                         'Ruger 10/22 Carbine .22 LR 18.5" 10rd')
        for line in ('  "price": 18.99,', '  "sku": "PA195S203",', "  {"):
            self.assertEqual(rows(line, ctx), [], line)
        self.assertEqual(self.one('  "Sig Sauer P365 XL 9mm 3.1\\" 12+1",', ctx).info.model.model, "Sig Sauer P365 XL")
        arr = rows('[{"name":"Glock 17 Gen 5 9mm","price":499.99},{"name":"Federal 9mm 115gr FMJ 50rd","price":17.5}]',
                   ctx)
        self.assertEqual(len(arr), 2)
        self.assertEqual(arr[1].info.cost_per_round, 0.35)

    def test_sql(self):
        sql = extract.make_context("sql", None, "-- dump")
        r = rows("INSERT INTO `products` (`id`, `title`, `price`) VALUES (1,'Mossberg 500 12ga 28\" 5+1',399.99),"
                 "(2,'Federal Champion 22 LR 36gr 525 Rounds',27.99);", sql)
        self.assertEqual(len(r), 2)
        self.assertEqual((r[0].title, r[0].price, r[0].info.model.model), ('Mossberg 500 12ga 28" 5+1', 399.99,
                                                                           "Mossberg 500"))
        self.assertEqual((r[1].info.rounds, r[1].price), (525, 27.99))
        escaped = rows("(3,'Smith & Wesson M&P Shield Plus 9mm 3.1\\\" 13rd','It''s new',479.00),", sql)
        self.assertEqual(escaped[0].info.brand, "Smith & Wesson")
        upd = rows("UPDATE products SET title = 'Henry Big Boy .357 Mag 20\" 10rd' WHERE id = 9;", sql)
        self.assertEqual(upd[0].info.brand, "Henry")

    def test_markdown_table(self):
        r = self.one('| 7 | Sig Sauer P365 XL 9mm 3.1" 12+1 | $599.00 |')
        self.assertEqual((r.title, r.price), ('Sig Sauer P365 XL 9mm 3.1" 12+1', 599.0))
        self.assertEqual(rows("| Title | Price |"), [])

    def test_prices(self):
        self.assertEqual(extract.parse_price("$1,299.99"), 1299.99)
        self.assertEqual(extract.parse_price(" 18.99 USD"), 18.99)
        self.assertEqual(extract.parse_price(18.99), 18.99)
        for bad in ("abc", "0", -5, None, True, ""):
            self.assertIsNone(extract.parse_price(bad), bad)
        self.assertEqual(extract.find_price_in_text("Glock 19 Gen 5 9mm (@ $549)"), (549.0, "Glock 19 Gen 5 9mm"))
        self.assertEqual(extract.find_price_in_text('Ruger 10/22 4.02"'), (None, 'Ruger 10/22 4.02"'))

    def test_split_cells(self):
        cells = extract.split_cells('a, "b ""x"", c" ,d', ",")
        self.assertEqual([c.text for c in cells], ["a", 'b "x", c', "d"])
        self.assertEqual([(c.start, c.end) for c in cells], [(0, 1), (2, 16), (17, 18)])

    def test_header_columns(self):
        self.assertEqual(extract.header_columns(["id", "Title", "Price"]), (1, 2))
        self.assertEqual(extract.header_columns(["item_name", "regular_price", "our_price"]), (0, 2))
        self.assertEqual(extract.header_columns(["id", "title"]), (1, None))
        for names in (["Glock 19", "Gen 5", "9mm"], ["title", "18.99"], ["title"]):
            self.assertIsNone(extract.header_columns(names), names)

    def test_language_for(self):
        lf = extract.language_for
        self.assertEqual(lf("source.json", None), "json")
        self.assertEqual(lf("text.plain", "/x/feed.jsonl"), "jsonl")
        self.assertEqual(lf("text.plain", "/x/feed.CSV"), "csv")
        self.assertEqual(lf("text.advanced_csv", None), "csv")
        self.assertEqual(lf("text.plain", "/x/feed.tsv"), "tsv")
        self.assertEqual(lf("source.sql", None), "sql")
        self.assertEqual(lf("text.html.markdown", None), "markdown")
        self.assertEqual(lf("text.plain", "notes.txt"), "plaintext")
        self.assertEqual(lf("", None), "plaintext")


class TitlesTest(unittest.TestCase):
    def test_looks_like_title(self):
        def t(s):
            return titles.looks_like_title(rows(s)[0].info, s)
        self.assertTrue(t('Glock 19 Gen 5 MOS 9mm 4.02" 15rd Pistol'))
        self.assertTrue(t("Federal 9mm 115gr FMJ"))
        self.assertFalse(t("hello world 380 people"))
        self.assertFalse(t("call me at 308 tomorrow"))

    def test_normalize_caliber_text(self):
        n = titles.normalize_caliber_text
        self.assertEqual(n("9mm Luger").text, NINE)
        self.assertEqual(n("9mm Luger", True).text, "9x19mm Parabellum")
        self.assertEqual(n(' "5.56 NATO" ').text, ' "5.56×45mm NATO" ')
        r = n(".223 Rem\n12ga\r\nbar\n300 BLK")
        self.assertEqual(r.text, ".223 Rem\n12 Gauge\r\nbar\n.300 AAC Blackout")
        self.assertEqual(r.changed, [("12ga", "12 Gauge"), ("300 BLK", ".300 AAC Blackout")])
        self.assertEqual((r.unknown, r.ambiguous), (["bar"], []))
        title = n("Federal 9mm Luger 115gr FMJ 50 Rounds")
        self.assertEqual(title.text, "Federal 9mm Luger 115gr FMJ 50 Rounds")
        self.assertEqual(title.ambiguous, ["Federal 9mm Luger 115gr FMJ 50 Rounds"])
        self.assertEqual(n("9mm / .380").ambiguous, ["9mm / .380"])
        self.assertEqual(n(NINE).changed, [])
        for given, expected in [("45 auto", ".45 ACP"), ("6.5 CM", "6.5mm Creedmoor"), ("38 Spl", ".38 S&W Special"),
                                ("12ga", "12 Gauge"), ("300 BLK", ".300 AAC Blackout")]:
            self.assertEqual(n(given).text, expected, given)

    def test_rounds_from(self):
        self.assertEqual(titles.rounds_from("50"), 50)
        self.assertEqual(titles.rounds_from("1,000"), 1000)
        self.assertEqual(titles.rounds_from("Federal 9mm 115gr FMJ 1000 Round Case"), 1000)
        self.assertEqual(titles.rounds_from("20/box"), 20)
        self.assertIsNone(titles.rounds_from("0"))
        self.assertIsNone(titles.rounds_from(""))
        self.assertIsNone(titles.rounds_from("Glock 19"))


SAMPLE = [r for i, line in enumerate(['Glock 19 Gen 5 MOS 9mm 4.02" 15rd Pistol',
                                      "Federal American Eagle 9mm Luger 115gr FMJ 50 Rounds $18.99"])
          for r in titles.parse_line(line, i, PLAIN)]
OFF = formats.Options()
ON = formats.Options(links=True)


class FormatsTest(unittest.TestCase):
    def test_json(self):
        data = json.loads(formats.to_json(SAMPLE, OFF))
        self.assertEqual(len(data), 2)
        self.assertEqual(list(data[0]), ["line", "title", "kind", "brand", "model", "caliber", "calibers", "capacity",
                                         "barrel_length", "rounds", "price", "cost_per_round"])
        self.assertEqual(data[0]["model"]["model"], "Glock 19 Gen 5 MOS")
        self.assertEqual(data[0]["model"]["configs"], ["MOS"])
        self.assertEqual(data[0]["caliber"], {"id": "9x19mmparabellum", "name": NINE, "type": "handgun"})
        self.assertEqual((data[1]["price"], data[1]["cost_per_round"]), (18.99, 0.3798))
        self.assertEqual(json.loads(formats.to_json(SAMPLE, ON))[0]["caliber"]["url"], NINE_URL)
        self.assertEqual(json.loads(formats.to_json(SAMPLE, formats.Options(ascii_names=True)))[0]["caliber"]["name"],
                         "9x19mm Parabellum")

    def test_csv(self):
        lines = formats.to_csv(SAMPLE, OFF).split("\n")
        self.assertEqual(lines[0], "line,title,kind,brand,model,family,generation,configs,features,caliber,"
                                   "caliber_type,calibers,capacity,barrel_in,rounds,price,cost_per_round")
        self.assertEqual(lines[1], '1,"Glock 19 Gen 5 MOS 9mm 4.02"" 15rd Pistol",firearm,Glock,Glock 19 Gen 5 MOS,'
                                   "Glock 19,5,MOS,,%s,handgun,%s,15,4.02,,," % (NINE, NINE))
        self.assertEqual(lines[2], "2,Federal American Eagle 9mm Luger 115gr FMJ 50 Rounds,ammo,,,,,,,%s,handgun,%s,,,"
                                   "50,18.99,0.3798" % (NINE, NINE))
        self.assertEqual(lines[3], "")
        linked = formats.to_csv(SAMPLE, formats.Options(links=True, ascii_names=True)).split("\n")
        self.assertTrue(linked[0].endswith(",caliber_url"))
        self.assertTrue(linked[1].endswith("," + NINE_URL))
        self.assertIn(",9x19mm Parabellum,", linked[1])
        self.assertEqual(formats.csv_field(" a"), '" a"')
        self.assertEqual(formats.csv_field(None), "")
        self.assertEqual(formats.csv_field("a\tb", "\t"), '"a\tb"')
        self.assertEqual(formats.csv_field(22.0), "22")

    def test_text(self):
        text = formats.to_text(SAMPLE, OFF)
        self.assertTrue(text.startswith("Parsed 2 titles with the gunsnprices parser 0.1.2.\n\n"))
        self.assertIn('Line 1: Glock 19 Gen 5 MOS 9mm 4.02" 15rd Pistol\n  Kind:           firearm\n'
                      "  Brand:          Glock\n  Model:          Glock 19 Gen 5 MOS\n  Family:         Glock 19\n", text)
        self.assertIn("  Caliber:        %s (handgun)\n  Capacity:       15 rounds\n  Barrel:         4.02 in\n" % NINE,
                      text)
        self.assertIn("  Price:          $18.99\n  Cost per round: $0.38 (37.98¢)\n", text)
        self.assertNotIn("https://", text)
        self.assertIn(NINE_URL, formats.to_text(SAMPLE, ON))

    def test_popup(self):
        html = formats.popup_html(SAMPLE[0], OFF)
        self.assertIn("<h1>Glock 19 Gen 5 MOS</h1>", html)
        self.assertIn('<span class="label">Caliber:</span> %s (handgun)' % NINE, html)
        self.assertIn('href="copy:json"', html)
        self.assertNotIn("https://", html)
        self.assertIn('<a href="%s">%s</a>' % (NINE_URL, NINE), formats.popup_html(SAMPLE[0], ON))
        self.assertIn("<h1>Ammo · %s · 50 rounds</h1>" % NINE, formats.popup_html(SAMPLE[1], OFF))
        escaped = formats.popup_html(rows("Glock 19 <b>Gen 5</b> 9mm 15rd")[0], OFF)
        self.assertNotIn("<b>", escaped)

    def test_annotation_and_money(self):
        self.assertEqual(formats.annotation_text(SAMPLE[0], OFF), 'Glock 19 Gen 5 MOS · %s · 15 rd · 4.02"'
                         % NINE)
        self.assertEqual(formats.annotation_text(SAMPLE[1], OFF), "ammo · %s · 50 rd · $0.38/rd" % NINE)
        self.assertEqual(formats.money(1289.5), "$1,289.50")
        self.assertEqual(formats.per_round(0.3798), "$0.38")
        self.assertEqual(formats.per_round(0.0899, True), "$0.09 (8.99¢)")
        self.assertEqual(formats.cost_text(289.99, 1000, 0.29), "$289.99 for 1,000 rounds = $0.29 (29.00¢) per round")


class ColumnsTest(unittest.TestCase):
    CSV = ["sku,title,price", "A1,Glock 19 Gen 5 9mm 4.02in 15rd,529.99", "",
           'A2,"Federal 9mm 115gr FMJ, 50 Rounds",18.99', "A3,Gift card,25.00"]

    def test_add_columns_with_header(self):
        ctx = extract.make_context("csv", "feed.csv", self.CSV[0])
        res = columns.add_spec_columns(self.CSV, ctx)
        self.assertIsNone(res.error)
        got = dict(res.suffixes)
        self.assertEqual(got[0], ",parsed_kind,parsed_brand,parsed_model,parsed_caliber,parsed_capacity,"
                                 "parsed_barrel_in,parsed_rounds,parsed_cost_per_round")
        self.assertEqual(got[1], ",firearm,Glock,Glock 19 Gen 5,%s,15,4.02,," % NINE)
        self.assertNotIn(2, got)
        self.assertEqual(got[3], ",ammo,,,%s,,,50,0.3798" % NINE)
        self.assertEqual(got[4], ",,,,,,,,")
        self.assertEqual((res.rows, res.empty), (2, 1))
        cells = [extract.split_cells(self.CSV[i] + got[i], ",") for i in (0, 1, 3, 4)]
        self.assertEqual({len(c) for c in cells}, {11})

    def test_add_columns_again_is_refused(self):
        lines = [self.CSV[0] + ",parsed_kind,parsed_brand", self.CSV[1] + ",firearm,Glock"]
        ctx = extract.make_context("csv", "feed.csv", lines[0])
        self.assertIn("already has the parsed_kind columns", columns.add_spec_columns(lines, ctx).error)

    def test_add_columns_tsv_custom_columns(self):
        lines = ["id\tname", "1\tSig Sauer P365 XL 9mm 3.7in 12rd Pistol"]
        ctx = extract.make_context("tsv", "feed.tsv", lines[0])
        res = columns.add_spec_columns(lines, ctx, ["model", "caliber_url"], formats.Options(ascii_names=True))
        self.assertEqual(res.suffixes, [(0, "\tparsed_model\tparsed_caliber_url"),
                                        (1, "\tSig Sauer P365 XL\t" + NINE_URL)])

    def test_add_columns_needs_a_delimited_file(self):
        ctx = extract.make_context("plaintext", "titles.txt", "Glock 19 Gen 5 9mm")
        self.assertIn("works on CSV and TSV files", columns.add_spec_columns(["Glock 19 Gen 5 9mm"], ctx).error)
        ctx = extract.make_context("csv", "feed.csv", "a,b")
        self.assertIn("Unknown column", columns.add_spec_columns(["a,b"], ctx, ["kind", "colour"]).error)

    def test_annotate_lines(self):
        lines = list(enumerate(['Glock 19 Gen 5 MOS 9mm 4.02" 15rd Pistol', "hello world 380 people", "",
                                '[{"name":"Glock 17 Gen 5 9mm"},{"name":"Federal 9mm 115gr FMJ 50rd"}]']))
        notes = columns.annotate_lines(lines, PLAIN)
        self.assertEqual([i for i, _ in notes], [0, 3])
        self.assertTrue(notes[1][1].endswith("(+1 more)"))


if __name__ == "__main__":
    unittest.main()
