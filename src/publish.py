"""Publish episodes to a podcast RSS feed on S3-compatible storage.

Uploads output/<slug>/episode.mp3 to your bucket, updates feed/episodes.json,
regenerates feed.xml, and uploads that too. Point Apple Podcasts / Spotify at
<public_base_url>/feed.xml once; new episodes then appear automatically.

Usage:
    python -m src.publish "Costco"                      # publish an episode
    python -m src.publish "Costco" --title "Costco"     # override episode title
    python -m src.publish --feed-only                   # regenerate + upload feed only
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import os
import re
import subprocess
import sys
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "feed" / "episodes.json"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def probe_duration(path: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return int(float(out))


def fmt_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def s3_client(pub: dict):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=pub["endpoint_url"],
        aws_access_key_id=os.environ[pub.get("access_key_env", "R2_ACCESS_KEY_ID")],
        aws_secret_access_key=os.environ[pub.get("secret_key_env", "R2_SECRET_ACCESS_KEY")],
    )


def upload(client, bucket: str, key: str, path: Path | None = None, body: bytes | None = None,
           content_type: str | None = None) -> None:
    kwargs = {"Bucket": bucket, "Key": key}
    if content_type:
        kwargs["ContentType"] = content_type
    if path is not None:
        client.upload_file(str(path), bucket, key,
                           ExtraArgs={"ContentType": content_type} if content_type else None)
    else:
        client.put_object(Body=body, **kwargs)


def build_feed(show: dict, base_url: str, episodes: list[dict]) -> str:
    def e(text: object) -> str:
        return escape(str(text or ""))

    items = []
    for ep in sorted(episodes, key=lambda x: x["pub_date"], reverse=True):
        pub = format_datetime(dt.datetime.fromisoformat(ep["pub_date"]))
        items.append(f"""    <item>
      <title>{e(ep['title'])}</title>
      <description>{e(ep['description'])}</description>
      <enclosure url="{e(ep['url'])}" length="{ep['size_bytes']}" type="audio/mpeg"/>
      <guid isPermaLink="false">{e(ep['url'])}</guid>
      <pubDate>{pub}</pubDate>
      <itunes:duration>{fmt_duration(ep['duration_secs'])}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>""")

    image = (f'\n    <itunes:image href="{e(show["image_url"])}"/>'
             f'\n    <image><url>{e(show["image_url"])}</url>'
             f'<title>{e(show["title"])}</title><link>{e(base_url)}</link></image>'
             if show.get("image_url") else "")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{e(show['title'])}</title>
    <link>{e(base_url)}</link>
    <description>{e(show['description'])}</description>
    <language>{e(show.get('language', 'en'))}</language>
    <atom:link href="{e(base_url)}/feed.xml" rel="self" type="application/rss+xml"/>
    <itunes:author>{e(show.get('author', ''))}</itunes:author>
    <itunes:owner>
      <itunes:name>{e(show.get('author', ''))}</itunes:name>
      <itunes:email>{e(show.get('email', ''))}</itunes:email>
    </itunes:owner>
    <itunes:category text="{e(show.get('category', 'Business'))}"/>
    <itunes:explicit>{'true' if show.get('explicit') else 'false'}</itunes:explicit>{image}
{chr(10).join(items)}
  </channel>
</rss>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish an episode to your podcast RSS feed")
    parser.add_argument("company", nargs="?", help="Company name or slug (matches output/<slug>/)")
    parser.add_argument("--title", help="Episode title override")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--feed-only", action="store_true", help="Regenerate and upload feed.xml only")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    pub = cfg.get("publish")
    if not pub:
        sys.exit("Add a `publish:` section to config.yaml (see README → Publishing)")
    base_url = pub["public_base_url"].rstrip("/")
    client = s3_client(pub)

    MANIFEST.parent.mkdir(exist_ok=True)
    episodes: list[dict] = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []

    if not args.feed_only:
        if not args.company:
            sys.exit("Provide a company/slug, or use --feed-only")
        slug = re.sub(r"[^a-z0-9]+", "-", args.company.lower()).strip("-")
        ep_dir = ROOT / "output" / slug
        mp3 = ep_dir / "episode.mp3"
        if not mp3.exists():
            sys.exit(f"{mp3} not found — run the generator first")

        title, description = args.company, ""
        outline_path = ep_dir / "02_outline.json"
        if outline_path.exists():
            outline = json.loads(outline_path.read_text())
            title = args.title or outline.get("episode_title", title)
            description = outline.get("logline", "")

        key = f"episodes/{slug}.mp3"
        log(f"[publish] uploading {mp3} -> {pub['bucket']}/{key}")
        upload(client, pub["bucket"], key, path=mp3, content_type="audio/mpeg")

        entry = {
            "slug": slug,
            "title": title,
            "description": description,
            "url": f"{base_url}/{key}",
            "size_bytes": mp3.stat().st_size,
            "duration_secs": probe_duration(mp3),
            "pub_date": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        episodes = [e for e in episodes if e["slug"] != slug] + [entry]
        MANIFEST.write_text(json.dumps(episodes, indent=2))
        log(f"[publish] manifest updated ({len(episodes)} episodes)")

    feed = build_feed(pub["show"], base_url, episodes)
    (ROOT / "feed" / "feed.xml").write_text(feed)
    upload(client, pub["bucket"], "feed.xml", body=feed.encode(),
           content_type="application/rss+xml")
    log(f"[publish] feed live at {base_url}/feed.xml")
    log("[publish] commit feed/episodes.json so the manifest survives this machine")


if __name__ == "__main__":
    main()
