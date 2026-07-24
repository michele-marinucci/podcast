# Drill — investing interview prep

Flashcard drill for hedge fund interviews. Tiger-style framing: concentrated,
thesis-driven, long-biased, ~12-month horizon.

Two modes, kept strictly separate — **math cards you compute, diligence cards
you reason**. Diligence cards may hand you numbers, but never ask you to
calculate them.

## Layout

    data/markets.json      22 cards  market structure, inflections, dynamic -> financials
    data/quality.json      12 cards  moats via Helmer's 7 Powers
    data/projections.json  10 cards  driver trees, unit economics, thesis -> model
    data/misc.json          8 cards  variant perception, catalysts, kill criteria, pitch
    data/generators.js      8 gens   parameterised math, clean + precise difficulty
    app.html                         renderer (data injected at build)
    build.py                         inlines data -> dist/drill.html

Cards live in data files and the shell is a renderer over them. Never hardcode
card text into `app.html` — the bank stays portable that way, so a different
front end can read the same JSON.

## Build

    python3 build.py

Writes a single self-contained `dist/drill.html`. Artifacts run under a strict
CSP with no external requests, so everything ships inline.

## Card shape

Diligence backs have five sections in fixed order: **the principle** (the
teaching payload), **how to frame it** (numbered structure), **what matters
most** (where to spend your time), **trap**, and a **follow-up ladder** of three
chained questions revealed one at a time.

Math generators carry a static teaching back plus a reference table — but only
where a table genuinely teaches (conversions, drags, yields). No filler tables
on simple arithmetic.

## Scoring

Session-scoped: drill, self-grade, see what to work on. No cross-device
persistence — if that starts to matter after real use, that is the trigger to
graduate off an artifact, not before.
