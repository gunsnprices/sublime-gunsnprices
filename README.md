# GunsNPrices

A Sublime Text package that turns gun and ammo product titles into structured data: brand, model, generation,
caliber, magazine capacity, barrel length, rounds per box and cost per round. It is meant for people who build product
feeds, imports and catalogs for gun and ammo stores and work with CSV exports, JSON feeds and SQL dumps full of titles
like `G19 GEN5 9MM 15RD FS`.

Select some lines and run **GunsNPrices: Parse Titles** from the Command Palette:

```text
Glock 19 Gen 5 MOS 9mm 4.02" 15rd Pistol PA195S203MOS
Federal American Eagle 9mm Luger 115gr FMJ 50 Rounds $18.99
```

The output panel shows what the parser read from each line:

```text
Line 1: Glock 19 Gen 5 MOS 9mm 4.02" 15rd Pistol PA195S203MOS
  Kind:           firearm
  Brand:          Glock
  Model:          Glock 19 Gen 5 MOS
  Family:         Glock 19
  Generation:     5
  Configuration:  MOS
  Caliber:        9×19mm Parabellum (handgun)
  Capacity:       15 rounds
  Barrel:         4.02 in

Line 2: Federal American Eagle 9mm Luger 115gr FMJ 50 Rounds
  Kind:           ammo
  Caliber:        9×19mm Parabellum (handgun)
  Rounds per box: 50
  Price:          $18.99
  Cost per round: $0.38 (37.98¢)
```

Everything runs on your computer. The package makes no network requests, collects no telemetry and needs no account
or API key. The parsing is done by [`gunsnprices`](https://github.com/gunsnprices/gunsnprices-python), the open source
title parser behind the price comparison site [GunsNPrices](https://gunsnprices.com). It is bundled with the package,
so there is nothing else to install.

## Installation

With [Package Control](https://packagecontrol.io/installation): open the Command Palette, run
**Package Control: Install Package** and choose **GunsNPrices**.

Manually: clone this repository into your `Packages` folder (**Preferences > Browse Packages...**) as a folder named
`GunsNPrices`:

```bash
git clone https://github.com/gunsnprices/sublime-gunsnprices.git GunsNPrices
```

Requires Sublime Text 4 (build 4107 or newer).

## Commands

All commands are in the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`) under **GunsNPrices:**.

| Command | What it does |
|---|---|
| **GunsNPrices: Parse Titles** | Parses the selected lines, or the line with the cursor. One title opens a popup, several open the `gunsnprices` output panel |
| **GunsNPrices: Parse Titles to JSON** | Same, as a JSON array in a new tab |
| **GunsNPrices: Parse Titles to CSV** | Same, as CSV in a new tab |
| **GunsNPrices: Add Spec Columns to CSV** | Appends `parsed_kind`, `parsed_brand`, `parsed_model`, ... columns to every row of a CSV or TSV file |
| **GunsNPrices: Annotate Lines** | Shows the parsed specs at the end of each selected line, or of every line when nothing is selected |
| **GunsNPrices: Clear Annotations** | Removes those annotations |
| **GunsNPrices: Normalize Caliber** | Replaces the selected caliber text with its standard name |
| **GunsNPrices: Cost per Round** | Asks for a price and a round count and shows the price of one round |
| **Preferences: GunsNPrices Settings** | Opens the settings |

### Parse Titles

Each selected line is read according to what it looks like:

| Input | How the title and price are found |
|---|---|
| Plain list of titles | The line is the title. A price written as `$18.99`, `$1,299.99` or `18.99 USD` is taken out of the title and used for cost per round. |
| CSV / TSV with a header row | The column named `title`, `name`, `product_name`, `item_name`, `description`, ... is the title; `sale_price`, `price`, `our_price`, ... is the price. The header row itself is skipped. Works for `.csv` and `.tsv` files and for unsaved files that start with such a header. |
| CSV / TSV without a header | The text cell that parses best is the title; the first cell that holds only a price (`24.99`, `$24.99`) is the price. |
| JSON | JSON Lines (`{"title": "...", "price": 18.99}`), arrays on one line, and pretty-printed files: lines like `"title": "..."` or `"name": "..."` are read, other properties are skipped. |
| SQL | `INSERT ... VALUES (...), (...)` with any number of rows on one line, using the column list when there is one; `UPDATE ... SET title = '...'`. |
| Markdown tables | `\| ... \|` rows; header and separator rows are skipped. |

The popup for a single title has **Copy JSON** and **Copy CSV** links. To parse a whole file, select all
(`Ctrl+A` / `Cmd+A`) first. Selections of more than 300 lines are parsed in the background, with progress in the status
bar; the parser reads about 1,000 titles per second.

The JSON output has the fields of the parser's `ProductInfo` plus the source `line` and the `price` that was found:

```json
{
  "line": 2,
  "title": "Federal American Eagle 9mm Luger 115gr FMJ 50 Rounds",
  "kind": "ammo",
  "brand": "",
  "model": null,
  "caliber": { "id": "9x19mmparabellum", "name": "9×19mm Parabellum", "type": "handgun" },
  "calibers": [{ "id": "9x19mmparabellum", "name": "9×19mm Parabellum", "type": "handgun" }],
  "capacity": null,
  "barrel_length": null,
  "rounds": 50,
  "price": 18.99,
  "cost_per_round": 0.3798
}
```

For firearms, `model` is an object with `brand`, `family`, `model`, `generation`, `configs`, `features` and `source`.

The CSV output has these columns (several values in one cell are separated by `; `):

```text
line,title,kind,brand,model,family,generation,configs,features,caliber,caliber_type,calibers,capacity,barrel_in,rounds,price,cost_per_round
1,"Glock 19 Gen 5 MOS 9mm 4.02"" 15rd Pistol PA195S203MOS",firearm,Glock,Glock 19 Gen 5 MOS,Glock 19,5,MOS,,9×19mm Parabellum,handgun,9×19mm Parabellum,15,4.02,,,
2,Federal American Eagle 9mm Luger 115gr FMJ 50 Rounds,ammo,,,,,,,9×19mm Parabellum,handgun,9×19mm Parabellum,,,50,18.99,0.3798
```

### Add Spec Columns to CSV

Works on CSV and TSV files: a `.csv` or `.tsv` file, or any file whose first line is a header with a title column.
Every row gets the columns from the `spec_columns` setting, the header row gets their names with a `parsed_` prefix,
and rows without a gun or ammo title get empty cells, so all rows keep the same number of cells:

```text
sku,title,price,parsed_kind,parsed_brand,parsed_model,parsed_caliber,parsed_capacity,parsed_barrel_in,parsed_rounds,parsed_cost_per_round
A1,Glock 19 Gen 5 9mm 4.02in 15rd,529.99,firearm,Glock,Glock 19 Gen 5,9×19mm Parabellum,15,4.02,,
A2,"Federal 9mm 115gr FMJ, 50 Rounds",18.99,ammo,,,9×19mm Parabellum,,,50,0.3798
A3,Gift card,25.00,,,,,,,,
```

The whole change is one undo step. When the header row already has the `parsed_` columns, the command does nothing.
It works line by line, so quoted cells that span several lines are not supported.

### Annotate Lines

Shows a short summary at the right edge of each line that reads like a gun or ammo title, without changing the text:

```text
Glock 19 Gen 5 MOS 9mm 4.02" 15rd Pistol PA195S203MOS        Glock 19 Gen 5 MOS · 9×19mm Parabellum · 15 rd · 4.02"
Federal American Eagle 9mm Luger 115gr FMJ 50 Rounds $18.99  ammo · 9×19mm Parabellum · 50 rd · $0.38/rd
```

Lines that merely contain a number that could be a caliber (`call me at 308 tomorrow`) are skipped. Annotations do not
update while you edit; run the command again, or **GunsNPrices: Clear Annotations** to remove them.

### Normalize Caliber

Select a caliber, or a column of them (one per line, or with several cursors), and run **GunsNPrices: Normalize
Caliber**:

| Selected | Becomes |
|---|---|
| `9mm Luger`, `9x19` | `9×19mm Parabellum` |
| `5.56 NATO` | `5.56×45mm NATO` |
| `.223 Remington` | `.223 Rem` |
| `12ga` | `12 Gauge` |
| `300 BLK` | `.300 AAC Blackout` |
| `45 auto` | `.45 ACP` |
| `6.5 CM` | `6.5mm Creedmoor` |
| `38 Spl` | `.38 S&W Special` |

The names come from a list of 293 calibers. Quotes and spaces around the value are kept. Text that isn't recognized is
left as it is, and so is text that is more than a caliber (a whole title, or `9mm / .380`), so selecting too much never
loses data; a message lists what was left. Set `ascii_caliber_names` to get `9x19mm Parabellum` instead of
`9×19mm Parabellum`.

### Cost per Round

Asks for the price of the box or case, then for the number of rounds or a title that contains it (`50 Rounds`,
`1000rd case`, `20/box`). When the cursor is on a line with a price and a round count, both are filled in. The result
is shown in a popup with a **Copy** link:

```text
$289.99 for 1,000 rounds = $0.29 (29.00¢) per round
```

The command also takes arguments, for use in key bindings or macros:
`{"command": "gunsnprices_cost_per_round", "args": {"price": "18.99", "rounds": "50"}}`.

## Key bindings

The package adds no key bindings. To add your own, open **Preferences > Key Bindings** and add, for example:

```json
[
	{ "keys": ["ctrl+alt+g"], "command": "gunsnprices_parse_titles", "args": { "output": "auto" } },
	{ "keys": ["ctrl+alt+shift+g"], "command": "gunsnprices_normalize_caliber" }
]
```

`gunsnprices_parse_titles` takes `output`: `auto`, `popup`, `panel`, `json` or `csv`.

## Settings

Open **Preferences > Package Settings > GunsNPrices > Settings**, or run **Preferences: GunsNPrices Settings**.

| Setting | Default | |
|---|---|---|
| `ascii_caliber_names` | `false` | Write `×` as `x` in caliber names |
| `caliber_links` | `false` | Add the URL of each caliber's price comparison page on gunsnprices.com to results: `url` in JSON, a `caliber_url` column in CSV, clickable caliber names in popups |
| `spec_columns` | `["kind", "brand", "model", "caliber", "capacity", "barrel_in", "rounds", "cost_per_round"]` | Columns for **Add Spec Columns to CSV**. Also available: `family`, `generation`, `configs`, `features`, `caliber_type`, `calibers`, `price`, `caliber_url` |
| `max_lines` | `20000` | The most lines one command reads |

## What it recognizes

| Field | Example in a title | Result |
|---|---|---|
| Firearm or ammo | `... 150gr ... 20rds` | ammo |
| Brand and model (50 brands) | `G19 Gen5 MOS`, Glock part number `PA195S203` | Glock 19 Gen 5 MOS |
| Calibers (293) | `.357 Mag / .38 Spl`, `6.5 CM`, `12ga`, `300 BLK` | .357 Mag, .38 S&W Special, ... |
| Magazine capacity | `15+1`, `17RD`, `10-shot` | 15, 17, 10 |
| Barrel length, inches | `4.02in`, `16 1/2"`, `22 BBL` | 4.02, 16.5, 22 |
| Rounds per box | `50/Box`, `Box of 20`, `1,000 Rounds` | 50, 20, 1000 |

Brands with model dictionaries include Glock, Sig Sauer, Smith & Wesson, Ruger, Springfield, Taurus, Mossberg,
Remington, Beretta, Benelli, Browning, Winchester, CZ, FN, HK, Henry, Marlin, Savage, Tikka, Walther and 30 more; the
full list is in the [`gunsnprices` README](https://github.com/gunsnprices/gunsnprices-python#readme). Titles of other
brands still get calibers and numbers. The parser is built for titles from US retailers, in English.

The same parser is available as a Python package (`pip install gunsnprices`), for Node.js and browsers
(`npm install gunsnprices`) and in several other languages, with the same results, if you want to run it in a feed
pipeline. All of them are listed at [gunsnprices.com/developers](https://gunsnprices.com/developers).

## Privacy

The package reads only the text you select or annotate, in memory. It sends nothing anywhere: there is no telemetry
and no network code. With `caliber_links` turned on, caliber names in popups become links that open in your browser
when you click them.

## Development

The package code is in `gunsnprices_plugin.py` (Sublime Text commands) and `core/` (everything that does not need the
editor). The parser is a copy of the [`gunsnprices`](https://pypi.org/project/gunsnprices/) Python package in
`vendor/gunsnprices/`, with one change for loading its data from the package archive (see
[`SOURCE.txt`](vendor/gunsnprices/SOURCE.txt)).

The package runs on Sublime Text's Python 3.8 plugin host (`.python-version`); Sublime Text 4205 and newer run it on
Python 3.14. The tests use mock `sublime` and `sublime_plugin` modules and need no dependencies:

```bash
python3 -m unittest discover -s tests
```

Questions, corrections and missing models: open an issue or write to app@gunsnprices.com.

## License

The code is under the [MIT License](LICENSE). The model and caliber data in `vendor/gunsnprices/data/` are under
[CC BY 4.0](LICENSE-DATA): you can use them for anything, including commercial use, if you credit
**GunsNPrices (gunsnprices.com)** with a link.
