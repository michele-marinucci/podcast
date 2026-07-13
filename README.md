# Deep Dives — Podcast Generator

Give it a company name or stock ticker → get a 3-4 hour, two-host, Acquired-style
deep-dive podcast: the full history told as narrative, then investor-grade analysis
(the numbers, 7 Powers, playbook, bull vs. bear, grading, carve-outs).

## Web app (primary interface)

```bash
pip install -r requirements.txt        # + ffmpeg on PATH
export ANTHROPIC_API_KEY=... GLM_API_KEY=... GEMINI_API_KEY=...
uvicorn src.webapp:app                 # http://localhost:8000
```

Flow: type a ticker, optionally upload documents (earnings transcripts, initiation
reports, investor decks — PDF/DOCX/TXT/MD with a doc-type + period per file) →
pipeline maps sources and fetches the corpus (EDGAR filings, YouTube interview
captions, articles, book-derivative material) → writes the cited dossier → you get
the **outline checkpoint** (title, chapters, teasers; add per-chapter notes) →
approve → chapters are written, fact-audited, polished, and voiced one by one,
appearing in the UI as they finish → full episode player + transcript + a
**sources panel** listing everything the episode was built from.

Try the whole flow without API keys or spend:

```bash
DRY_RUN=1 uvicorn src.webapp:app       # canned content + silent audio, real flow
```

Layout: `src/webapp.py` (FastAPI), `src/pipeline.py` (staged orchestration + job
state), `src/fetchers.py` (EDGAR/articles/YouTube/uploads), `web/` (frontend),
`prompts/` (the editorial brain — see `prompts/README.md` for the stage contract).

## Production deploy

The app needs a **persistent single container** (long-running jobs, ffmpeg, local
disk) — serverless platforms like Vercel cannot run it. Two supported paths:

**Render (recommended — no CLI needed).** `render.yaml` is a one-click blueprint:
Render dashboard → *New + → Blueprint* → connect this repo → fill in the four env
vars when prompted (`APP_PASSWORD`, `ANTHROPIC_API_KEY`, `GLM_API_KEY`,
`GEMINI_API_KEY`). It builds the Dockerfile, attaches a 10 GB disk at `/app/output`,
and health-checks `/api/health`. ~$7/mo for the instance + disk.

**Fly.io (CLI).** See the header of `fly.toml` for the four commands.

Operational rules baked into both configs:
- **Exactly one instance.** Jobs run in-process and state lives on the local disk;
  horizontal scaling would split the brain. (Scaling later = job queue + object
  storage — a straightforward refactor when needed.)
- `MAX_ACTIVE_JOBS` (default 2) caps concurrent generations so a burst of requests
  can't run up your API bill; extra requests get a polite 429.
- Set `APP_PASSWORD` or the instance is open to anyone with the URL.
- Set spend limits on the Anthropic / Z.ai / Google consoles as the real backstop.

## How it works

A 3.5-hour episode is ~32,000 words of dialogue — far too long (and too fragile) for a
single generation. The pipeline is staged, and every stage checkpoints to disk:

```
company/ticker
   │
   ▼
1. RESEARCH   Claude + server-side web search → 8-15k word factual dossier
   │          (the single source of truth; writers may not invent facts)
   ▼
2. OUTLINE    Showrunner pass → episode structure as JSON: ~13 segment briefs
   │          with beats, must-use facts, running threads, handoffs
   ▼
3. SEGMENTS   One generation per segment (~2,600 words each), each fed the
   │          dossier + outline + previous segment's tail + "already covered" list
   ▼
4. POLISH     Seam repair between segments, de-dup, TTS hygiene
   │          (+ ElevenLabs v3 audio tags if that provider is selected)
   ▼
5. TTS        Multi-speaker synthesis in ~4.5k-char chunks (resumable)
   ▼
6. STITCH     ffmpeg concat → output/<slug>/episode.mp3
```

All artifacts land in `output/<slug>/` (`01_dossier.md`, `02_outline.json`,
`segments/`, `03_script.txt`, `audio/`, `episode.mp3`). Re-running resumes; delete an
artifact to regenerate that stage. Edit the dossier or outline by hand between runs to
steer the episode.

## Model choices & cost (3.5h episode ≈ 32k words ≈ 190k chars)

**Key insight: TTS dominates the cost, not the LLM.** Choose the script model on
quality; optimize price on the voice side.

### Script generation

| Model | Pricing (in/out per MTok) | Cost/episode | Notes |
|---|---|---|---|
| **GLM 5.2** (default) | $1.40 / $4.40 (Z.ai) — cheaper via OpenRouter | **~$1** | Frontier-class writing at ~1/6 the price of GPT-tier models |
| Claude Sonnet 5 | $3 / $15 | ~$2 | Slightly stronger analysis & prose |
| Claude Opus 4.8 | $5 / $25 | ~$4 | Best analysis; also powers the research stage |

### Research

The research stage defaults to **Claude + server-side web search** regardless of the
script provider — an Acquired-style episode lives or dies on factual grounding, and
GLM's API has no built-in search. (~$1-2/episode including search fees.) You can also
drop 10-Ks / articles into `output/<slug>/sources/` to feed them in directly, or set
`research.provider: script` to run search-free.

### Text-to-speech

| Provider | Price | Cost/episode | Notes |
|---|---|---|---|
| **Gemini Flash TTS** (default) | ~$20/1M audio tokens ≈ $1.80/audio-hour | **~$6** | Native two-speaker dialogue with style steering — the quality/price winner |
| ElevenLabs Flash v2.5 | $0.05/1k chars | ~$9.50 | Good, less emotional range |
| MiniMax Speech 2.6 | ~$0.06/1k chars | ~$11 | Long-text mode: 200k chars/request |
| ElevenLabs v3 (dialogue) | $0.10/1k chars | ~$19 | Most expressive; inline `[laughs]`/`[sighs]` audio tags |

**Totals:** default stack ≈ **$8-9/episode**; premium stack (Opus 4.8 + ElevenLabs v3)
≈ **$24/episode**.

## Setup

```bash
pip install -r requirements.txt
# ffmpeg must be on PATH

export ANTHROPIC_API_KEY=...    # research stage (and/or anthropic script provider)
export GLM_API_KEY=...          # Z.ai — or OPENROUTER_API_KEY (see config.yaml)
export GEMINI_API_KEY=...       # Gemini TTS
# export ELEVENLABS_API_KEY=... # only if tts.provider: elevenlabs
```

Review `config.yaml` — providers, hosts' names, runtime, voices are all there.

## CLI usage (headless alternative)

```bash
python -m src.generate "Costco"                 # full pipeline
python -m src.generate NVDA --runtime 240       # 4-hour episode
python -m src.generate "Costco" --script-only   # stop before TTS (review the script)
python -m src.generate "Costco" --tts-only      # voice an existing/edited script
```

Recommended workflow: run `--script-only` first, skim `03_script.txt` (and spot-check
numbers against `01_dossier.md`), then `--tts-only`.

## Publishing to Apple Podcasts / Spotify

Episodes are saved to `output/<slug>/episode.mp3`. Apple and Spotify don't accept MP3
uploads directly — they ingest a **podcast RSS feed** at a public URL. Two routes:

### Route A — zero infrastructure (manual)

Upload `episode.mp3` to a free podcast host like **Spotify for Creators**
(creators.spotify.com). It hosts the audio, generates the RSS feed, publishes to
Spotify instantly, and can distribute to Apple Podcasts too. Easiest if you publish
occasionally.

### Route B — automated (`src/publish.py`)

Self-host the feed on any S3-compatible bucket. **Cloudflare R2 recommended**: free
egress means people streaming your 3-hour episodes costs you ~$0.

One-time setup:
1. Create an R2 bucket, enable public access (r2.dev URL or a custom domain).
2. Create an R2 API token; export `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`.
3. Fill in the `publish:` section of `config.yaml` — including `show.image_url`
   (Apple requires 3000x3000 cover art) and `show.email` (Apple verifies it).

Then per episode:

```bash
python -m src.publish "Costco"     # upload MP3 + regenerate/upload feed.xml
git add feed/ && git commit -m "publish costco"   # keep the episode manifest
```

Submit `https://<your-public-url>/feed.xml` **once**:
- **Spotify**: creators.spotify.com → Add your podcast → "I have a podcast elsewhere" → paste feed URL
- **Apple**: podcastsconnect.apple.com → Add show → "Add a show with an RSS feed"

Every later `publish` run updates the feed; both platforms pick up new episodes
automatically (Apple can take a few hours).

### Private listening (just for you)

Skip the directories entirely: in the Apple Podcasts app, **Library → ⋯ → Follow a
Show by URL** and paste your `feed.xml` URL. Works immediately, no review, nothing
public-facing. Spotify doesn't support arbitrary RSS URLs — for Spotify the show must
go through a host/directory (Route A or B), or use an app like Pocket Casts which
follows any RSS URL.

## The prompts

The editorial craft lives in `prompts/` — tune these to change the show:

- `01_research.md` — the dossier spec: 16 required sections, sourcing rules, `[UNVERIFIED]` flagging
- `02_outline.md` — the showrunner: macro-arc, act structure, running threads, JSON segment briefs
- `03_segment_writer.md` — **the master prompt**: host personas, grounding rules, TTS-clean output format, and the storytelling craft (stakes-first scenes, numbers-as-drama, callbacks, honest hedging, host disagreements)
- `04_polish.md` — seam repair, de-duplication, TTS hygiene, optional ElevenLabs audio tags

## Notes & caveats

- **Verify TTS model IDs** against provider docs before first run (e.g. Gemini's current
  TTS model name); they churn faster than LLM IDs. Both are configurable in `config.yaml`.
- Long-form factuality: the pipeline hard-separates research from writing precisely so
  hallucinations can be caught by reviewing one file (the dossier). Fabricated quotes are
  banned at both the research and writing layers.
- Voice consistency across chunks: Gemini prebuilt voices and ElevenLabs voice IDs are
  deterministic per chunk, so stitching is seamless; keep chunks ≤ ~5 min for reliability.
