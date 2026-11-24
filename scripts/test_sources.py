"""CLI smoke test for all CIFOR-ICRAF Grant Finder connectors."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grant_finder.sources import fetch_all_sources
from grant_finder.storage import save_cache


async def main() -> None:
    print("Fetching live grants from all built-in sources...")
    grants, statuses = await fetch_all_sources()
    print("\n=== Source Status ===")
    for st in statuses:
        icon = "OK" if st.ok else "FAIL"
        print(f"[{icon}] {st.name}: {st.count} items — {st.message}")

    print(f"\nTotal unique grants: {len(grants)}")
    relevant = [g for g in grants if g.relevance_score > 0]
    print(f"CIFOR-ICRAF relevant (score > 0): {len(relevant)}")
    print("\n=== Top 10 Relevant Grants ===")
    for g in relevant[:10]:
        themes = ", ".join(g.themes) if g.themes else "General"
        print(
            f"  [{g.relevance_score:3d}] ({g.source}) {g.title[:80]} "
            f"| Deadline: {g.deadline or 'N/A'} | Themes: {themes}"
        )

    if grants:
        save_cache(grants, statuses)
        print("\nSaved initial cache to data/grants_cache.json")


if __name__ == "__main__":
    asyncio.run(main())
