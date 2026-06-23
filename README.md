# Mock Journal Archive

A small, self-contained **fake academic journal archive** built as a practice
harness for retrieval-augmented generation (RAG) and web-scraping experiments.

It contains **15 fabricated articles** (`JID-001` … `JID-015`), each on a
deliberately different topic — deep-sea anglerfish lures, medieval coinage,
competitive Tetris, mycorrhizal soil networks, the history of traffic lights,
sourdough microbiology, Antarctic ice cores, colour-term linguistics, the
honeybee waggle dance, pipe-organ restoration, Roman marine concrete, octopus
sleep, phantom islands, desert fulgurites, and postwar Japanese vending
machines.

> **Everything here is invented.** The authors, journals, volumes, references,
> and findings are not real. The content exists only to give a retrieval
> system realistic, varied text to distinguish between.

There is **no search, embeddings, vector database, or AI** of any kind in this
repo — that part is intentionally left empty for you to build.

## Run it

This is a plain static site. The repo already ships with the generated files,
so you can serve it directly with Python's built-in server:

```bash
python3 -m http.server 8000
```

Then open <http://localhost:8000/> — the home page lists all 15 articles, and
each links to its own readable HTML page (good for scraping/parsing practice).

## Regenerating the content

All articles live as structured data in [`articles_data.py`](articles_data.py).
To rebuild the HTML pages and the `/data` exports from that source, run:

```bash
python3 build.py
```

`build.py` has **no third-party dependencies** (the PDF writer is implemented
from scratch in pure Python), so it runs on a stock Python 3 install.

## Where the raw files live

The `/data` folder holds the same 15 articles in three ingestion-friendly
formats, so you can practice loading them several ways:

| Path                    | What it is                                                        |
| ----------------------- | ----------------------------------------------------------------- |
| `data/JID-0NN.txt`      | Plain-text version of each article (one file per article).        |
| `data/JID-0NN.pdf`      | Simple PDF version of each article (one file per article).        |
| `data/articles.json`    | **All 15 articles** as structured metadata in a single JSON file. |

Each object in `data/articles.json` has the shape:

```json
{
  "id": "JID-001",
  "title": "...",
  "authors": ["...", "..."],
  "year": 2011,
  "volume": 38,
  "issue": 2,
  "journal": "...",
  "abstract": "...",
  "full_text": "..."
}
```

## Layout

```
.
├── index.html            # home page: lists all 15 articles with links
├── articles/
│   └── JID-0NN.html      # one readable HTML page per article (15 files)
├── data/
│   ├── JID-0NN.txt       # plain-text export (15 files)
│   ├── JID-0NN.pdf       # PDF export (15 files)
│   └── articles.json     # structured metadata for all 15 articles
├── articles_data.py      # source content for every article
├── build.py              # regenerates the site + /data exports
└── README.md
```

Build your RAG layer on top of any of these — scrape the HTML, parse the PDFs,
read the `.txt` files, or load `articles.json` directly.
