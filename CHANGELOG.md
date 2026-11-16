# Changelog

## 1.0.0 (2026-11-16)

First release.

- **Parse Titles**: brand, model, generation, calibers, capacity, barrel length, rounds per box, price and cost per
  round for the selected lines, in a popup (one title), the output panel, or a new tab as JSON or CSV. Reads plain
  lists, CSV/TSV (with or without a header row), JSON Lines and pretty-printed JSON, SQL `INSERT`/`UPDATE` statements
  and Markdown tables.
- **Add Spec Columns to CSV**: appends `parsed_*` columns to every row of a CSV or TSV file.
- **Annotate Lines** / **Clear Annotations**: the parsed specs at the end of each line.
- **Normalize Caliber**: replaces selected caliber text with its standard name (293 calibers).
- **Cost per Round** from a price and a round count or a title.
- Settings: `ascii_caliber_names`, `caliber_links` (off by default), `spec_columns`, `max_lines`.
- Bundles the [`gunsnprices`](https://pypi.org/project/gunsnprices/) parser 0.1.2. Offline, no telemetry.
