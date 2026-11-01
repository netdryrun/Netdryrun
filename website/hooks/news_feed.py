"""Write news/feed.xml, an RSS 2.0 feed of the News posts (docs/news/posts/*.md), after each build.

Built from the posts' own front matter (title, date, slug, description), so the feed always matches the
pages. No plugin or extra dependency: the Pages workflow installs only mkdocs-material.
"""
from datetime import date, datetime, time, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

SITE = "https://netdryrun.com/"


def _when(value) -> datetime:
    if isinstance(value, dict):
        value = value.get("created")
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time(12, 0), tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)


def on_post_build(config):
    posts = []
    for path in sorted(Path(config["docs_dir"], "news", "posts").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---") else {}
        if meta.get("draft"):
            continue
        posts.append((_when(meta["date"]), meta))
    posts.sort(key=lambda p: p[0], reverse=True)
    items = []
    for when, meta in posts:
        link = f"{SITE}news/{meta['slug']}/"
        items.append(
            "    <item>\n"
            f"      <title>{escape(meta['title'])}</title>\n"
            f"      <link>{link}</link>\n"
            f"      <guid isPermaLink=\"true\">{link}</guid>\n"
            f"      <pubDate>{format_datetime(when)}</pubDate>\n"
            f"      <description>{escape(meta.get('description', ''))}</description>\n"
            "    </item>")
    built = format_datetime(posts[0][0]) if posts else format_datetime(datetime.now(timezone.utc))
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        "    <title>Netdryrun news</title>\n"
        f"    <link>{SITE}news/</link>\n"
        f'    <atom:link href="{SITE}news/feed.xml" rel="self" type="application/rss+xml"/>\n'
        "    <description>Netdryrun releases, findings and write-ups.</description>\n"
        "    <language>en</language>\n"
        f"    <lastBuildDate>{built}</lastBuildDate>\n"
        + "\n".join(items) + "\n"
        "  </channel>\n"
        "</rss>\n")
    out = Path(config["site_dir"], "news", "feed.xml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(feed, encoding="utf-8", newline="\n")
