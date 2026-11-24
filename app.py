"""CIFOR-ICRAF Grant Finder — Python Shiny Web Application."""

from __future__ import annotations

import csv
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import faicons as fa
import pandas as pd
from shiny import App, reactive, render, ui

from grant_finder.models import ALL_REGIONS, THEMES, Grant, SourceStatus
from grant_finder.scoring import score_and_tag_grant
from grant_finder.storage import (
    load_cache,
    load_custom_feeds,
    load_shortlist,
    save_cache,
    save_custom_feeds,
    save_shortlist,
)

IS_SHINYLIVE = sys.platform == "emscripten" or "pyodide" in sys.modules

if not IS_SHINYLIVE:
    from grant_finder.sources import BUILTIN_SOURCES, fetch_all_sources

    BUILTIN_SOURCE_NAMES = list(BUILTIN_SOURCES.keys())
else:
    fetch_all_sources = None
    BUILTIN_SOURCE_NAMES = [
        "Grants.gov",
        "EU Funding & Tenders",
        "UKRI Funding Finder",
        "Terra Viva Grants",
        "FundsforNGOs",
        "IKI (Intl Climate Initiative)",
        "IDRC (Canada)",
        "Darwin Initiative (UK)",
        "FFAR (Food & Ag Research)",
        "Gates Grand Challenges",
    ]

APP_DIR = Path(__file__).resolve().parent
ALL_THEMES = list(THEMES.keys())
SHORTLIST_STAGES = ["Watching", "Exploring", "Drafting", "Submitted", "Archived"]

EXTERNAL_PORTALS: list[dict[str, str]] = [
    {
        "name": "Devex Funding (Open & Forecast)",
        "url": "https://www.devex.com/funding/r?report=tender-924449&filter%5Bstatuses%5D%5B%5D=forecast&filter%5Bstatuses%5D%5B%5D=open&sorting%5Border%5D=desc&sorting%5Bfield%5D=updated_at",
        "note": "Requires browser session / Devex Funding login. Export to CSV and upload below to score & filter here.",
    },
    {
        "name": "CEPF — Open Calls for Proposals",
        "url": "https://www.cepf.net/grants/open-calls-for-proposals",
        "note": "Biodiversity hotspot small & large grants across Africa, Asia, and Latin America.",
    },
    {
        "name": "Bezos Earth Fund — News & Initiatives",
        "url": "https://www.bezosearthfund.org/news-and-insights",
        "note": "Mostly invitation-only; check here for occasional competitive Grand Challenges.",
    },
]


def _status_badge(status: str) -> ui.Tag:
    st = (status or "Open").strip()
    cls = {
        "Open": "badge-status-open",
        "Forthcoming": "badge-status-forthcoming",
        "Closed": "badge-status-closed",
    }.get(st, "badge-status-open")
    return ui.span(st, class_=cls)


def _theme_badges(themes: list[str]) -> list[ui.Tag]:
    tags: list[ui.Tag] = []
    for t in themes:
        color = THEMES.get(t, {}).get("color", "#2d6a4f")
        tags.append(
            ui.span(
                t,
                class_="badge-theme",
                style=f"background-color: {color};",
            )
        )
    return tags


# ---------------------------------------------------------------------------
# UI Definition
# ---------------------------------------------------------------------------
app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.div(
            ui.div(
                fa.icon_svg("calendar-check", margin_right="0.35rem"),
                "Auto-synced daily via GitHub Actions",
                class_="small text-center py-2 px-2 mb-1 rounded-3",
                style="background: rgba(94, 75, 139, 0.12); color: #3b2f63; font-weight: 600;",
            )
            if IS_SHINYLIVE
            else ui.input_action_button(
                "refresh_btn",
                "Refresh Live Feeds",
                icon=fa.icon_svg("arrows-rotate"),
                class_="btn-forest w-100 mb-2",
            ),
            ui.output_ui("last_updated_ui"),
            class_="mb-2",
        ),
        ui.hr(class_="my-2"),
        ui.div("Search & Relevance", class_="sidebar-section-title"),
        ui.input_text(
            "search_query",
            None,
            placeholder="Keyword (e.g., biochar, cocoa, Kenya...)",
        ),
        ui.input_slider(
            "min_score",
            "Minimum CIFOR-ICRAF Relevance",
            min=0,
            max=80,
            value=10,
            step=5,
        ),
        ui.input_select(
            "status_filter",
            "Opportunity Status",
            choices={
                "active": "Open & Forthcoming",
                "Open": "Open only",
                "Forthcoming": "Forthcoming only",
                "all": "All (including Closed)",
            },
            selected="active",
        ),
        ui.hr(class_="my-2"),
        ui.div("Continent & Country", class_="sidebar-section-title"),
        ui.input_selectize(
            "region_filter",
            "Continent / Region",
            choices=ALL_REGIONS,
            selected=[],
            multiple=True,
            options={"placeholder": "All continents / regions"},
        ),
        ui.output_ui("country_filter_ui"),
        ui.hr(class_="my-2"),
        ui.div("CIFOR-ICRAF Themes", class_="sidebar-section-title"),
        ui.div(
            ui.input_action_link("themes_all", "Select all"),
            " · ",
            ui.input_action_link("themes_none", "Clear"),
            class_="small mb-1",
        ),
        ui.input_checkbox_group(
            "theme_filter",
            None,
            choices=ALL_THEMES,
            selected=[],
        ),
        ui.hr(class_="my-2"),
        ui.div("Grant Sources", class_="sidebar-section-title"),
        ui.output_ui("source_filter_ui"),
        ui.hr(class_="my-2"),
        ui.download_button(
            "download_csv",
            "Export Filtered CSV",
            icon=fa.icon_svg("download"),
            class_="btn-outline-secondary btn-sm w-100",
        ),
        width=310,
        open="desktop",
    ),
    ui.include_css(APP_DIR / "styles.css"),
    # Header Banner
    ui.div(
        ui.div(
            ui.h1(
                fa.icon_svg("seedling", margin_right="0.45rem"),
                "CIFOR-ICRAF Grant Finder",
            ),
            ui.p(
                "Live funding opportunities across agroforestry, regenerative agriculture, "
                "biodiversity, land restoration, and soil health.",
                class_="subtitle",
            ),
        ),
        ui.output_ui("header_badge_ui"),
        class_="app-header",
    ),
    # KPI Value Boxes
    ui.layout_columns(
        ui.value_box(
            "Matching Grants",
            ui.output_text("kpi_matching"),
            showcase=fa.icon_svg("magnifying-glass"),
            theme="bg-white",
        ),
        ui.value_box(
            "Open & Forthcoming",
            ui.output_text("kpi_open"),
            showcase=fa.icon_svg("door-open"),
            theme="bg-white",
        ),
        ui.value_box(
            "Closing Within 30 Days",
            ui.output_text("kpi_soon"),
            showcase=fa.icon_svg("clock"),
            theme="bg-white",
        ),
        ui.value_box(
            "Shortlisted",
            ui.output_text("kpi_shortlisted"),
            showcase=fa.icon_svg("bookmark"),
            theme="bg-white",
        ),
        fill=False,
        class_="mb-3",
    ),
    # Main Tabbed Workspace
    ui.navset_card_underline(
        ui.nav_panel(
            "Explore Grants",
            ui.p(
                "Click any row in the table to inspect full details, open the official call, "
                "or save it to your team shortlist.",
                class_="text-muted small mb-2",
            ),
            ui.output_data_frame("grants_table"),
            ui.hr(class_="my-3"),
            ui.output_ui("grant_detail_panel"),
            icon=fa.icon_svg("compass"),
        ),
        ui.nav_panel(
            "Shortlist & Tracker",
            ui.div(
                ui.p(
                    "Track saved opportunities, proposal stages, and internal notes. "
                    "Saved locally in data/shortlist.json.",
                    class_="text-muted small mb-0",
                ),
                ui.download_button(
                    "download_shortlist_csv",
                    "Export Shortlist CSV",
                    icon=fa.icon_svg("file-csv"),
                    class_="btn-outline-secondary btn-sm",
                ),
                class_="d-flex justify-content-between align-items-center mb-3",
            ),
            ui.output_ui("shortlist_view"),
            icon=fa.icon_svg("bookmark"),
        ),
        ui.nav_panel(
            "Sources & Custom Feeds",
            ui.layout_columns(
                ui.div(
                    ui.h5("Connected Grant Portals", class_="mb-3"),
                    ui.output_ui("sources_status_ui"),
                ),
                ui.div(
                    ui.h5("External Portals (Manual / Login Required)", class_="mb-2"),
                    ui.p(
                        "Sites behind login or anti-bot gates that cannot be auto-fetched. "
                        "Open them directly in your browser:",
                        class_="text-muted small",
                    ),
                    *[
                        ui.div(
                            ui.div(
                                ui.strong(p["name"]),
                                ui.a(
                                    "Open Portal ↗",
                                    href=p["url"],
                                    target="_blank",
                                    rel="noopener noreferrer",
                                    class_="btn btn-forest btn-sm",
                                ),
                                class_="d-flex justify-content-between align-items-center mb-1",
                            ),
                            ui.div(p["note"], class_="small text-muted"),
                            class_="source-status-card",
                        )
                        for p in EXTERNAL_PORTALS
                    ],
                    ui.hr(),
                    ui.h5("Import Grants CSV (e.g., Devex Export)", class_="mb-2"),
                    ui.p(
                        "Upload a CSV exported from Devex Funding or another tracker to "
                        "automatically score, tag by theme/geography, and merge into Explore Grants.",
                        class_="text-muted small",
                    ),
                    ui.input_file(
                        "import_csv",
                        None,
                        accept=[".csv"],
                        button_label="Choose CSV file",
                        placeholder="No file selected",
                    ),
                    ui.hr(),
                    ui.h5("Add Custom RSS / Atom Feed", class_="mb-2"),
                    ui.p(
                        "Add any donor or regional funding RSS feed (e.g., GEF, CGIAR, "
                        "Darwin Initiative, ReliefWeb) to include it in live refreshes.",
                        class_="text-muted small",
                    ),
                    ui.input_text(
                        "custom_feed_name",
                        "Feed Name",
                        placeholder="e.g., GEF News & Funding",
                    ),
                    ui.input_text(
                        "custom_feed_url",
                        "RSS / Atom URL",
                        placeholder="https://example.org/grants/feed/",
                    ),
                    ui.input_action_button(
                        "add_feed_btn",
                        "Add Feed & Refresh",
                        icon=fa.icon_svg("plus"),
                        class_="btn-forest mb-3",
                    ),
                    ui.hr(),
                    ui.h6("Configured Custom Feeds"),
                    ui.output_ui("custom_feeds_list_ui"),
                ),
                col_widths=[7, 5],
            ),
            icon=fa.icon_svg("satellite-dish"),
        ),
        id="main_tabs",
    ),
    title="CIFOR-ICRAF Grant Finder",
    fillable=False,
)


# ---------------------------------------------------------------------------
# Server Logic
# ---------------------------------------------------------------------------
def server(input, output, session):
    cached_grants, cached_statuses, cached_updated = load_cache()

    grants_rv: reactive.Value[list[Grant]] = reactive.Value(cached_grants)
    statuses_rv: reactive.Value[list[SourceStatus]] = reactive.Value(cached_statuses)
    updated_at_rv: reactive.Value[str] = reactive.Value(cached_updated)
    shortlist_rv: reactive.Value[dict] = reactive.Value(load_shortlist())
    custom_feeds_rv: reactive.Value[list[dict[str, str]]] = reactive.Value(
        load_custom_feeds()
    )
    selected_grant_id_rv: reactive.Value[str | None] = reactive.Value(
        cached_grants[0].id if cached_grants else None
    )

    # Dynamic country selector populated from detected countries
    @render.ui
    def country_filter_ui():
        counts: dict[str, int] = {}
        for g in grants_rv():
            for c in g.countries:
                counts[c] = counts.get(c, 0) + 1
        choices = {c: f"{c} ({counts[c]})" for c in sorted(counts)}
        return ui.input_selectize(
            "country_filter",
            "Country",
            choices=choices,
            selected=[],
            multiple=True,
            options={"placeholder": "All countries"},
        )

    # Dynamic source checkboxes (built-in + custom feeds + any imported CSV sources)
    @render.ui
    def source_filter_ui():
        custom_names = [f["name"] for f in custom_feeds_rv()]
        extra_sources = sorted(
            {
                g.source
                for g in grants_rv()
                if g.source not in BUILTIN_SOURCE_NAMES and g.source not in custom_names
            }
        )
        all_sources = BUILTIN_SOURCE_NAMES + custom_names + extra_sources
        return ui.input_checkbox_group(
            "source_filter",
            None,
            choices=all_sources,
            selected=all_sources,
        )

    @render.ui
    def last_updated_ui():
        ts = updated_at_rv()
        if ts:
            return ui.div(
                f"Last synced: {ts}",
                class_="text-muted small text-center",
            )
        return ui.div(
            "No cached data yet — click Refresh.",
            class_="text-warning small text-center",
        )

    @render.ui
    def header_badge_ui():
        total = len(grants_rv())
        return ui.span(
            f"{total} opportunities indexed",
            class_="badge bg-light text-dark px-3 py-2",
            style="font-size: 0.82rem; font-weight: 600;",
        )

    # Select all / Clear themes
    @reactive.effect
    @reactive.event(input.themes_all)
    def _select_all_themes():
        ui.update_checkbox_group("theme_filter", selected=ALL_THEMES)

    @reactive.effect
    @reactive.event(input.themes_none)
    def _clear_themes():
        ui.update_checkbox_group("theme_filter", selected=[])

    # Live fetch coroutine triggered by Refresh button (or when adding custom feed)
    async def _run_refresh() -> None:
        if IS_SHINYLIVE or fetch_all_sources is None:
            ui.notification_show(
                "Live browser fetching is disabled on static GitHub Pages; data refreshes daily via GitHub Actions.",
                type="message",
                duration=4,
            )
            return
        with ui.Progress(min=0, max=1) as p:
            p.set(0.2, message="Fetching live grant portals & RSS feeds...")
            grants, statuses = await fetch_all_sources(
                selected_sources=None,
                custom_feeds=custom_feeds_rv(),
            )
            p.set(0.85, message="Scoring CIFOR-ICRAF thematic relevance...")
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            grants_rv.set(grants)
            statuses_rv.set(statuses)
            updated_at_rv.set(now_str)
            if grants:
                save_cache(grants, statuses)
                selected_grant_id_rv.set(grants[0].id)
            p.set(1.0, message="Done!")
        ok_count = sum(1 for s in statuses if s.ok)
        ui.notification_show(
            f"Refreshed {len(grants)} grants from {ok_count}/{len(statuses)} sources.",
            type="message" if ok_count > 0 else "warning",
            duration=4,
        )

    @reactive.effect
    @reactive.event(input.refresh_btn)
    async def _on_refresh():
        await _run_refresh()

    # Auto-fetch on first launch if no cache exists (local server only)
    @reactive.effect
    async def _initial_fetch_if_empty():
        if not grants_rv() and not IS_SHINYLIVE:
            await _run_refresh()

    # Filtered grants reactive calc
    @reactive.calc
    def filtered_grants() -> list[Grant]:
        grants = grants_rv()
        q = (input.search_query() or "").strip().lower()
        min_sc = input.min_score() or 0
        status_f = input.status_filter() or "active"
        selected_themes = set(input.theme_filter() or [])
        selected_sources = set(input.source_filter() or [])
        selected_regions = set(input.region_filter() or [])
        selected_countries = set(input.country_filter() or [])

        out: list[Grant] = []
        for g in grants:
            if selected_sources and g.source not in selected_sources:
                continue
            if g.relevance_score < min_sc:
                continue
            if status_f == "active" and g.status == "Closed":
                continue
            elif status_f in ("Open", "Forthcoming") and g.status != status_f:
                continue
            if selected_regions and not (selected_regions & set(g.regions)):
                continue
            if selected_countries and not (selected_countries & set(g.countries)):
                continue
            if selected_themes and not (selected_themes & set(g.themes)):
                continue
            if q:
                haystack = " ".join(
                    [
                        g.title,
                        g.description,
                        g.funder,
                        g.source,
                        g.geography,
                        " ".join(g.regions),
                        " ".join(g.countries),
                        " ".join(g.themes),
                        " ".join(g.matched_keywords),
                    ]
                ).lower()
                if q not in haystack:
                    continue
            out.append(g)
        return out

    # KPIs
    @render.text
    def kpi_matching():
        return str(len(filtered_grants()))

    @render.text
    def kpi_open():
        return str(
            sum(1 for g in filtered_grants() if g.status in ("Open", "Forthcoming"))
        )

    @render.text
    def kpi_soon():
        count = 0
        for g in filtered_grants():
            d = g.days_until_deadline()
            if d is not None and 0 <= d <= 30:
                count += 1
        return str(count)

    @render.text
    def kpi_shortlisted():
        return str(len(shortlist_rv()))

    # Main interactive DataGrid
    @render.data_frame
    def grants_table():
        fg = filtered_grants()
        sl = shortlist_rv()
        if not fg:
            df = pd.DataFrame(
                columns=[
                    "Saved",
                    "Score",
                    "Title",
                    "Source",
                    "Amount",
                    "Region / Country",
                    "Status",
                    "Deadline",
                    "Themes",
                ]
            )
            return render.DataGrid(df, width="100%", height="340px")

        rows = []
        for g in fg:
            days = g.days_until_deadline()
            if g.deadline and days is not None:
                dl_label = (
                    f"{g.deadline} ({days}d)" if days >= 0 else f"{g.deadline} (closed)"
                )
            else:
                dl_label = g.deadline or "See call"
            geo_parts = []
            if g.countries:
                geo_parts.append(", ".join(g.countries[:3]))
            if g.regions:
                geo_parts.append(", ".join(g.regions[:2]))
            geo_label = " · ".join(geo_parts) if geo_parts else (g.geography or "Global")
            rows.append(
                {
                    "Saved": "★" if g.id in sl else "",
                    "Score": g.relevance_score,
                    "Title": g.title,
                    "Source": g.source,
                    "Amount": g.amount or "—",
                    "Region / Country": geo_label,
                    "Status": g.status,
                    "Deadline": dl_label,
                    "Themes": ", ".join(g.themes[:3]) if g.themes else "General",
                }
            )
        df = pd.DataFrame(rows)
        return render.DataGrid(
            df,
            selection_mode="row",
            width="100%",
            height="380px",
            filters=False,
        )

    # Track selected row from DataGrid
    @reactive.effect
    def _sync_selected_row():
        sel = grants_table.cell_selection()
        rows = sel.get("rows") if sel else None
        fg = filtered_grants()
        if rows:
            idx = rows[0]
            if 0 <= idx < len(fg):
                selected_grant_id_rv.set(fg[idx].id)

    @reactive.calc
    def selected_grant() -> Grant | None:
        fg = filtered_grants()
        if not fg:
            return None
        gid = selected_grant_id_rv()
        for g in fg:
            if g.id == gid:
                return g
        return fg[0]

    # Detail panel for selected grant
    @render.ui
    def grant_detail_panel():
        g = selected_grant()
        if not g:
            return ui.div(
                "No grants match your current filters. Try lowering the minimum relevance score "
                "or clearing theme filters.",
                class_="alert alert-light border",
            )

        sl = shortlist_rv()
        is_saved = g.id in sl
        saved_entry = sl.get(g.id, {})
        current_stage = saved_entry.get("stage", "Watching")
        current_notes = saved_entry.get("notes", "")

        days = g.days_until_deadline()
        deadline_display = g.deadline or "Not listed (check call page)"
        if days is not None:
            if days < 0:
                deadline_display += f" · Expired {abs(days)} days ago"
            elif days == 0:
                deadline_display += " · Due today!"
            else:
                deadline_display += f" · {days} days left"

        return ui.div(
            ui.div(
                ui.div(
                    ui.span(f"Relevance {g.relevance_score}/100", class_="score-pill me-2"),
                    _status_badge(g.status),
                    ui.span(
                        g.source,
                        class_="badge bg-secondary ms-2",
                        style="font-size: 0.76rem;",
                    ),
                ),
                ui.div(
                    ui.a(
                        fa.icon_svg("arrow-up-right-from-square", margin_right="0.35rem"),
                        "Open Official Call",
                        href=g.url,
                        target="_blank",
                        rel="noopener noreferrer",
                        class_="btn btn-forest btn-sm me-2",
                    ),
                    ui.input_action_button(
                        "toggle_shortlist_btn",
                        "Remove from Shortlist" if is_saved else "Save to Shortlist",
                        icon=fa.icon_svg("bookmark"),
                        class_="btn-outline-danger btn-sm"
                        if is_saved
                        else "btn-outline-success btn-sm",
                    ),
                ),
                class_="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2",
            ),
            ui.h4(g.title, class_="mb-2", style="color: #3b2f63; font-weight: 700;"),
            ui.div(*_theme_badges(g.themes), class_="mb-2") if g.themes else None,
            ui.div(
                ui.div(
                    ui.div("Funder / Agency", class_="detail-meta-label"),
                    ui.div(g.funder or "N/A"),
                ),
                ui.div(
                    ui.div("Funding / Call Amount", class_="detail-meta-label"),
                    ui.div(g.amount or "Not specified (see call)"),
                ),
                ui.div(
                    ui.div("Deadline", class_="detail-meta-label"),
                    ui.div(deadline_display),
                ),
                ui.div(
                    ui.div("Continent / Region", class_="detail-meta-label"),
                    ui.div(", ".join(g.regions) if g.regions else (g.geography or "See call")),
                ),
                ui.div(
                    ui.div("Detected Countries", class_="detail-meta-label"),
                    ui.div(", ".join(g.countries) if g.countries else "Regional / Multi-country"),
                ),
                ui.div(
                    ui.div("Published / ID", class_="detail-meta-label"),
                    ui.div(
                        " · ".join(
                            p for p in [g.published, g.opportunity_number] if p
                        )
                        or "N/A"
                    ),
                ),
                class_="detail-meta-grid",
            ),
            ui.p(
                g.description or "No summary provided by feed. Open the official call for details.",
                class_="mb-2",
                style="line-height: 1.55;",
            ),
            ui.div(
                ui.span("Matched keywords: ", class_="small text-muted me-1"),
                *[ui.span(kw, class_="badge-keyword") for kw in g.matched_keywords],
                class_="mb-3",
            )
            if g.matched_keywords
            else None,
            # Inline team tracking controls when saved
            ui.div(
                ui.hr(class_="my-2"),
                ui.h6("Shortlist Tracking & Team Notes", class_="mb-2"),
                ui.layout_columns(
                    ui.input_select(
                        "detail_stage",
                        "Proposal Stage",
                        choices=SHORTLIST_STAGES,
                        selected=current_stage,
                    ),
                    ui.input_text_area(
                        "detail_notes",
                        "Internal Notes (e.g., lead scientist, partners, consortium fit)",
                        value=current_notes,
                        rows=2,
                    ),
                    col_widths=[4, 8],
                ),
                ui.input_action_button(
                    "save_notes_btn",
                    "Save Stage & Notes",
                    icon=fa.icon_svg("floppy-disk"),
                    class_="btn-forest btn-sm",
                ),
                class_="mt-2",
            )
            if is_saved
            else None,
            class_="detail-panel",
        )

    @reactive.effect
    @reactive.event(input.toggle_shortlist_btn)
    def _toggle_shortlist():
        g = selected_grant()
        if not g:
            return
        sl = dict(shortlist_rv())
        if g.id in sl:
            del sl[g.id]
            ui.notification_show("Removed from shortlist.", type="message", duration=2)
        else:
            sl[g.id] = {
                "grant": g.to_dict(),
                "stage": "Watching",
                "notes": "",
                "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }
            ui.notification_show("Saved to shortlist!", type="message", duration=2)
        save_shortlist(sl)
        shortlist_rv.set(sl)

    @reactive.effect
    @reactive.event(input.save_notes_btn)
    def _save_notes():
        g = selected_grant()
        if not g:
            return
        sl = dict(shortlist_rv())
        if g.id in sl:
            sl[g.id]["stage"] = input.detail_stage() or "Watching"
            sl[g.id]["notes"] = (input.detail_notes() or "").strip()
            save_shortlist(sl)
            shortlist_rv.set(sl)
            ui.notification_show("Updated shortlist stage & notes.", type="message", duration=2)

    # Shortlist tab UI
    @render.ui
    def shortlist_view():
        sl = shortlist_rv()
        if not sl:
            return ui.div(
                "No shortlisted grants yet. Select any opportunity in the Explore Grants tab "
                "and click 'Save to Shortlist'.",
                class_="alert alert-light border",
            )
        cards = []
        for gid, entry in sl.items():
            g = Grant.from_dict(entry["grant"])
            stage = entry.get("stage", "Watching")
            notes = entry.get("notes", "")
            saved_at = entry.get("saved_at", "")
            cards.append(
                ui.div(
                    ui.div(
                        ui.div(
                            ui.span(stage, class_="badge bg-success me-2"),
                            ui.span(f"Score {g.relevance_score}", class_="score-pill me-2"),
                            ui.span(g.source, class_="badge bg-secondary"),
                        ),
                        ui.div(
                            ui.a(
                                "Open Call ↗",
                                href=g.url,
                                target="_blank",
                                rel="noopener noreferrer",
                                class_="btn btn-forest btn-sm me-2",
                            ),
                            ui.span(
                                f"Saved {saved_at}",
                                class_="text-muted small",
                            ),
                        ),
                        class_="d-flex justify-content-between align-items-center mb-1",
                    ),
                    ui.h6(g.title, class_="mb-1", style="color: #3b2f63; font-weight: 700;"),
                    ui.div(
                        f"Funder: {g.funder} · Amount: {g.amount or 'See call'} · Deadline: {g.deadline or 'See call'} · Status: {g.status}",
                        class_="small text-muted mb-1",
                    ),
                    ui.div(*_theme_badges(g.themes), class_="mb-1") if g.themes else None,
                    ui.p(
                        f"Notes: {notes}" if notes else "No notes added yet.",
                        class_="small mb-0 fst-italic text-secondary",
                    ),
                    class_="source-status-card",
                )
            )
        return ui.div(*cards)

    # Sources status tab UI
    @render.ui
    def sources_status_ui():
        statuses = statuses_rv()
        if not statuses:
            return ui.div(
                "No source telemetry yet. Click 'Refresh Live Feeds' to fetch.",
                class_="alert alert-light border",
            )
        cards = []
        for st in statuses:
            badge = (
                ui.span("Connected", class_="badge-status-open")
                if st.ok
                else ui.span("Unavailable", class_="badge-status-closed")
            )
            cards.append(
                ui.div(
                    ui.div(
                        ui.strong(st.name),
                        badge,
                        class_="d-flex justify-content-between align-items-center mb-1",
                    ),
                    ui.div(
                        f"{st.count} items · Last checked: {st.fetched_at}",
                        class_="small text-muted",
                    ),
                    ui.div(st.message, class_="small mt-1"),
                    ui.a(
                        st.url,
                        href=st.url,
                        target="_blank",
                        rel="noopener noreferrer",
                        class_="small",
                    )
                    if st.url
                    else None,
                    class_="source-status-card",
                )
            )
        return ui.div(*cards)

    # Custom RSS feeds management
    @render.ui
    def custom_feeds_list_ui():
        feeds = custom_feeds_rv()
        if not feeds:
            return ui.p("No custom feeds configured yet.", class_="text-muted small")
        items = []
        for idx, f in enumerate(feeds):
            items.append(
                ui.div(
                    ui.div(
                        ui.strong(f["name"]),
                        ui.div(f["url"], class_="small text-muted text-break"),
                    ),
                    class_="source-status-card",
                )
            )
        return ui.div(
            *items,
            ui.input_action_button(
                "clear_custom_feeds_btn",
                "Clear Custom Feeds",
                class_="btn-outline-danger btn-sm mt-1",
            ),
        )

    @reactive.effect
    @reactive.event(input.add_feed_btn)
    async def _add_custom_feed():
        name = (input.custom_feed_name() or "").strip()
        url = (input.custom_feed_url() or "").strip()
        if not name or not url.startswith(("http://", "https://")):
            ui.notification_show(
                "Please enter both a feed name and a valid http(s) RSS/Atom URL.",
                type="warning",
                duration=4,
            )
            return
        feeds = list(custom_feeds_rv())
        feeds.append({"name": name, "url": url})
        save_custom_feeds(feeds)
        custom_feeds_rv.set(feeds)
        ui.update_text("custom_feed_name", value="")
        ui.update_text("custom_feed_url", value="")
        await _run_refresh()

    @reactive.effect
    @reactive.event(input.clear_custom_feeds_btn)
    def _clear_custom_feeds():
        save_custom_feeds([])
        custom_feeds_rv.set([])
        ui.notification_show("Cleared custom feeds.", type="message", duration=2)

    # Import CSV (e.g., Devex Funding export or custom spreadsheet)
    @reactive.effect
    @reactive.event(input.import_csv)
    def _on_import_csv():
        files = input.import_csv()
        if not files:
            return
        file_info = files[0]
        datapath = file_info.get("datapath")
        filename = file_info.get("name", "Imported CSV")
        if not datapath:
            return

        try:
            df = pd.read_csv(datapath, dtype=str).fillna("")
        except Exception as exc:
            ui.notification_show(f"Could not read CSV: {exc}", type="error", duration=5)
            return

        if df.empty:
            ui.notification_show("Uploaded CSV has no rows.", type="warning", duration=4)
            return

        cols_lower = {c.strip().lower(): c for c in df.columns}

        def _pick(row, candidates: list[str]) -> str:
            for cand in candidates:
                for low_col, orig_col in cols_lower.items():
                    if cand == low_col or cand in low_col:
                        val = str(row.get(orig_col, "")).strip()
                        if val:
                            return val
            return ""

        source_label = (
            "Devex (Imported CSV)"
            if "devex" in filename.lower()
            else f"CSV Import ({Path(filename).stem[:24]})"
        )
        imported: list[Grant] = []
        for idx, row in df.iterrows():
            title = _pick(row, ["title", "name", "opportunity", "tender", "call"])
            if not title:
                continue
            funder = _pick(row, ["funder", "donor", "organization", "agency", "client"])
            status_raw = _pick(row, ["status", "stage"])
            low_st = status_raw.lower()
            if "forecast" in low_st or "forthcoming" in low_st:
                status = "Forthcoming"
            elif "closed" in low_st or "expired" in low_st:
                status = "Closed"
            else:
                status = "Open"
            deadline = _pick(row, ["deadline", "closing", "due date", "submission"])
            amount = _pick(row, ["amount", "budget", "value", "size", "funding"])
            geo = _pick(row, ["country", "countries", "location", "region", "geography"])
            url = _pick(row, ["url", "link", "website"]) or EXTERNAL_PORTALS[0]["url"]
            desc = _pick(row, ["description", "summary", "details", "sector", "notes"])
            if geo and geo.lower() not in desc.lower():
                desc = f"{desc} Location: {geo}.".strip()

            g = Grant(
                id=f"csv-{idx}-{abs(hash(title + url)) % 10**8}",
                title=title,
                source=source_label,
                funder=funder or source_label,
                url=url,
                status=status,
                deadline=deadline[:20],
                amount=amount,
                geography=geo or "See opportunity details",
                description=desc or title,
            )
            imported.append(score_and_tag_grant(g))

        if not imported:
            ui.notification_show(
                "No grants found — ensure the CSV has a 'Title' or 'Name' column.",
                type="warning",
                duration=5,
            )
            return

        existing = [g for g in grants_rv() if g.source != source_label]
        merged = existing + imported
        merged.sort(key=lambda g: (-g.relevance_score, g.deadline or "9999-99-99"))
        grants_rv.set(merged)

        st_list = [s for s in statuses_rv() if s.name != source_label]
        st_list.append(
            SourceStatus(
                name=source_label,
                ok=True,
                count=len(imported),
                fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                message=f"Imported {len(imported)} rows from {filename}.",
            )
        )
        statuses_rv.set(st_list)
        ui.notification_show(
            f"Imported {len(imported)} grants from {filename}!",
            type="message",
            duration=4,
        )

    # CSV Exports
    @render.download(filename="cifor_icraf_grants.csv")
    def download_csv():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "Relevance Score",
                "Title",
                "Source",
                "Funder",
                "Status",
                "Amount",
                "Deadline",
                "Published",
                "Regions",
                "Countries",
                "Geography",
                "Themes",
                "Keywords",
                "URL",
                "Description",
            ]
        )
        for g in filtered_grants():
            writer.writerow(
                [
                    g.relevance_score,
                    g.title,
                    g.source,
                    g.funder,
                    g.status,
                    g.amount,
                    g.deadline,
                    g.published,
                    "; ".join(g.regions),
                    "; ".join(g.countries),
                    g.geography,
                    "; ".join(g.themes),
                    "; ".join(g.matched_keywords),
                    g.url,
                    g.description,
                ]
            )
        yield buf.getvalue()

    @render.download(filename="cifor_icraf_shortlist.csv")
    def download_shortlist_csv():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "Stage",
                "Notes",
                "Saved Date",
                "Relevance Score",
                "Title",
                "Source",
                "Funder",
                "Amount",
                "Deadline",
                "Themes",
                "URL",
            ]
        )
        for entry in shortlist_rv().values():
            g = Grant.from_dict(entry["grant"])
            writer.writerow(
                [
                    entry.get("stage", "Watching"),
                    entry.get("notes", ""),
                    entry.get("saved_at", ""),
                    g.relevance_score,
                    g.title,
                    g.source,
                    g.funder,
                    g.amount,
                    g.deadline,
                    "; ".join(g.themes),
                    g.url,
                ]
            )
        yield buf.getvalue()


app = App(app_ui, server)
