#!/usr/bin/env python3
"""Inline the card data and math generators into a single self-contained page.

Artifacts run under a strict CSP with no external requests, so the shell and its
data have to ship as one file. Keeping the cards in data/ and inlining at build
time means the bank stays portable: point any other renderer at the same JSON.
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "data"
DIST = ROOT / "dist"

DECK_FILES = ["markets.json", "quality.json", "projections.json", "misc.json"]


def main() -> None:
    decks = []
    for name in DECK_FILES:
        deck = json.loads((DATA / name).read_text(encoding="utf-8"))
        decks.append(deck)
        print(f"  {name:20} {len(deck['cards']):3d} cards")

    generators = (DATA / "generators.js").read_text(encoding="utf-8")
    shell = (ROOT / "app.html").read_text(encoding="utf-8")

    if "/*__DATA__*/" not in shell or "/*__GENERATORS__*/" not in shell:
        raise SystemExit("app.html is missing an injection token")

    out = shell.replace("/*__GENERATORS__*/", generators)
    out = out.replace("/*__DATA__*/", json.dumps(decks, ensure_ascii=False))

    DIST.mkdir(exist_ok=True)
    target = DIST / "drill.html"
    target.write_text(out, encoding="utf-8")

    total = sum(len(d["cards"]) for d in decks)
    size = target.stat().st_size / 1024
    print(f"  {'':20} {total:3d} cards total")
    print(f"\n  wrote {target.relative_to(ROOT)}  ({size:.0f} KB)")


if __name__ == "__main__":
    main()
