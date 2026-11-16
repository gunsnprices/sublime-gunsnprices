# Publishing

How this package gets to Package Control (https://packagecontrol.io) and how to release new versions. This file and
the tests are left out of the installed package (see `.gitattributes`).

## How Package Control works

- The default channel is the GitHub repository `wbond/package_control_channel`. Packages are listed in
  `repository/<first letter>.json`; this one goes into `repository/g.json`.
- The entry points to this GitHub repository (`details`) and says `"tags": true`: every git tag that is a semantic
  version (`1.0.0`, `1.0.1`, `1.1.0`) is a release. Package Control builds the `.sublime-package` archive from the tag
  with `git archive`, so files marked `export-ignore` in `.gitattributes` are not installed.
- The packagecontrol.io page shows the repository description, the README and the repository homepage
  (`https://gunsnprices.com/developers`), all read from GitHub.
- New packages are reviewed by a person. Their checklist is in the channel's pull request template; the automated part
  is `kaste/st_package_reviewer`, which also runs in this repository's CI (job `package-review`).

## Review rules and how this package meets them

| Rule | Here |
|---|---|
| No "Sublime" in the package name, no dots, ASCII | `GunsNPrices` |
| Semantic version tag | `1.0.0` |
| README that explains what the package is for and how to use it | `README.md` |
| Commands are in the Command Palette | `Default.sublime-commands`, all with the `GunsNPrices:` prefix |
| No context menu entries | none |
| No default key bindings | none; the README shows how to add your own |
| Settings in the menu and the Command Palette, opened with `edit_settings` | `Main.sublime-menu` (Preferences > Package Settings > GunsNPrices > Settings) and `Preferences: GunsNPrices Settings` |
| Settings file named after the package | `GunsNPrices.sublime-settings` |
| Plugins in the repository root, shared code in subpackages, relative imports, no `sys.path` changes | `gunsnprices_plugin.py`; `core/`, `vendor/` |
| Works from the zipped `.sublime-package` (no `.no-sublime-package`) | data files are read through the module loader or `sublime.load_resource` |
| No Sublime API calls at import time | settings are loaded when a command runs |
| One command prefix | `gunsnprices_` |
| `messages.json` when there is a `messages` folder | `install` message |
| Tests, CI and other files not needed at runtime are excluded | `.gitattributes` |
| README says whether code leaves the machine | "Privacy" section: no network code |

## Python version

`.python-version` contains `3.8`. Sublime Text builds 4050 to 4204 run the package on Python 3.8; build 4205 and newer
run it on Python 3.14 (`3.8` is kept as an alias). Without the file Sublime Text would use the deprecated Python 3.3
host. The code must therefore run on both 3.8 and 3.14: no `match`, no `X | Y` annotations evaluated at runtime, no
standard library APIs added after 3.8. CI checks this with `vermin` and runs the tests on Python 3.8 and 3.14.

## Releasing a new version

1. Make the change, add tests, and update `CHANGELOG.md`.
2. For a change users should know about, add a message file and register it in `messages.json`, for example
   `"1.1.0": "messages/1.1.0.txt"`. Package Control shows it after the update.
3. Run the tests: `python3 -m unittest discover -s tests`.
4. Commit, then tag and push:

   ```bash
   git tag 1.1.0
   git push origin main 1.1.0
   gh release create 1.1.0 --title 1.1.0 --notes-from-tag   # optional, Package Control only needs the tag
   ```

5. Package Control picks up the new tag on its next crawl. The channel entry does not change.

## Updating the bundled parser

`vendor/gunsnprices/` is a copy of the `gunsnprices` Python package (https://github.com/gunsnprices/gunsnprices-python).
To update it:

1. Copy `__init__.py`, `calibers.py`, `models.py`, `parse.py`, `specs.py` and `data/*.json` from the new version.
2. In `calibers.py` and `models.py`, replace the `importlib.resources` reads with `read_data(...)` from `._data`, as in
   the current copy (see `vendor/gunsnprices/SOURCE.txt`).
3. Copy the new `tests/golden.jsonl` into `tests/`, update the version in `SOURCE.txt`, `test_vendored_parser.py`
   and `CHANGELOG.md`, and run the tests on Python 3.8.

## First submission to the channel

The fork is `gunsnprices-admin/package_control_channel`, branch `add-gunsnprices`, with this entry in
`repository/g.json` (between `Guna` and `Gutter Color`):

```json
{
	"name": "GunsNPrices",
	"details": "https://github.com/gunsnprices/sublime-gunsnprices",
	"labels": ["text manipulation", "utilities", "csv", "json"],
	"releases": [
		{
			"sublime_text": ">=4107",
			"tags": true
		}
	]
}
```

Open the pull request from that branch to `wbond/package_control_channel` with the title `Add GunsNPrices` and the
channel's pull request template. Reviews usually take a few weeks. The reviewers want to talk to the person who will
maintain the package, so answer their questions on the pull request yourself. After a review comment is fixed, push
a new tag; a comment with `/review` on the pull request runs the automated check again.

After the package is merged, its page is `https://packagecontrol.io/packages/GunsNPrices`. Replace the GitHub link
for Sublime Text on https://gunsnprices.com/developers with that page.
