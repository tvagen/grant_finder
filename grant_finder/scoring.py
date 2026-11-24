"""CIFOR-ICRAF thematic tagging and relevance scoring."""

from __future__ import annotations

import re

from grant_finder.models import (
    ALL_REGIONS,
    COUNTRY_ALIASES,
    REGION_COUNTRIES,
    REGION_KEYWORDS,
    THEMES,
    Grant,
)

# Precompiled regexes for fast, accurate geography extraction
_COUNTRY_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = []
for _reg, _countries in REGION_COUNTRIES.items():
    for _c in _countries:
        _canonical = COUNTRY_ALIASES.get(_c.lower(), _c)
        # Require exact word boundaries; avoid matching "Guinea" inside "Papua New Guinea" or "Guinea-Bissau"
        _pat = re.compile(rf"\b{re.escape(_c)}\b", flags=re.IGNORECASE)
        _COUNTRY_PATTERNS.append((_reg, _canonical, _pat))

_REGION_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    reg: [re.compile(rf"\b{re.escape(kw)}\b", flags=re.IGNORECASE) for kw in kws]
    for reg, kws in REGION_KEYWORDS.items()
}


def extract_geography(grant: Grant) -> tuple[list[str], list[str]]:
    """Extract continents/regions and specific countries mentioned in a grant."""
    # Scan title, description, and funder (avoid synthetic placeholder strings in grant.geography)
    text = " ".join(
        filter(
            None,
            [
                grant.title,
                grant.description,
                grant.funder,
            ],
        )
    )

    found_regions: list[str] = []
    found_countries: list[str] = []

    # 1. Detect explicit country mentions (also infer parent continent/region)
    for region, canonical, pat in _COUNTRY_PATTERNS:
        if pat.search(text):
            if canonical not in found_countries:
                found_countries.append(canonical)
            if region not in found_regions:
                found_regions.append(region)

    # Avoid false "Guinea" match when only "Papua New Guinea" or "Guinea-Bissau" or "Equatorial Guinea" appeared
    if "Guinea" in found_countries and any(
        other in found_countries
        for other in ("Papua New Guinea", "Guinea-Bissau", "Equatorial Guinea")
    ):
        stripped = re.sub(
            r"\b(?:Papua New Guinea|Guinea-Bissau|Equatorial Guinea)\b",
            "",
            text,
            flags=re.IGNORECASE,
        )
        if not re.search(r"\bGuinea\b", stripped, flags=re.IGNORECASE):
            found_countries.remove("Guinea")

    # 2. Detect continent / region keywords
    for region in ALL_REGIONS:
        if region in found_regions:
            continue
        for pat in _REGION_PATTERNS[region]:
            if pat.search(text):
                found_regions.append(region)
                break

    # 3. Source-based fallback if nothing matched (or for global developing-world directories)
    src = (grant.source or "").lower()
    if not found_regions:
        if "grants.gov" in src:
            found_regions.append("North America")
        elif "eu funding" in src or "ukri" in src:
            found_regions.append("Europe")
        else:
            found_regions.append("Global / Developing Countries")
    elif ("terra viva" in src or "fundsforngos" in src) and "Global / Developing Countries" not in found_regions and not found_countries:
        found_regions.append("Global / Developing Countries")

    # Preserve canonical region ordering & alphabetical country ordering
    ordered_regions = [r for r in ALL_REGIONS if r in found_regions]
    found_countries.sort()
    return ordered_regions, found_countries

# High-value core CIFOR-ICRAF terms get extra weight
CORE_PRIORITY_TERMS: set[str] = {
    "agroforestry",
    "regenerative agriculture",
    "agroecology",
    "land restoration",
    "forest restoration",
    "landscape restoration",
    "soil health",
    "soil carbon",
    "biodiversity",
    "reforestation",
    "deforestation",
    "tropical forest",
    "climate-smart agriculture",
    "nature-based solution",
    "smallholder",
    "peatland",
    "mangrove",
    "redd+",
    "silvopasture",
}


# Regex for extracting funding / grant amounts from free text
_AMOUNT_PATTERN = re.compile(
    r"""
    (?P<prefix>(?:up\s+to\s+|maximum\s+of\s+|between\s+)?)
    (?P<curr>(?:US\$|USD|EUR|GBP|CHF|CAD|AUD|€|\$|£)\s*)
    (?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
    (?P<unit>\s*(?:billion|million|thousand|bn|mn|m|k)\b)?
    (?:\s*(?:to|-|–|—)\s*(?:US\$|USD|EUR|GBP|CHF|CAD|AUD|€|\$|£)?\s*
        (?P<num2>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
        (?P<unit2>\s*(?:billion|million|thousand|bn|mn|m|k)\b)?
    )?
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)

# Also match trailing currency like "5 million EUR" or "500,000 USD"
_AMOUNT_TRAILING_PATTERN = re.compile(
    r"""
    (?P<prefix>(?:up\s+to\s+)?)
    (?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
    (?P<unit>\s*(?:billion|million|thousand|bn|mn|m|k))?
    \s+(?P<curr>EUR|USD|GBP|CHF|CAD|AUD|euros?|dollars?|pounds?)\b
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


def extract_amount_from_text(text: str) -> str:
    """Extract a clean funding/call amount string from grant text if present."""
    if not text:
        return ""
    for m in _AMOUNT_PATTERN.finditer(text):
        num_str = m.group("num").replace(",", "")
        unit = (m.group("unit") or "").strip().lower()
        try:
            val = float(num_str)
        except ValueError:
            continue
        # Ignore tiny stray numbers like "$1" or "$5" unless they have a multiplier unit
        if not unit and val < 500:
            continue
        matched = re.sub(r"\s+", " ", m.group(0)).strip()
        return matched

    for m in _AMOUNT_TRAILING_PATTERN.finditer(text):
        num_str = m.group("num").replace(",", "")
        unit = (m.group("unit") or "").strip().lower()
        try:
            val = float(num_str)
        except ValueError:
            continue
        if not unit and val < 500:
            continue
        matched = re.sub(r"\s+", " ", m.group(0)).strip()
        return matched

    return ""


def score_and_tag_grant(grant: Grant) -> Grant:
    """Compute CIFOR-ICRAF relevance score (0-100) and assign thematic tags."""
    title_text = (grant.title or "").lower()
    body_text = " ".join(
        filter(
            None,
            [
                grant.title,
                grant.description,
                grant.funder,
                grant.geography,
            ],
        )
    ).lower()

    matched_themes: list[str] = []
    matched_keywords: list[str] = []
    raw_score = 0

    for theme_name, meta in THEMES.items():
        theme_hits: list[str] = []
        for kw in meta["keywords"]:
            # Word-boundary matching for short keywords; substring for multi-word phrases
            if len(kw) <= 4:
                found_body = bool(re.search(rf"\b{re.escape(kw)}\b", body_text))
                found_title = bool(re.search(rf"\b{re.escape(kw)}\b", title_text))
            else:
                found_body = kw in body_text
                found_title = kw in title_text

            if found_body:
                theme_hits.append(kw)
                if kw not in matched_keywords:
                    matched_keywords.append(kw)
                weight = 14 if kw in CORE_PRIORITY_TERMS else 7
                if found_title:
                    weight = int(weight * 1.6)
                raw_score += weight

        if theme_hits:
            matched_themes.append(theme_name)

    # Bonus for multi-theme synergy (typical of CIFOR-ICRAF integrated landscape work)
    if len(matched_themes) >= 2:
        raw_score += 8 * min(len(matched_themes) - 1, 3)

    # Cap to 0-100
    grant.themes = matched_themes
    grant.matched_keywords = matched_keywords[:12]
    grant.relevance_score = min(100, raw_score)
    regions, countries = extract_geography(grant)
    grant.regions = regions
    grant.countries = countries
    if not grant.amount:
        grant.amount = extract_amount_from_text(
            f"{grant.title or ''} {grant.description or ''}"
        )
    return grant
