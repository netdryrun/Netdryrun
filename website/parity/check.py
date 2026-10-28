#!/usr/bin/env python3
"""Parity check between two built copies of the site (Material for MkDocs vs Zensical).

usage: python3 check.py OLD_SITE_DIR NEW_SITE_DIR [--json out.json]

Compares: page URL set, per-page title / meta description / canonical / OpenGraph+Twitter tags / JSON-LD
(types and key fields), static files (robots.txt, llms*.txt, sitemap URLs, CNAME, favicons), internal
links in the NEW build, and the search index. Exits 1 on any gap. Stdlib only.
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin

STATIC = ["robots.txt", "llms.txt", "llms-full.txt", "CNAME", "favicon.ico",
          "assets/favicon.svg", "assets/favicon.ico", "assets/favicon-32.png",
          "assets/netdryrun-mark-180.png", "assets/netdryrun-wordmark-white-tm.svg"]
BASE = "https://netdryrun.com/"
META_KEYS = {"description", "author", "theme-color", "twitter:card", "twitter:image", "twitter:title",
             "twitter:description", "robots"}


class Head(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.in_title = False
        self.meta = {}
        self.canon = None
        self.jsonld = []
        self._ld = None
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, a):
        a = dict(a)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("name"):
            self.ids.add(a["name"])
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            k = a.get("property") or a.get("name")
            if k in META_KEYS or (k or "").startswith("og:"):
                self.meta.setdefault(k, []).append(a.get("content"))
        elif tag == "link" and a.get("rel") == "canonical":
            self.canon = a.get("href")
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._ld = ""
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "script" and self._ld is not None:
            try:
                self.jsonld.append(json.loads(self._ld))
            except ValueError:
                self.jsonld.append({"_invalid": self._ld[:80]})
            self._ld = None

    def handle_data(self, d):
        if self.in_title:
            self.title += d
        if self._ld is not None:
            self._ld += d


def parse(path):
    p = Head()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def pages(root):
    out = {}
    for f in root.rglob("index.html"):
        rel = f.parent.relative_to(root).as_posix()
        out["/" if rel == "." else "/" + rel + "/"] = f
    return out


def flatten(ld):
    out = []
    for blk in ld:
        if isinstance(blk, dict):
            out.extend(blk.get("@graph", [blk]))
    return out


def sig(node):
    """Type plus key fields; the FAQ is compared by its question list."""
    keys = ("@type", "@id", "name", "headline", "url", "description", "datePublished", "softwareVersion",
            "inLanguage")
    s = {k: node.get(k) for k in keys if k in node}
    if "mainEntity" in node:
        s["questions"] = [q.get("name") for q in node["mainEntity"]]
    if "itemListElement" in node:
        s["crumbs"] = [(i.get("name"), i.get("item")) for i in node["itemListElement"]]
    return json.dumps(s, sort_keys=True)


def sitemap_text(root):
    f = root / "sitemap.xml"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def main(old, new, out=None):
    old, new = Path(old), Path(new)
    gaps = []

    def gap(area, msg):
        gaps.append({"area": area, "detail": msg})

    po, pn = pages(old), pages(new)
    for u in sorted(set(po) - set(pn)):
        gap("urls", f"missing in new: {u}")
    for u in sorted(set(pn) - set(po)):
        gap("urls", f"extra in new: {u}")
    parsed_new = {}
    for u in sorted(set(po) & set(pn)):
        a, b = parse(po[u]), parse(pn[u])
        parsed_new[u] = b
        if a.title.strip() != b.title.strip():
            gap("title", f"{u}: {a.title.strip()!r} vs {b.title.strip()!r}")
        if a.canon != b.canon:
            gap("canonical", f"{u}: {a.canon} vs {b.canon}")
        for k in sorted(set(a.meta) | set(b.meta)):
            if a.meta.get(k) != b.meta.get(k):
                gap("meta", f"{u}: {k}: {a.meta.get(k)} vs {b.meta.get(k)}")
        sa, sb = sorted(map(sig, flatten(a.jsonld))), sorted(map(sig, flatten(b.jsonld)))
        for s in sa:
            if s not in sb:
                gap("jsonld", f"{u}: missing/different node {s[:160]}")
        for s in sb:
            if s not in sa:
                gap("jsonld", f"{u}: extra node {s[:160]}")
    for name in STATIC:
        fo, fn = old / name, new / name
        if fo.exists() and not fn.exists():
            gap("static", f"{name} missing in new")
        elif fo.exists() and fo.read_bytes() != fn.read_bytes():
            gap("static", f"{name} differs")
    if (old / "404.html").exists() and not (new / "404.html").exists():
        gap("static", "404.html missing in new")
    for f in old.glob("*.txt"):  # includes the IndexNow key file
        if not (new / f.name).exists() or (new / f.name).read_bytes() != f.read_bytes():
            gap("static", f"{f.name} missing or differs")
    to, tn = sitemap_text(old), sitemap_text(new)
    lo, ln = sorted(re.findall(r"<loc>([^<]+)</loc>", to)), sorted(re.findall(r"<loc>([^<]+)</loc>", tn))
    if lo != ln:
        gap("sitemap", f"URL lists differ: only old {sorted(set(lo) - set(ln))[:5]}, only new {sorted(set(ln) - set(lo))[:5]}")
    if "<lastmod>" in to and "<lastmod>" not in tn:
        gap("sitemap", "old has <lastmod>, new has none")
    # internal links and anchors in the new build
    ids = {u: p.ids for u, p in parsed_new.items()}
    broken = 0
    for u, p in parsed_new.items():
        for h in p.links:
            if re.match(r"(mailto:|tel:|javascript:|data:)", h):
                continue
            full = urljoin(BASE + u.lstrip("/"), h)
            if not full.startswith(BASE):
                continue
            path, frag = urldefrag(full)
            rel = path[len(BASE):].strip("/")
            tgt = new / rel
            ok = tgt.is_file() or (tgt / "index.html").is_file()
            if ok and frag and (tgt / "index.html").is_file():
                ok = frag in ids.get("/" + rel + "/" if rel else "/", {frag})
            if not ok:
                broken += 1
                if broken <= 30:
                    gap("links", f"{u}: broken {h}")
    # search index
    for label, root in (("old", old), ("new", new)):
        idx = list(root.rglob("search_index.json")) + list(root.glob("search.json"))
        if not idx:
            gap("search", f"{label}: no search index file")
            continue
        try:
            d = json.loads(idx[0].read_text(encoding="utf-8"))
            n = len(d.get("items") or d.get("docs") or [])
            if n < 50:
                gap("search", f"{label}: index has only {n} entries ({idx[0].name})")
        except Exception as e:
            gap("search", f"{label}: unreadable index {e}")
    if out:
        Path(out).write_text(json.dumps({"pages_old": len(po), "pages_new": len(pn), "gaps": gaps}, indent=1))
    by = {}
    for g in gaps:
        by[g["area"]] = by.get(g["area"], 0) + 1
    print(f"pages old={len(po)} new={len(pn)}; gaps by area: {by or 'none'}")
    for g in gaps[:60]:
        print(f"  [{g['area']}] {g['detail']}")
    if len(gaps) > 60:
        print(f"  ... {len(gaps) - 60} more")
    return 1 if gaps else 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    out = None
    if "--json" in argv:
        i = argv.index("--json")
        out = argv[i + 1]
        del argv[i:i + 2]
    sys.exit(main(argv[0], argv[1], out))
