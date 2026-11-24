# CIFOR-ICRAF Grant Finder (Python Shiny)

A lightweight Python Shiny web application for discovering, filtering, and tracking live funding opportunities relevant to **CIFOR-ICRAF** — covering agroforestry, regenerative agriculture, biodiversity, land & forest restoration, soil health, climate finance, watersheds, and rural livelihoods.

## Live Grant Sources

| Source | Coverage | Integration |
| --- | --- | --- |
| **Grants.gov** | US Federal agencies (USAID, USDA, NSF, EPA, DOI, USFWS) | Official `search2` REST API |
| **EU Funding & Tenders (SEDIA)** | Horizon Europe, LIFE, NDICI-Global Europe open & forthcoming calls | Official EC SEDIA Search API |
| **UKRI Funding Finder** | UK Research & Innovation (NERC, BBSRC, FCDO international calls) | Official RSS + WordPress REST API |
| **Terra Viva Grants Directory** | Agriculture, forestry, biodiversity, water & climate in developing countries | WordPress REST API + RSS fallback |
| **FundsforNGOs** | International NGO & research grants (Agriculture, Environment, Climate) | Category RSS feeds |
| **Custom RSS / Atom Feeds** | Any additional donor or regional funding feed (GEF, CGIAR, ReliefWeb, etc.) | Configurable in-app |

## Features

- **CIFOR-ICRAF Thematic Tagging & Relevance Scoring (0–100):** Automatically tags opportunities across 8 core themes and ranks the best matches first.
- **Interactive Filtering:** Filter by keyword, theme, source, status (Open / Forthcoming / Closed), and minimum relevance score.
- **Shortlist & Proposal Tracker:** Bookmark promising calls, assign proposal stages (`Watching`, `Exploring`, `Drafting`, `Submitted`, `Archived`), and save internal team notes locally in `data/shortlist.json`.
- **CSV Export & Local Caching:** Export filtered results or your shortlist to CSV, with fast startup from `data/grants_cache.json`.

## Running the App

```bash
uv sync --python 3.12
uv run shiny run --reload app.py
```

Or directly via the virtual environment:

```bash
.venv/bin/shiny run --port 8000 app.py
```

Then open `http://127.0.0.1:8000` in your browser.
