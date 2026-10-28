"""Per-page schema.org JSON-LD for search engines and AI assistants.

The site-wide graph (SoftwareApplication, Organization, WebSite) is in overrides/main.html. This hook adds
what depends on the page: a BreadcrumbList on every page but the home page, FAQPage on the FAQ (built from
its H2 questions, so the markup always matches the visible text), BlogPosting on posts, and TechArticle on
the guides, tutorial and reference pages. main.html prints page.meta["jsonld"].
"""
import html
import json
import re

SITE = "https://netdryrun.com/"
ORG = {"@id": SITE + "#organization"}
SOFTWARE = {"@id": SITE + "#software"}

ARTICLES = ("tutorial.md", "examples.md", "recipes.md", "batfish.md", "ai-agents.md", "github-action.md",
            "when-to-use-what.md", "troubleshooting.md", "getting-started.md", "how-its-built.md", "corpus.md")
ARTICLE_DIRS = ("guides/", "reference/", "corpus/")


def _text(fragment: str) -> str:
    fragment = re.sub(r'<a class="headerlink"[^>]*>.*?</a>', "", fragment, flags=re.S)
    fragment = re.sub(r"<(script|style)\b.*?</\1>", "", fragment, flags=re.S)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(fragment).replace("¶", "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\(\s+", "(", text)
    return re.sub(r"\s+([.,;:)])", r"\1", text)


def _faq(content: str) -> list[dict]:
    parts = re.split(r"<h2\b[^>]*>(.*?)</h2>", content, flags=re.S)
    out = []
    for i in range(1, len(parts) - 1, 2):
        question, answer = _text(parts[i]), _text(parts[i + 1])
        if question.endswith("?") and answer:
            out.append({"@type": "Question", "name": question,
                        "acceptedAnswer": {"@type": "Answer", "text": answer}})
    return out


def build_jsonld(src, url, title, description, content, markdown, is_home):
    """The per-page JSON-LD string (or None). Shared by the MkDocs hook and postbuild_jsonld.py (Zensical)."""
    graph = []
    if not is_home:
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Netdryrun", "item": SITE},
            {"@type": "ListItem", "position": 2, "name": title, "item": url},
        ]})
    base = {"headline": title, "description": description, "url": url, "mainEntityOfPage": url,
            "inLanguage": "en", "publisher": ORG, "author": ORG, "about": SOFTWARE}
    if src == "faq.md":
        questions = _faq(content)
        if questions:
            graph.append({"@type": "FAQPage", "@id": url + "#faq", "url": url, "name": title,
                          "about": SOFTWARE, "mainEntity": questions})
    elif src.startswith("posts/"):
        post = {"@type": "BlogPosting", **base}
        date = re.search(r"\b(20\d\d-\d\d-\d\d)\b", markdown[:400])
        if date:
            post["datePublished"] = date.group(1)
        graph.append(post)
    elif src in ARTICLES or src.startswith(ARTICLE_DIRS):
        graph.append({"@type": "TechArticle", **base})
    if not graph:
        return None
    data = {"@context": "https://schema.org", "@graph": graph}
    # "</" inside a <script> element would end it early.
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def on_page_content(content, page, config, files):
    url = page.canonical_url or (SITE + page.url)
    jsonld = build_jsonld(page.file.src_uri, url, _text(page.title or ""),
                          page.meta.get("description") or config["site_description"],
                          content, page.markdown, page.is_homepage)
    if jsonld:
        page.meta["jsonld"] = jsonld
    return content
