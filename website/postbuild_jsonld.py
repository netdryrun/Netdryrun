#!/usr/bin/env python3
"""Add the per-page schema.org JSON-LD to a built site (the Zensical replacement for the MkDocs hook).

Zensical 0.0.73 does not run MkDocs `hooks:`, so hooks/structured_data.py never fires. This script reuses its
build_jsonld() on the built HTML: title, description and canonical are read back from each page's <head>, the
FAQ questions from the rendered <article>, the post date from the Markdown source.

usage: python3 postbuild_jsonld.py [SITE_DIR=site] [DOCS_DIR=docs]   (run from website/)
"""
import html
import importlib.util
import re
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("structured_data", here / "hooks" / "structured_data.py")
sd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sd)

site = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
docs = Path(sys.argv[2] if len(sys.argv) > 2 else "docs")


def meta(page, name):
    m = re.search(r'<meta name="%s" content="([^"]*)"' % name, page)
    return html.unescape(m.group(1)) if m else ""


def source(rel):
    """URL path ('faq/') -> (src_uri, markdown text)."""
    for cand in ([rel.rstrip("/") + ".md", rel + "index.md"] if rel else ["index.md"]):
        if (docs / cand).is_file():
            return cand, (docs / cand).read_text(encoding="utf-8")
    return "", ""


added = skipped = 0
for f in sorted(site.rglob("index.html")):
    rel = f.parent.relative_to(site).as_posix()
    rel = "" if rel == "." else rel + "/"
    page = f.read_text(encoding="utf-8")
    if 'type="application/ld+json">{"@context": "https://schema.org", "@graph": [{"@type": "BreadcrumbList"' in page:
        continue  # already done
    canon = re.search(r'<link rel="canonical" href="([^"]*)"', page)
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    article = re.search(r"<article[^>]*>(.*)</article>", page, re.S)
    src, md = source(rel)
    if not (canon and title and article and src):
        skipped += 1
        continue
    # MkDocs' page.title is the navigation title (the sidebar label), not the <title>, which may come from front matter.
    active = re.search(r'md-nav__link--active"[^>]*>\s*<span class="md-ellipsis">\s*(.*?)\s*</span>', page, re.S)
    name = html.unescape(re.sub(r"\s+", " ", title.group(1))).strip()
    name = name[: -len(" - Netdryrun")] if name.endswith(" - Netdryrun") else name
    if active:
        name = active.group(1)
    data = sd.build_jsonld(src, canon.group(1), sd._text(name), meta(page, "description") or "",
                           article.group(1), md, rel == "")
    if not data:
        continue
    tag = '<script type="application/ld+json">%s</script>' % data
    f.write_text(page.replace("</head>", "  " + tag + "\n</head>", 1), encoding="utf-8")
    added += 1
print(f"postbuild_jsonld: added to {added} pages, skipped {skipped}")

# Zensical's sitemap has no <lastmod>; Material's carried the build date. Keep it (same meaning: the deploy date).
import datetime
sm = site / "sitemap.xml"
if sm.is_file() and "<lastmod>" not in sm.read_text(encoding="utf-8"):
    day = datetime.date.today().isoformat()
    sm.write_text(re.sub(r"(<loc>[^<]+</loc>)", r"\1\n        <lastmod>%s</lastmod>" % day,
                         sm.read_text(encoding="utf-8")), encoding="utf-8")
    print("postbuild_jsonld: sitemap lastmod =", day)
