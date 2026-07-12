"""Corpus builders: SEC EDGAR filings, web articles, YouTube captions, and
user-uploaded documents (PDF/DOCX/TXT/MD).

Everything is best-effort: a failed fetch logs and skips — the dossier prompt
works with whatever corpus it gets and fills gaps via web search.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import requests

SEC_HEADERS = {"User-Agent": "podcast-deep-dives research contact@example.com"}
MAX_DOC_CHARS = 250_000
MAX_CORPUS_CHARS = 1_500_000


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


@dataclass
class CorpusDoc:
    label: str          # "[S3]"
    type: str           # s1_filing | 10k_filing | article | interview_transcript | user_upload | ...
    title: str
    url: str            # "-" for uploads
    text: str
    licensed: bool = False


def html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s{2,}", " ", text)


# ------------------------------------------------------------------ EDGAR


def _cik_for(query: str) -> tuple[int, str] | None:
    data = requests.get(
        "https://www.sec.gov/files/company_tickers.json", headers=SEC_HEADERS, timeout=30
    ).json()
    q = query.strip().upper()
    for row in data.values():
        if row["ticker"].upper() == q:
            return row["cik_str"], row["title"]
    for row in data.values():  # fallback: name substring
        if q in row["title"].upper():
            return row["cik_str"], row["title"]
    return None


def fetch_filings(company: str, wanted: list[dict]) -> list[CorpusDoc]:
    """wanted: [{"type": "10-K", "year": 2008, "why": ...}, ...] from the source map."""
    hit = _cik_for(company)
    if not hit:
        log(f"[edgar] no CIK found for {company!r}")
        return []
    cik, title = hit
    subs = requests.get(
        f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=SEC_HEADERS, timeout=30
    ).json()
    recent = subs["filings"]["recent"]
    rows = list(zip(recent["form"], recent["filingDate"], recent["accessionNumber"],
                    recent["primaryDocument"]))

    docs: list[CorpusDoc] = []
    for want in wanted:
        form_type = want.get("type", "10-K")
        year = want.get("year")
        matches = [r for r in rows if r[0] == form_type or r[0].startswith(form_type)]
        if year:
            matches = [r for r in matches if abs(int(r[1][:4]) - int(year)) <= 1] or matches
        if not matches:
            log(f"[edgar] no {form_type} ({year}) in recent filings for {title}")
            continue
        form, date, accession, primary = matches[0]
        url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/"
               f"{accession.replace('-', '')}/{primary}")
        try:
            html = requests.get(url, headers=SEC_HEADERS, timeout=60).text
            text = html_to_text(html)[:MAX_DOC_CHARS]
            docs.append(CorpusDoc("", f"{form_type.lower().replace(' ', '')}_filing",
                                  f"{title} {form} ({date})", url, text))
            log(f"[edgar] fetched {form} {date} ({len(text)} chars)")
        except Exception as e:  # noqa: BLE001
            log(f"[edgar] failed {url}: {e}")
    return docs


# ------------------------------------------------------------------ articles


def fetch_article(url: str, title: str, doc_type: str = "article") -> CorpusDoc | None:
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (research)"})
        resp.raise_for_status()
        text = html_to_text(resp.text)
        if len(text) < 1500:  # paywall shell / consent page
            log(f"[article] too short, likely paywalled: {url}")
            return None
        return CorpusDoc("", doc_type, title, url, text[:MAX_DOC_CHARS])
    except Exception as e:  # noqa: BLE001
        log(f"[article] failed {url}: {e}")
        return None


# ------------------------------------------------------------------ youtube


YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/)([\w-]{11})")


def fetch_youtube(url: str, title: str) -> CorpusDoc | None:
    m = YT_ID_RE.search(url)
    if not m:
        log(f"[youtube] no video id in {url}")
        return None
    vid = m.group(1)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        try:  # v1.x API
            fetched = YouTubeTranscriptApi().fetch(vid)
            snippets = getattr(fetched, "snippets", fetched)
            text = " ".join(getattr(s, "text", None) or s["text"] for s in snippets)
        except AttributeError:  # legacy API
            text = " ".join(d["text"] for d in YouTubeTranscriptApi.get_transcript(vid))
        text = re.sub(r"\s{2,}", " ", text)
        return CorpusDoc("", "interview_transcript", title, url, text[:MAX_DOC_CHARS])
    except Exception as e:  # noqa: BLE001
        log(f"[youtube] no transcript for {url}: {e}")
        return None


# ------------------------------------------------------------------ uploads


def extract_upload_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(errors="replace")
    if suffix == ".pdf":
        from pypdf import PdfReader

        return "\n".join((page.extract_text() or "") for page in PdfReader(path).pages)
    if suffix == ".docx":
        import docx

        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    raise ValueError(f"Unsupported upload type: {path.name}")


LICENSED_TYPES = {"initiation_report", "expert_call", "newsletter", "book_excerpt"}


def load_uploads(uploads_dir: Path) -> list[CorpusDoc]:
    """Reads uploads_dir/manifest.json: [{"file": ..., "doc_type": ..., "period": ...}].
    Files without a manifest entry default to doc_type=user_upload."""
    if not uploads_dir.is_dir():
        return []
    manifest = {}
    mpath = uploads_dir / "manifest.json"
    if mpath.exists():
        manifest = {m["file"]: m for m in json.loads(mpath.read_text())}
    docs = []
    for path in sorted(uploads_dir.iterdir()):
        if path.name == "manifest.json" or path.is_dir():
            continue
        meta = manifest.get(path.name, {})
        doc_type = meta.get("doc_type", "user_upload")
        try:
            text = extract_upload_text(path)[:MAX_DOC_CHARS]
        except Exception as e:  # noqa: BLE001
            log(f"[uploads] failed {path.name}: {e}")
            continue
        period = f" ({meta['period']})" if meta.get("period") else ""
        docs.append(CorpusDoc("", doc_type, f"{path.stem}{period} (user-provided)", "-",
                              text, licensed=doc_type in LICENSED_TYPES))
        log(f"[uploads] {path.name}: {len(text)} chars as {doc_type}")
    return docs


# ------------------------------------------------------------------ assembly


def build_corpus(company: str, source_map: dict, uploads_dir: Path, out_dir: Path) -> tuple[str, list[dict]]:
    """Fetch everything, label [S#], write corpus.txt + corpus_manifest.json.
    Returns (corpus_text, manifest)."""
    docs: list[CorpusDoc] = []
    docs += load_uploads(uploads_dir)  # user material first — highest specificity
    docs += fetch_filings(company, source_map.get("filings", []))

    for item in source_map.get("interviews", []):
        if "youtube" in item.get("url", "") or item.get("platform") == "youtube":
            d = fetch_youtube(item["url"], item.get("title", "interview"))
        else:
            d = fetch_article(item.get("url", ""), item.get("title", "interview"),
                              "interview_transcript")
        if d:
            docs.append(d)

    for book in source_map.get("books", []):
        for der in book.get("derivative_sources", []):
            if der.get("paywalled"):
                continue
            fetcher = fetch_youtube if "youtube" in der.get("url", "") else fetch_article
            d = fetcher(der.get("url", ""), f"{der.get('title', '')} (re: {book['title']})")
            if d:
                d.type = f"book_{der.get('type', 'derivative')}"
                docs.append(d)

    for art in source_map.get("articles", []) + source_map.get("archives", []):
        if art.get("paywalled"):
            continue
        d = fetch_article(art.get("url", ""), art.get("title", "article"))
        if d:
            docs.append(d)

    # label + enforce total budget
    total = 0
    kept: list[CorpusDoc] = []
    for doc in docs:
        if total + len(doc.text) > MAX_CORPUS_CHARS:
            doc.text = doc.text[: max(0, MAX_CORPUS_CHARS - total)]
        if len(doc.text) < 500:
            continue
        doc.label = f"[S{len(kept) + 1}]"
        kept.append(doc)
        total += len(doc.text)
        if total >= MAX_CORPUS_CHARS:
            log("[corpus] budget reached; dropping remaining sources")
            break

    corpus = "\n\n".join(
        f"{d.label} | {d.type} | {d.title} | {d.url}\n\n{d.text}" for d in kept
    )
    manifest = [{k: v for k, v in asdict(d).items() if k != "text"} for d in kept]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "corpus.txt").write_text(corpus)
    (out_dir / "corpus_manifest.json").write_text(json.dumps(manifest, indent=2))
    log(f"[corpus] {len(kept)} documents, {total} chars")
    return corpus, manifest
