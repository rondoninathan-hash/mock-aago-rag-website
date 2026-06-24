#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the fake journal archive.

Reads the article content from articles_data.py and generates, with no
third-party dependencies:

    index.html                  home page listing all 15 articles
    articles/JID-0NN.html       one readable HTML page per article
    data/JID-0NN.txt            plain-text export of each article
    data/JID-0NN.pdf            simple PDF export of each article
    data/articles.json          structured metadata for all 15 articles

Run with:   python3 build.py

There is deliberately NO search, embedding, or AI code here. The RAG layer is
left for the user to build on top of this content.
"""

import html
import json
import os
import re

from articles_data import ARTICLES

ROOT = os.path.dirname(os.path.abspath(__file__))
ARTICLES_DIR = os.path.join(ROOT, "articles")
DATA_DIR = os.path.join(ROOT, "data")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def authors_str(authors):
    """Render an author list as 'A', 'A and B', or 'A, B, and C'."""
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return f"{authors[0]} and {authors[1]}"
    return ", ".join(authors[:-1]) + ", and " + authors[-1]


def plain_text(article):
    """Flatten an article into a single plain-text document (used for .txt,
    the PDF body, and the full_text field in articles.json)."""
    lines = []
    lines.append(article["title"])
    lines.append("")
    lines.append(authors_str(article["authors"]))
    lines.append(
        f"{article['journal']}, Vol. {article['volume']}, "
        f"No. {article['issue']} ({article['year']})"
    )
    lines.append(article["id"])
    lines.append("")
    lines.append("ABSTRACT")
    lines.append(article["abstract"])
    lines.append("")
    for section in article["sections"]:
        lines.append(section["heading"].upper())
        for para in section["paragraphs"]:
            lines.append(para)
            lines.append("")
    lines.append("REFERENCES")
    for i, ref in enumerate(article["references"], 1):
        lines.append(f"[{i}] {ref}")
    return "\n".join(lines).strip() + "\n"


def word_count(article):
    return len(plain_text(article).split())


# --------------------------------------------------------------------------- #
# Minimal dependency-free PDF writer
# --------------------------------------------------------------------------- #
# Produces a valid multi-page PDF using the built-in Helvetica font (one of the
# 14 standard fonts, so no font file needs embedding). Text is wrapped at a
# fixed character width, which is plenty for a practice corpus.

PAGE_W, PAGE_H = 612, 792          # US Letter, in points
MARGIN = 56
LINE_H = 14
FONT_SIZE = 10
WRAP = 92                          # characters per line at this size


def _pdf_escape(text):
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap_paragraph(text, width=WRAP):
    """Greedy word wrap. Returns a list of lines."""
    words = text.split()
    if not words:
        return [""]
    lines, current = [], words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _ascii(text):
    """The standard PDF fonts use a single-byte encoding, so map the few
    non-ASCII characters our content might contain to safe equivalents."""
    replacements = {
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "…": "...", " ": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


def _layout_lines(article):
    """Turn an article into a flat list of (text, style) lines for the PDF,
    where style is 'title', 'meta', 'heading', or 'body'."""
    out = [(article["title"], "title"), ("", "body")]
    out.append((authors_str(article["authors"]), "meta"))
    out.append((
        f"{article['journal']}, Vol. {article['volume']}, "
        f"No. {article['issue']} ({article['year']}) - {article['id']}",
        "meta",
    ))
    out.append(("", "body"))
    out.append(("Abstract", "heading"))
    for line in _wrap_paragraph(article["abstract"]):
        out.append((line, "body"))
    out.append(("", "body"))
    for section in article["sections"]:
        out.append((section["heading"], "heading"))
        for para in section["paragraphs"]:
            for line in _wrap_paragraph(para):
                out.append((line, "body"))
            out.append(("", "body"))
    out.append(("References", "heading"))
    for i, ref in enumerate(article["references"], 1):
        for j, line in enumerate(_wrap_paragraph(f"[{i}] {ref}")):
            out.append((line if j == 0 else "    " + line, "body"))
    return out


def write_pdf(article, path):
    """Write a single article to a minimal multi-page PDF."""
    style_font = {
        "title": ("/F2", 15),     # Helvetica-Bold
        "heading": ("/F2", 12),
        "meta": ("/F1", 9),       # Helvetica
        "body": ("/F1", FONT_SIZE),
    }

    # Paginate.
    pages, current, y = [], [], PAGE_H - MARGIN
    for text, style in _layout_lines(article):
        gap = LINE_H + (4 if style in ("title", "heading") else 0)
        if y - gap < MARGIN:
            pages.append(current)
            current, y = [], PAGE_H - MARGIN
        if style in ("title", "heading"):
            y -= 4
        current.append((text, style, y))
        y -= LINE_H
    if current:
        pages.append(current)

    # Build a content stream per page.
    page_streams = []
    for page in pages:
        parts = ["BT"]
        last_font = None
        for text, style, y in page:
            font_name, size = style_font[style]
            if (font_name, size) != last_font:
                parts.append(f"{font_name} {size} Tf")
                last_font = (font_name, size)
            safe = _pdf_escape(_ascii(text))
            parts.append(f"1 0 0 1 {MARGIN} {y:.1f} Tm ({safe}) Tj")
        parts.append("ET")
        page_streams.append("\n".join(parts))

    # Assemble PDF objects.
    # Object numbering:
    #   1 = Catalog, 2 = Pages, 3 = F1 (Helvetica), 4 = F2 (Helvetica-Bold)
    #   then for each page: a Page object and a Contents stream object.
    objects = {}
    n_pages = len(page_streams)
    page_obj_ids = [5 + 2 * i for i in range(n_pages)]
    content_obj_ids = [6 + 2 * i for i in range(n_pages)]

    objects[1] = "<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects[2] = f"<< /Type /Pages /Count {n_pages} /Kids [{kids}] >>"
    objects[3] = ("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                  "/Encoding /WinAnsiEncoding >>")
    objects[4] = ("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                  "/Encoding /WinAnsiEncoding >>")

    for i in range(n_pages):
        pid, cid = page_obj_ids[i], content_obj_ids[i]
        objects[pid] = (
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {cid} 0 R >>"
        )
        stream = page_streams[i]
        objects[cid] = (
            f"<< /Length {len(stream.encode('latin-1'))} >>\n"
            f"stream\n{stream}\nendstream"
        )

    # Serialise with a cross-reference table.
    out = bytearray()
    out += b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode("latin-1")
        out += objects[num].encode("latin-1")
        out += b"\nendobj\n"

    xref_pos = len(out)
    max_obj = max(objects)
    out += f"xref\n0 {max_obj + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for num in range(1, max_obj + 1):
        out += f"{offsets[num]:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")

    with open(path, "wb") as fh:
        fh.write(out)


# --------------------------------------------------------------------------- #
# HTML rendering
# --------------------------------------------------------------------------- #
PAGE_CSS = """\
:root { --ink:#1a1a1a; --muted:#666; --rule:#ddd; --link:#2a4d8f; }
* { box-sizing: border-box; }
body {
  font: 17px/1.65 Georgia, 'Times New Roman', serif;
  color: var(--ink); background: #fafaf8;
  margin: 0; padding: 2.5rem 1rem 5rem;
}
.wrap { max-width: 740px; margin: 0 auto; }
a { color: var(--link); }
header.site { border-bottom: 2px solid var(--ink); margin-bottom: 2rem;
  padding-bottom: 1rem; }
header.site h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
header.site p { color: var(--muted); margin: 0; font-size: .95rem; }
.meta { color: var(--muted); font-size: .9rem; }
.backlink { font-size: .9rem; }

/* index list */
ul.articles { list-style: none; padding: 0; margin: 0; }
ul.articles li { padding: 1rem 0; border-bottom: 1px solid var(--rule); }
ul.articles .title { font-size: 1.12rem; font-weight: bold; }
ul.articles .sub { color: var(--muted); font-size: .92rem; margin-top: .2rem; }
.jid { font-family: ui-monospace, 'SFMono-Regular', Menlo, monospace;
  font-size: .82rem; color: #fff; background: #444; padding: .08rem .4rem;
  border-radius: 3px; }

/* article page */
article h1 { font-size: 1.5rem; line-height: 1.25; margin: .2rem 0 .6rem; }
article .byline { font-size: 1.02rem; margin: 0 0 .2rem; }
article .pubinfo { margin: 0 0 1.4rem; }
article h2 { font-size: 1.15rem; margin: 1.8rem 0 .5rem;
  border-bottom: 1px solid var(--rule); padding-bottom: .2rem; }
article .abstract { background: #f0efe9; border-left: 3px solid #bbb;
  padding: .8rem 1rem; font-size: .96rem; }
article .abstract strong { font-variant: small-caps; letter-spacing: .03em; }
ol.refs { font-size: .9rem; color: #333; }
ol.refs li { margin-bottom: .4rem; }
footer.site { max-width: 740px; margin: 3rem auto 0; color: var(--muted);
  font-size: .82rem; border-top: 1px solid var(--rule); padding-top: 1rem; }
"""


def esc(text):
    return html.escape(text, quote=False)


# Chatbase chat widget. Injected site-wide before </body> on every page.
# Kept as a plain (non-f) string so the JavaScript braces don't need escaping.
CHATBASE_WIDGET = """<script>
(function(){if(!window.chatbase||window.chatbase("getState")!=="initialized"){window.chatbase=(...arguments)=>{if(!window.chatbase.q){window.chatbase.q=[]}window.chatbase.q.push(arguments)};window.chatbase=new Proxy(window.chatbase,{get(target,prop){if(prop==="q"){return target.q}return(...args)=>target(prop,...args)}})}const onLoad=function(){const script=document.createElement("script");script.src="https://www.chatbase.co/embed.min.js";script.id="2aSqzkdTzkzTeW5pg-0Yi";script.domain="www.chatbase.co";document.body.appendChild(script)};if(document.readyState==="complete"){onLoad()}else{window.addEventListener("load",onLoad)}})();
</script>"""


def render_article_html(article):
    sections_html = []
    for section in article["sections"]:
        paras = "\n".join(
            f"      <p>{esc(p)}</p>" for p in section["paragraphs"]
        )
        sections_html.append(
            f"    <h2>{esc(section['heading'])}</h2>\n{paras}"
        )
    refs_html = "\n".join(
        f"      <li>{esc(ref)}</li>" for ref in article["references"]
    )
    body = "\n".join(sections_html)
    title = esc(article["title"])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(article['id'])} - {title}</title>
<meta name="citation_title" content="{esc(article['title'])}">
<meta name="citation_journal_title" content="{esc(article['journal'])}">
<meta name="citation_volume" content="{article['volume']}">
<meta name="citation_issue" content="{article['issue']}">
<meta name="citation_publication_date" content="{article['year']}">
<style>{PAGE_CSS}</style>
</head>
<body>
<div class="wrap">
  <p class="backlink"><a href="../index.html">&larr; Back to archive index</a></p>
  <article>
    <p class="jid">{esc(article['id'])}</p>
    <h1>{title}</h1>
    <p class="byline">{esc(authors_str(article['authors']))}</p>
    <p class="pubinfo meta">{esc(article['journal'])}, Vol. {article['volume']},
       No. {article['issue']} &middot; {article['year']}</p>
    <div class="abstract"><strong>Abstract.</strong> {esc(article['abstract'])}</div>
{body}
    <h2>References</h2>
    <ol class="refs">
{refs_html}
    </ol>
  </article>
  <p class="backlink" style="margin-top:2rem">
    Raw exports for this article:
    <a href="../data/{article['id']}.txt">.txt</a> &middot;
    <a href="../data/{article['id']}.pdf">.pdf</a> &middot;
    <a href="../data/articles.json">articles.json</a>
  </p>
</div>
<footer class="site">Mock journal archive &mdash; fabricated content for RAG
practice. Not real research.</footer>
{CHATBASE_WIDGET}
</body>
</html>
"""


def render_index_html(articles):
    items = []
    for a in sorted(articles, key=lambda x: x["id"]):
        items.append(
            f"""    <li>
      <div class="title"><a href="articles/{a['id']}.html">{esc(a['title'])}</a></div>
      <div class="sub">{esc(authors_str(a['authors']))} &middot; {a['year']}
        &middot; {esc(a['journal'])}
        &middot; <span class="jid">{esc(a['id'])}</span></div>
    </li>"""
        )
    items_html = "\n".join(items)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mock Journal Archive</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="site">
    <h1>Mock Journal Archive</h1>
    <p>{len(articles)} fabricated articles for retrieval / scraping practice.
       Each links to a full HTML page; raw <code>.txt</code>, <code>.pdf</code>,
       and <code>articles.json</code> exports live in <code>/data</code>.</p>
  </header>
  <ul class="articles">
{items_html}
  </ul>
</div>
<footer class="site">Mock journal archive &mdash; fabricated content for RAG
practice. No search or AI features are included; build those yourself.</footer>
{CHATBASE_WIDGET}
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Main build
# --------------------------------------------------------------------------- #
def main():
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    # Index page.
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(render_index_html(ARTICLES))

    metadata = []
    for article in ARTICLES:
        aid = article["id"]

        # HTML page.
        with open(os.path.join(ARTICLES_DIR, f"{aid}.html"), "w",
                  encoding="utf-8") as fh:
            fh.write(render_article_html(article))

        # Plain text export.
        text = plain_text(article)
        with open(os.path.join(DATA_DIR, f"{aid}.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write(text)

        # PDF export.
        write_pdf(article, os.path.join(DATA_DIR, f"{aid}.pdf"))

        # Metadata for articles.json.
        metadata.append({
            "id": aid,
            "title": article["title"],
            "authors": article["authors"],
            "year": article["year"],
            "volume": article["volume"],
            "issue": article["issue"],
            "journal": article["journal"],
            "abstract": article["abstract"],
            "full_text": text,
        })

        print(f"  {aid}  {word_count(article):>4} words  {article['title'][:48]}")

    with open(os.path.join(DATA_DIR, "articles.json"), "w",
              encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, ensure_ascii=False)

    print(f"\nBuilt {len(ARTICLES)} articles -> index.html, articles/, data/")


if __name__ == "__main__":
    main()
