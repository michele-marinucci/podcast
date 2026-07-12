# Prompt Suite — Pipeline Contract (v2, web-app design)

Design decisions baked in: **web app for end users** (fully autonomous — no human
review of scripts) · **outline checkpoint** (user sees/edits the outline before the
expensive run) · **listener-facing sources panel** (citations flow end-to-end) ·
**staged generation** (a 3-4h episode ≈ 32k words is beyond one reliable generation).

## Stages

| # | Prompt | Input | Output | Notes |
|---|---|---|---|---|
| 0 | `00_source_map.md` | company, date | JSON source map | Needs web search. Feeds the fetchers. |
| 0b | *(fetchers — code, not a prompt)* | source map | corpus of docs labeled `[S1]..[Sn]` | EDGAR, transcript APIs, YouTube captions, Whisper, article extraction |
| 1 | `01_research.md` | company, date, corpus (+optional web search) | cited dossier (md) | Every claim carries `[S#]` or `(Pub, YYYY)`; §16 Source Register feeds the sources panel |
| 2 | `02_outline.md` | dossier, runtime, prefs | strict JSON outline | **← UI checkpoint**: show title/logline/chapter teasers; user edits land as `user_notes` on segment briefs |
| 3 | `03_segment_writer.md` | dossier + outline + brief + prev tail + covered list | one segment of `NAME: line` dialogue | One call per segment (~2.6k words). Citations become on-air attribution, never markup |
| 3b | `03b_fact_audit.md` | dossier + segment | JSON verdict + exact-substitution fixes | Backend string-replaces `line_quote` → `replacement`; re-runs writer on `fail` |
| 4 | `04_polish.md` | segment + neighbor seams | corrected segment | Seam repair, TTS hygiene, artifact stripping; ElevenLabs audio tags optional |

Then: TTS per segment (chunked) → stitch. Segments are locally final after 3b/4, so
**TTS can start on segment 1 while segment 6 is still writing** — stream chapters to
the user as they finish.

## Template variables

| Variable | Used in | Source |
|---|---|---|
| `{{COMPANY}}`, `{{DATE}}` | 00, 01, 02, 03 | request |
| `{{USER_MATERIALS}}` | 00 | upload list summary ("none" if empty) |
| `{{RUNTIME_MINUTES}}`, `{{TARGET_WORDS}}`, `{{SEGMENT_COUNT}}`, `{{WORDS_PER_SEGMENT}}` | 02, 03 | user setting → backend math |
| `{{USER_PREFERENCES}}` | 02 | user knobs (story-vs-analysis balance, tone, focus areas) |
| `{{HOST_A}}`, `{{HOST_B}}` | 03 | product config (or user setting) |
| `{{AUDIO_TAGS_RULE}}` | 04 | set iff TTS provider is ElevenLabs v3 |

## User uploads

The episode-creation screen accepts documents that join the corpus alongside fetched
sources. Ranked by value per upload (use this as UI copy):

| Upload | Why it's gold | Notes |
|---|---|---|
| **Sell-side initiation reports** | An initiation-of-coverage report IS a mini-dossier: history, business model, unit economics, competitive map, valuation — the single highest-value upload | Licensed → grounding only, listed generically in sources panel |
| **Earnings call transcripts** | Management's voice quarter by quarter; users often have brokerage access we don't | Ask for the *inflection* quarters, not just recent ones |
| **Investor day / analyst day decks** | The company's own strategy narrative + segment disclosures that never make the 10-K | PDF-heavy — needs slide text extraction |
| **Expert-network call transcripts** (Tegus/AlphaSense) | Operator-level detail on how the business actually works | Licensed → same handling as initiations |
| **Paid newsletter deep dives** | Often the best synthesis writing on a company | Licensed |
| **Book excerpts / their own book notes** | Closes the gap stage 0 can only approximate | Personal-use materials; grounding only |
| **User's own thesis / notes** | Doubles as steering — "emphasize the logistics story" | Facts appearing *only* here stay `[UNVERIFIED]` |
| **(Private companies)** pitch decks, data-room docs | Only path to real numbers for non-filers | Confidential → never surface in sources panel |

Intake spec:
- **Formats**: PDF, DOCX, TXT, MD; transcripts also as pasted text. Extract to plain
  text before corpus assembly.
- **Metadata per file** (one dropdown + one text field): document type (from the table
  above) and period/date. Everything else is inferable.
- **Corpus labeling**: same `[S#]` namespace, `user_upload` type (see format below).
- **Trust tier**: filings > official transcripts > journalism/interviews > user uploads
  > web search — encoded in `01_research.md`; numeric conflicts resolve toward filings.
- **Prompt-injection guard**: uploads are untrusted data; `01_research.md` instructs
  the model to ignore instruction-like text inside documents and flag it.
- **Licensing**: licensed uploads ground facts but are never quoted at length (>25
  words) and appear only generically in the public sources panel.
- **Dedup**: the upload list is passed to stage 0 as `{{USER_MATERIALS}}` so the source
  map targets gaps instead of re-fetching what the user provided.

## Corpus format (stage 0b → 1)

Concatenate fetched documents, each prefixed with a header line:

```
[S1] | s1_filing | Amazon S-1 (1997) | https://www.sec.gov/...
<text>

[S2] | interview_transcript | Jeff Bezos — Lex Fridman #405 (2023-12) | https://youtube.com/...
<text>
```

Budget guidance: cap the corpus around 300-500k tokens (1M-context models handle it;
otherwise chunk-summarize the longest transcripts first). Filings: strip XBRL/exhibits,
keep Business, Risk Factors, MD&A.

## UI hooks these prompts assume

1. **Progress**: stage names + outline metadata (title, chapter list) are available
   ~2 min in — render the episode page skeleton immediately.
2. **Outline checkpoint**: title, logline, `segments[].title` + `segments[].teaser`
   are written for that screen; user notes round-trip via `user_notes`.
3. **Sources panel**: render the dossier's §16 Source Register (type, title, URL).
4. **Chapters**: segment boundaries map 1:1 to podcast chapter markers.

## Legal guardrails encoded in the prompts

- No fact outside the cited dossier (01, 03, audited by 03b).
- Quotes must be verbatim + attributed or they don't air (01 §15, 03 rule 1, 03b).
- Real-person rules: criticize decisions, never character/private life; legal matters
  stated only as the documented record with attribution (01 §11, 03 rule 1c, 03b policy).
- Books are never ingested — only their legal shadow (00): published excerpts, author
  interviews, reviews, talks.
