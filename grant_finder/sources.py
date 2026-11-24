"""Async grant source connectors for CIFOR-ICRAF Grant Finder."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from grant_finder.models import Grant, SourceStatus
from grant_finder.scoring import score_and_tag_grant

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 "
    "CIFOR-ICRAF-GrantFinder/1.0"
)

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _clean_html(raw: str, max_len: int = 1200) -> str:
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def _normalize_date(val: Any) -> str:
    if not val:
        return ""
    if isinstance(val, (int, float)):
        # Handle epoch milliseconds or seconds
        ts = val / 1000.0 if val > 1e11 else float(val)
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return ""
    s = str(val).strip()
    if not s:
        return ""
    try:
        dt = date_parser.parse(s, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return s[:20]


def _extract_deadline_from_text(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r"(?:deadline|closing date|closes|due date|apply by|submission deadline)\s*[:\-]?\s*([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2})",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return _normalize_date(m.group(1))
    return ""


def _format_currency_num(val: Any, symbol: str = "$") -> str:
    try:
        n = float(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return ""
    if n <= 0:
        return ""
    if n >= 1_000_000_000:
        return f"{symbol}{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{symbol}{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{symbol}{n:,.0f}"
    return f"{symbol}{n:.0f}"


def _extract_eu_budget(meta: dict[str, Any]) -> str:
    """Parse structured EUR budget from EU SEDIA budgetOverview metadata if present."""
    raw_list = meta.get("budgetOverview") or []
    if not raw_list:
        return ""
    try:
        obj = json.loads(raw_list[0]) if isinstance(raw_list[0], str) else raw_list[0]
        topic_map = obj.get("budgetTopicActionMap") or {}
        totals: list[float] = []
        for actions in topic_map.values():
            for act in actions or []:
                year_map = act.get("budgetYearMap") or {}
                for amt in year_map.values():
                    try:
                        val = float(amt)
                        if val > 0:
                            totals.append(val)
                    except (ValueError, TypeError):
                        pass
        if totals:
            total = sum(totals)
            return _format_currency_num(total, "€")
    except Exception:
        pass
    return ""


def _make_id(source: str, raw_id: str) -> str:
    digest = hashlib.sha1(f"{source}:{raw_id}".encode("utf-8")).hexdigest()[:12]
    prefix = re.sub(r"[^a-z0-9]+", "", source.lower())[:8]
    return f"{prefix}-{digest}"


# ---------------------------------------------------------------------------
# 1. Grants.gov (US Federal: USAID, USDA, NSF, EPA, USFWS, DOI, etc.)
# ---------------------------------------------------------------------------
async def fetch_grants_gov(
    client: httpx.AsyncClient,
    keywords: list[str] | None = None,
    rows_per_query: int = 20,
) -> tuple[list[Grant], SourceStatus]:
    url = "https://api.grants.gov/v1/api/search2"
    queries = keywords or [
        "agroforestry",
        "biodiversity",
        "land restoration",
        "soil health",
        "forestry",
        "regenerative agriculture",
        "watershed",
    ]
    seen: dict[str, Grant] = {}
    errors: list[str] = []

    async def _query_one(kw: str) -> None:
        payload = {
            "keyword": kw,
            "rows": rows_per_query,
            "oppStatuses": "forecasted|posted",
        }
        try:
            resp = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            resp.raise_for_status()
            body = resp.json()
            hits = body.get("data", {}).get("oppHits", []) or []
            for h in hits:
                opp_id = str(h.get("id", "")).strip()
                if not opp_id or opp_id in seen:
                    continue
                status_raw = str(h.get("oppStatus", "posted")).lower()
                status = "Forthcoming" if status_raw == "forecasted" else "Open"
                title = (h.get("title") or "").strip()
                agency = (h.get("agencyName") or h.get("agencyCode") or "US Federal Agency").strip()
                opp_num = (h.get("number") or "").strip()
                open_dt = _normalize_date(h.get("openDate"))
                close_dt = _normalize_date(h.get("closeDate"))
                alns = h.get("alnist") or []
                aln_str = f"ALN: {', '.join(alns)}" if alns else ""
                desc_parts = [
                    f"Agency: {agency}.",
                    f"Opportunity Number: {opp_num}." if opp_num else "",
                    f"Matched search query: {kw}.",
                    aln_str,
                ]
                ceiling = _format_currency_num(h.get("awardCeiling"), "$")
                floor = _format_currency_num(h.get("awardFloor"), "$")
                total_fund = _format_currency_num(h.get("estimatedTotalProgramFunding"), "$")
                if floor and ceiling:
                    amount_str = f"{floor} – {ceiling}"
                elif ceiling:
                    amount_str = f"Up to {ceiling}"
                elif total_fund:
                    amount_str = f"{total_fund} total"
                else:
                    amount_str = ""

                g = Grant(
                    id=_make_id("grantsgov", opp_id),
                    title=title,
                    source="Grants.gov",
                    funder=agency,
                    url=f"https://www.grants.gov/search-results-detail/{opp_id}",
                    status=status,
                    deadline=close_dt,
                    published=open_dt,
                    amount=amount_str,
                    geography="US / International (check eligibility)",
                    description=" ".join(p for p in desc_parts if p),
                    opportunity_number=opp_num,
                )
                seen[opp_id] = score_and_tag_grant(g)
        except Exception as exc:
            errors.append(f"{kw}: {exc}")

    await asyncio.gather(*(_query_one(kw) for kw in queries))
    grants = list(seen.values())
    ok = len(grants) > 0 or not errors
    msg = (
        f"Fetched {len(grants)} opportunities across {len(queries)} queries."
        if ok
        else f"Errors: {'; '.join(errors[:2])}"
    )
    return grants, SourceStatus(
        name="Grants.gov",
        ok=ok,
        count=len(grants),
        fetched_at=_now_iso(),
        message=msg,
        url="https://www.grants.gov",
    )


# ---------------------------------------------------------------------------
# 2. EU Funding & Tenders Portal (SEDIA API — Horizon Europe, LIFE, Global Europe)
# ---------------------------------------------------------------------------
async def fetch_eu_sedia(
    client: httpx.AsyncClient,
    keywords: list[str] | None = None,
    page_size: int = 20,
) -> tuple[list[Grant], SourceStatus]:
    url = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
    queries = keywords or [
        "agroforestry",
        "biodiversity",
        "soil health",
        "land restoration",
        "forestry",
        "regenerative agriculture",
    ]
    seen: dict[str, Grant] = {}
    errors: list[str] = []

    query_filter = {
        "bool": {
            "must": [
                {"terms": {"type": ["1", "2", "8"]}},
                # 31094501 = Forthcoming, 31094502 = Open for submission
                {"terms": {"status": ["31094501", "31094502"]}},
            ]
        }
    }
    languages = ["en"]
    sort_obj = {"field": "sortStatus", "order": "ASC"}

    async def _query_one(kw: str) -> None:
        params = {
            "apiKey": "SEDIA",
            "text": kw,
            "pageSize": str(page_size),
            "pageNumber": "1",
        }
        files = {
            "query": ("blob", json.dumps(query_filter), "application/json"),
            "languages": ("blob", json.dumps(languages), "application/json"),
            "sort": ("blob", json.dumps(sort_obj), "application/json"),
        }
        try:
            resp = await client.post(url, params=params, files=files)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") or []
            for item in results:
                meta = item.get("metadata") or {}
                ident = (
                    (meta.get("identifier") or [None])[0]
                    or item.get("reference")
                    or item.get("url")
                )
                if not ident or ident in seen:
                    continue

                title_list = meta.get("title") or []
                title = (
                    title_list[0]
                    if title_list
                    else item.get("summary") or ident
                )
                title = _clean_html(str(title), max_len=240)

                deadlines = meta.get("deadlineDate") or []
                norm_deadlines = sorted(
                    d for d in (_normalize_date(x) for x in deadlines) if d
                )
                deadline = norm_deadlines[-1] if norm_deadlines else ""
                start_dates = meta.get("startDate") or []
                published = _normalize_date(start_dates[0]) if start_dates else ""

                status_codes = [str(c) for c in (meta.get("status") or [])]
                if "31094503" in status_codes:
                    status = "Closed"
                elif "31094502" in status_codes:
                    status = "Open"
                elif "31094501" in status_codes:
                    status = "Forthcoming"
                else:
                    status = "Open"

                prog_list = meta.get("frameworkProgramme") or meta.get("programmeDivision") or []
                call_title = (meta.get("callTitle") or [""])[0]
                funder = "European Commission"
                if call_title:
                    funder = f"EC — {_clean_html(str(call_title), 80)}"
                elif prog_list:
                    funder = f"EC ({prog_list[0]})"

                desc_raw = (
                    (meta.get("descriptionByte") or [None])[0]
                    or item.get("content")
                    or item.get("summary")
                    or ""
                )
                desc = _clean_html(str(desc_raw), max_len=1200)
                if not desc:
                    desc = f"EU Funding & Tenders opportunity ({ident}). Matched query: {kw}."

                topic_url = (
                    f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/"
                    f"opportunities/topic-details/{str(ident).lower()}"
                )

                eu_budget = _extract_eu_budget(meta)

                g = Grant(
                    id=_make_id("eusedia", str(ident)),
                    title=title,
                    source="EU Funding & Tenders",
                    funder=funder,
                    url=topic_url,
                    status=status,
                    deadline=deadline,
                    published=published,
                    amount=eu_budget,
                    geography="EU / Horizon Europe & International Partners",
                    description=desc,
                    opportunity_number=str(ident),
                )
                seen[str(ident)] = score_and_tag_grant(g)
        except Exception as exc:
            errors.append(f"{kw}: {exc}")

    # Run sequentially with tiny pause or small concurrency to be polite to EC API
    sem = asyncio.Semaphore(3)

    async def _bounded(kw: str) -> None:
        async with sem:
            await _query_one(kw)

    await asyncio.gather(*(_bounded(kw) for kw in queries))
    grants = list(seen.values())
    ok = len(grants) > 0 or not errors
    msg = (
        f"Fetched {len(grants)} open/forthcoming EU calls."
        if ok
        else f"Errors: {'; '.join(errors[:2])}"
    )
    return grants, SourceStatus(
        name="EU Funding & Tenders",
        ok=ok,
        count=len(grants),
        fetched_at=_now_iso(),
        message=msg,
        url="https://ec.europa.eu/info/funding-tenders/opportunities/portal/",
    )


# ---------------------------------------------------------------------------
# 3. UKRI Funding Finder (NERC, BBSRC, FCDO, International Research)
# ---------------------------------------------------------------------------
async def fetch_ukri(client: httpx.AsyncClient) -> tuple[list[Grant], SourceStatus]:
    rss_url = "https://www.ukri.org/opportunity/feed/"
    wp_url = "https://www.ukri.org/wp-json/wp/v2/opportunity?per_page=50"
    grants: list[Grant] = []
    seen_urls: set[str] = set()
    err_msgs: list[str] = []

    # Try RSS feed first
    try:
        resp = await client.get(rss_url, follow_redirects=True)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)
        for entry in parsed.entries:
            link = entry.get("link", "").strip()
            if not link or link in seen_urls:
                continue
            seen_urls.add(link)
            title = _clean_html(entry.get("title", ""), 240)
            summary = _clean_html(
                entry.get("summary") or entry.get("description") or "", 1200
            )
            published = _normalize_date(entry.get("published") or entry.get("updated"))
            deadline = _extract_deadline_from_text(summary)
            g = Grant(
                id=_make_id("ukri", link),
                title=title,
                source="UKRI Funding Finder",
                funder="UK Research and Innovation (UKRI)",
                url=link,
                status="Open",
                deadline=deadline,
                published=published,
                geography="UK / International Collaborations",
                description=summary,
            )
            grants.append(score_and_tag_grant(g))
    except Exception as exc:
        err_msgs.append(f"RSS: {exc}")

    # Fallback / supplement with WP REST API if RSS returned few results
    if len(grants) < 10:
        try:
            resp = await client.get(wp_url, follow_redirects=True)
            resp.raise_for_status()
            posts = resp.json()
            if isinstance(posts, list):
                for p in posts:
                    link = (p.get("link") or "").strip()
                    if not link or link in seen_urls:
                        continue
                    seen_urls.add(link)
                    title = _clean_html((p.get("title") or {}).get("rendered", ""), 240)
                    excerpt = _clean_html((p.get("excerpt") or {}).get("rendered", ""), 1200)
                    published = _normalize_date(p.get("date"))
                    deadline = _extract_deadline_from_text(excerpt)
                    g = Grant(
                        id=_make_id("ukri", link),
                        title=title,
                        source="UKRI Funding Finder",
                        funder="UK Research and Innovation (UKRI)",
                        url=link,
                        status="Open",
                        deadline=deadline,
                        published=published,
                        geography="UK / International Collaborations",
                        description=excerpt,
                    )
                    grants.append(score_and_tag_grant(g))
        except Exception as exc:
            err_msgs.append(f"WP API: {exc}")

    ok = len(grants) > 0
    msg = (
        f"Fetched {len(grants)} UKRI opportunities."
        if ok
        else f"Unable to fetch UKRI ({'; '.join(err_msgs)})"
    )
    return grants, SourceStatus(
        name="UKRI Funding Finder",
        ok=ok,
        count=len(grants),
        fetched_at=_now_iso(),
        message=msg,
        url="https://www.ukri.org/opportunity/",
    )


# ---------------------------------------------------------------------------
# 4. Terra Viva Grants Directory (Agriculture, Forestry, Biodiversity, Climate)
# ---------------------------------------------------------------------------
async def fetch_terra_viva(client: httpx.AsyncClient) -> tuple[list[Grant], SourceStatus]:
    endpoints = [
        ("wp", "https://www.terravivagrants.org/wp-json/wp/v2/posts?per_page=40"),
        ("rss", "https://www.terravivagrants.org/feed/"),
    ]
    grants: list[Grant] = []
    seen_urls: set[str] = set()
    err_msgs: list[str] = []

    for kind, ep in endpoints:
        if grants:
            break
        try:
            resp = await client.get(ep, follow_redirects=True)
            resp.raise_for_status()
            if kind == "wp":
                posts = resp.json()
                if not isinstance(posts, list):
                    continue
                for p in posts:
                    link = (p.get("link") or "").strip()
                    if not link or link in seen_urls:
                        continue
                    seen_urls.add(link)
                    title = _clean_html((p.get("title") or {}).get("rendered", ""), 240)
                    body_html = (p.get("excerpt") or {}).get("rendered") or (
                        p.get("content") or {}
                    ).get("rendered", "")
                    desc = _clean_html(body_html, 1200)
                    published = _normalize_date(p.get("date"))
                    deadline = _extract_deadline_from_text(desc)
                    g = Grant(
                        id=_make_id("terraviva", link),
                        title=title,
                        source="Terra Viva Grants",
                        funder="Various (via Terra Viva Grants)",
                        url=link,
                        status="Open",
                        deadline=deadline,
                        published=published,
                        geography="Developing Countries / Global South",
                        description=desc,
                    )
                    grants.append(score_and_tag_grant(g))
            else:
                parsed = feedparser.parse(resp.text)
                for entry in parsed.entries:
                    link = entry.get("link", "").strip()
                    if not link or link in seen_urls:
                        continue
                    seen_urls.add(link)
                    title = _clean_html(entry.get("title", ""), 240)
                    desc = _clean_html(
                        entry.get("summary") or entry.get("description") or "", 1200
                    )
                    published = _normalize_date(entry.get("published") or entry.get("updated"))
                    deadline = _extract_deadline_from_text(desc)
                    g = Grant(
                        id=_make_id("terraviva", link),
                        title=title,
                        source="Terra Viva Grants",
                        funder="Various (via Terra Viva Grants)",
                        url=link,
                        status="Open",
                        deadline=deadline,
                        published=published,
                        geography="Developing Countries / Global South",
                        description=desc,
                    )
                    grants.append(score_and_tag_grant(g))
        except Exception as exc:
            err_msgs.append(f"{kind}: {exc}")

    ok = len(grants) > 0
    msg = (
        f"Fetched {len(grants)} grants from Terra Viva."
        if ok
        else f"Unavailable ({'; '.join(err_msgs[:2])})"
    )
    return grants, SourceStatus(
        name="Terra Viva Grants",
        ok=ok,
        count=len(grants),
        fetched_at=_now_iso(),
        message=msg,
        url="https://www.terravivagrants.org",
    )


# ---------------------------------------------------------------------------
# 5. FundsforNGOs (Agriculture, Environment, Climate Change RSS Feeds)
# ---------------------------------------------------------------------------
async def fetch_funds_for_ngos(client: httpx.AsyncClient) -> tuple[list[Grant], SourceStatus]:
    feeds = [
        "https://www2.fundsforngos.org/category/agriculture-food-and-nutrition/feed/",
        "https://www2.fundsforngos.org/category/environment/feed/",
        "https://www2.fundsforngos.org/category/climate-change/feed/",
        "https://www2.fundsforngos.org/feed/",
    ]
    grants: list[Grant] = []
    seen_urls: set[str] = set()
    errors: list[str] = []

    async def _fetch_feed(feed_url: str) -> None:
        try:
            resp = await client.get(feed_url, follow_redirects=True)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.text)
            for entry in parsed.entries:
                link = entry.get("link", "").strip()
                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)
                title = _clean_html(entry.get("title", ""), 240)
                desc = _clean_html(
                    entry.get("summary") or entry.get("description") or "", 1200
                )
                published = _normalize_date(entry.get("published") or entry.get("updated"))
                deadline = _extract_deadline_from_text(desc)
                g = Grant(
                    id=_make_id("fundsforngos", link),
                    title=title,
                    source="FundsforNGOs",
                    funder="Various (via FundsforNGOs)",
                    url=link,
                    status="Open",
                    deadline=deadline,
                    published=published,
                    geography="International / NGOs & Research",
                    description=desc,
                )
                grants.append(score_and_tag_grant(g))
        except Exception as exc:
            errors.append(f"{feed_url.split('/')[-3]}: {exc}")

    await asyncio.gather(*(_fetch_feed(u) for u in feeds))
    ok = len(grants) > 0
    msg = (
        f"Fetched {len(grants)} grants across FundsforNGOs feeds."
        if ok
        else f"Unavailable ({'; '.join(errors[:2])})"
    )
    return grants, SourceStatus(
        name="FundsforNGOs",
        ok=ok,
        count=len(grants),
        fetched_at=_now_iso(),
        message=msg,
        url="https://www2.fundsforngos.org",
    )


# ---------------------------------------------------------------------------
# 6. Custom RSS / Atom feeds (user-configurable)
# ---------------------------------------------------------------------------
async def fetch_custom_rss(
    client: httpx.AsyncClient, name: str, feed_url: str
) -> tuple[list[Grant], SourceStatus]:
    grants: list[Grant] = []
    try:
        resp = await client.get(feed_url, follow_redirects=True)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)
        for entry in parsed.entries:
            link = entry.get("link", "").strip() or feed_url
            title = _clean_html(entry.get("title", "Untitled Opportunity"), 240)
            desc = _clean_html(
                entry.get("summary") or entry.get("description") or "", 1200
            )
            published = _normalize_date(entry.get("published") or entry.get("updated"))
            deadline = _extract_deadline_from_text(desc)
            g = Grant(
                id=_make_id(f"rss-{name}", f"{link}-{title}"),
                title=title,
                source=name,
                funder=name,
                url=link,
                status="Open",
                deadline=deadline,
                published=published,
                geography="See opportunity details",
                description=desc,
            )
            grants.append(score_and_tag_grant(g))
        return grants, SourceStatus(
            name=name,
            ok=True,
            count=len(grants),
            fetched_at=_now_iso(),
            message=f"Fetched {len(grants)} items from custom RSS feed.",
            url=feed_url,
        )
    except Exception as exc:
        return [], SourceStatus(
            name=name,
            ok=False,
            count=0,
            fetched_at=_now_iso(),
            message=f"Failed: {exc}",
            url=feed_url,
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
BUILTIN_SOURCES: dict[str, Any] = {
    "Grants.gov": fetch_grants_gov,
    "EU Funding & Tenders": fetch_eu_sedia,
    "UKRI Funding Finder": fetch_ukri,
    "Terra Viva Grants": fetch_terra_viva,
    "FundsforNGOs": fetch_funds_for_ngos,
}


async def fetch_all_sources(
    selected_sources: list[str] | None = None,
    custom_feeds: list[dict[str, str]] | None = None,
) -> tuple[list[Grant], list[SourceStatus]]:
    """Fetch grants concurrently from all selected built-in and custom sources."""
    chosen = selected_sources or list(BUILTIN_SOURCES.keys())
    headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers) as client:
        tasks = []
        for name in chosen:
            if name in BUILTIN_SOURCES:
                tasks.append(BUILTIN_SOURCES[name](client))
        for feed in custom_feeds or []:
            fname = feed.get("name", "").strip()
            furl = feed.get("url", "").strip()
            if fname and furl and (selected_sources is None or fname in chosen):
                tasks.append(fetch_custom_rss(client, fname, furl))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_grants: list[Grant] = []
    statuses: list[SourceStatus] = []
    seen_ids: set[str] = set()

    for res in results:
        if isinstance(res, Exception):
            statuses.append(
                SourceStatus(
                    name="Unknown Source",
                    ok=False,
                    count=0,
                    fetched_at=_now_iso(),
                    message=str(res),
                )
            )
            continue
        g_list, st = res
        statuses.append(st)
        for g in g_list:
            if g.id not in seen_ids:
                # Auto-mark past deadlines as Closed
                days_left = g.days_until_deadline()
                if days_left is not None and days_left < 0:
                    g.status = "Closed"
                seen_ids.add(g.id)
                all_grants.append(g)

    # Sort by relevance score descending, then closest upcoming deadline
    all_grants.sort(
        key=lambda g: (
            -g.relevance_score,
            g.deadline if g.deadline else "9999-99-99",
        )
    )
    return all_grants, statuses
