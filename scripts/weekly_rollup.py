#!/usr/bin/env python3
"""Sunday rollup: merge novel weekly items into catalog and clear This Week."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    ARCHIVE_WEEKLY,
    CATEGORY_AGENTS_FOR_SECURITY,
    CATEGORY_SECURITY_OF_AGENTS,
    HIGHLIGHTS_PATH,
    README_PATH,
    WEEKLY_END,
    WEEKLY_START,
    catalog_ids,
    deepseek_chat,
    empty_weekly_body,
    ensure_dirs,
    extract_json_payload,
    extract_urls,
    get_marked_section,
    iso_week_id,
    load_catalog,
    normalize_url,
    now_beijing,
    enrich_arxiv_paper_names,
    filter_github_entries_for_catalog,
    resolve_item_type,
    save_catalog,
)
from render_readme import update_catalog_section, update_weekly_section

STARS_RE = re.compile(r"⭐\s*(\d+)")
BOLD_NAME_RE = re.compile(r"\*\*(.+?)\*\*")


def parse_weekly_items(weekly_body: str) -> list[dict]:
    items: list[dict] = []
    current_category = CATEGORY_SECURITY_OF_AGENTS

    for raw_line in weekly_body.splitlines():
        line = raw_line.strip()
        if line.startswith(">"):
            quote = line.lstrip(">").strip()
            if quote and items and not items[-1].get("description"):
                items[-1]["description"] = quote
            continue
        if "Agents for Security" in line and line.startswith("#"):
            current_category = CATEGORY_AGENTS_FOR_SECURITY
            continue
        if "Security of Agents" in line and line.startswith("#"):
            current_category = CATEGORY_SECURITY_OF_AGENTS
            continue
        if not line.startswith("*"):
            continue

        urls = extract_urls(line)
        if not urls:
            continue
        item_id, canonical = None, None
        for url in urls:
            item_id, canonical = normalize_url(url)
            if item_id:
                break
        if not item_id:
            continue

        working = re.sub(r"^\*\s+", "", line).strip()
        working = re.sub(r"!\[[^\]]*\]\([^)]+\)\s*", "", working)
        name = ""
        link_name = re.match(r"^\[([^\]]+)\]\((https?://[^)]+)\)\s*", working)
        if link_name and not working.startswith("**"):
            name = link_name.group(1).strip()
            working = working[link_name.end() :]
        else:
            bold = BOLD_NAME_RE.search(working)
            if bold:
                name = bold.group(1).strip()
                working = working[: bold.start()] + working[bold.end() :]
        name = re.sub(r"\s*\(⭐[^)]*\)\s*", " ", name).strip() or item_id.split("/")[-1]

        desc = working
        for url in urls:
            desc = desc.replace(f"[{url}]({url})", "")
            desc = desc.replace(f"[Link]({url})", "")
            desc = desc.replace(url, "")
        desc = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", desc)
        desc = re.sub(r"\bLink\b", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"^\s*[-–—:]\s*", "", desc)
        desc = re.sub(r"\s+", " ", desc).strip(" -–—:")

        stars_match = STARS_RE.search(line)
        entry = {
            "id": item_id,
            "name": name,
            "url": canonical,
            "description": desc,
            "category": current_category,
        }
        entry["type"] = resolve_item_type(entry)
        if stars_match:
            entry["stars"] = int(stars_match.group(1))
        items.append(entry)

    # Deduplicate within week, keep first
    seen = set()
    unique = []
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        unique.append(item)
    return unique


def refine_with_llm(items: list[dict]) -> list[dict]:
    if not items:
        return []

    raw = []
    for item in items:
        raw.append(
            f"- id: {item['id']}\n  name: {item['name']}\n  url: {item['url']}\n"
            f"  description: {item.get('description', '')}\n  category_hint: {item['category']}"
        )
    prompt = f"""
You are merging weekly AI-security-agent finds into a curated catalog.

ITEMS:
{chr(10).join(raw)}

TASK:
For each item, confirm or fix ONLY the theme category and write a one-sentence English description.
For papers, expand short nicknames into the FULL paper title when the provided name is abbreviated.
Drop items that are clearly off-topic for AI agent security.
Do NOT decide resource type (paper/project/benchmark); that is handled separately.

Categories:
- agents_for_security
- security_of_agents

RULES:
- Do NOT invent new urls or ids.
- Prefer full academic titles for papers; do not shorten them to method acronyms alone.
- Return JSON only:
{{
  "items": [
    {{
      "id": "...",
      "name": "...",
      "url": "...",
      "description": "...",
      "category": "agents_for_security" | "security_of_agents",
      "keep": true
    }}
  ]
}}
"""
    try:
        payload = extract_json_payload(deepseek_chat(prompt))
        by_id = {i["id"]: i for i in items}
        result = []
        for row in payload.get("items", []):
            if not row.get("keep", True):
                continue
            item_id = row.get("id")
            if item_id not in by_id:
                continue
            base = by_id[item_id]
            category = row.get("category")
            if category not in (CATEGORY_AGENTS_FOR_SECURITY, CATEGORY_SECURITY_OF_AGENTS):
                category = base["category"]
            entry = {
                "id": item_id,
                "name": row.get("name") or base["name"],
                "url": base["url"],
                "description": (row.get("description") or base.get("description") or "").strip(),
                "category": category,
                "first_seen": base.get("first_seen"),
            }
            entry["type"] = resolve_item_type(entry)
            if base.get("stars") is not None:
                entry["stars"] = base["stars"]
            result.append(entry)
        return result
    except Exception as exc:  # noqa: BLE001
        print(f"LLM refine failed, keeping parsed items: {exc}")
        for item in items:
            item["type"] = resolve_item_type(item)
        return items


def main() -> int:
    ensure_dirs()
    week_id = iso_week_id(now_beijing())
    catalog = load_catalog()

    if catalog.get("last_rollup_week") == week_id:
        print(f"Rollup for {week_id} already applied; skipping.")
        return 0

    if not README_PATH.exists():
        print("README.md missing; nothing to roll up.")
        return 0

    text = README_PATH.read_text(encoding="utf-8")
    weekly = get_marked_section(text, WEEKLY_START, WEEKLY_END)
    if not weekly or weekly.strip() == empty_weekly_body().strip():
        print("This Week is empty; marking rollup complete.")
        catalog["last_rollup_week"] = week_id
        save_catalog(catalog)
        return 0

    parsed = parse_weekly_items(weekly)
    existing = catalog_ids(catalog)
    highlight_ids: set[str] = set()
    if HIGHLIGHTS_PATH.exists():
        for url in extract_urls(HIGHLIGHTS_PATH.read_text(encoding="utf-8")):
            item_id, _ = normalize_url(url)
            if item_id:
                highlight_ids.add(item_id)
    novel = [i for i in parsed if i["id"] not in existing and i["id"] not in highlight_ids]
    print(f"Weekly items={len(parsed)}, novel={len(novel)}")

    refined = refine_with_llm(novel) if novel else []
    refined = enrich_arxiv_paper_names(refined)
    refined, dropped_repos = filter_github_entries_for_catalog(refined)
    if dropped_repos:
        print("Skipped GitHub repos for catalog:")
        for reason in dropped_repos:
            print(f"  - {reason}")
    today = now_beijing().strftime("%Y-%m-%d")
    for item in refined:
        item["first_seen"] = item.get("first_seen") or today
        if not item.get("description"):
            item["description"] = item["name"]
        item["type"] = resolve_item_type(item)
        catalog.setdefault("entries", []).append(
            {
                "id": item["id"],
                "name": item["name"],
                "url": item["url"],
                "description": item.get("description", ""),
                "category": item["category"],
                "type": item["type"],
                "first_seen": item["first_seen"],
                **({"stars": item["stars"]} if item.get("stars") is not None else {}),
            }
        )

    # Archive weekly content before clearing
    archive_path = ARCHIVE_WEEKLY / f"{week_id}.md"
    archive_path.write_text(
        f"# Weekly archive {week_id}\n\n{weekly.strip()}\n",
        encoding="utf-8",
    )

    catalog["last_rollup_week"] = week_id
    save_catalog(catalog)
    update_catalog_section(catalog)
    update_weekly_section(empty_weekly_body())

    print(f"Rollup complete for {week_id}: added {len(refined)} entries; archived to {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
