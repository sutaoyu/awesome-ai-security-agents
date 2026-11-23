#!/usr/bin/env python3
"""Fetch arXiv/GitHub updates and append unique items to This Week."""

from __future__ import annotations

import os
import re
import sys
import time
from datetime import timedelta
from pathlib import Path

from urllib.parse import quote

import feedparser
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    CATEGORY_AGENTS_FOR_SECURITY,
    CATEGORY_SECURITY_OF_AGENTS,
    README_PATH,
    WEEKLY_START,
    deepseek_chat,
    empty_weekly_body,
    ensure_dirs,
    extract_json_payload,
    get_marked_section,
    heuristic_category,
    load_seen,
    normalize_url,
    now_beijing,
    render_bullet,
    enrich_arxiv_paper_names,
    resolve_item_type,
    save_seen,
    today_beijing_str,
)
from render_readme import update_weekly_section, write_readme


def fetch_arxiv(limit: int = 4) -> list[dict]:
    print("Fetching arXiv RSS...")
    feed = feedparser.parse("https://rss.arxiv.org/rss/cs.AI")
    items: list[dict] = []
    for entry in feed.entries:
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        title_lower = title.lower()
        summary_lower = summary.lower()
        if "agent" not in title_lower and "agent" not in summary_lower:
            continue
        if not any(k in title_lower for k in ("security", "safety", "attack", "defense")):
            continue
        link = entry.get("link", "")
        item_id, canonical = normalize_url(link)
        if not item_id:
            continue
        items.append(
            {
                "id": item_id,
                "name": title.strip(),
                "url": canonical,
                "description": re.sub(r"\s+", " ", summary)[:220].strip(),
                "source": "arxiv",
            }
        )
        if len(items) >= limit:
            break
    print(f"Got {len(items)} arXiv papers")
    return items


def fetch_github(limit: int = 4) -> list[dict]:
    print("Fetching GitHub new repos...")
    token = os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Awesome-Security-Agents-Daily-Action",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    created_after = (now_beijing() - timedelta(days=7)).strftime("%Y-%m-%d")
    query = f'"agent security" created:>{created_after} stars:>10'
    url = (
        "https://api.github.com/search/repositories"
        f"?q={quote(query)}&sort=stars&order=desc&per_page={limit}"
    )

    for attempt in range(3):
        resp = requests.get(url, headers=headers, timeout=45)
        if resp.status_code == 200:
            items = []
            for repo in resp.json().get("items", []):
                html_url = repo.get("html_url", "")
                item_id, canonical = normalize_url(html_url)
                if not item_id:
                    continue
                items.append(
                    {
                        "id": item_id,
                        "name": repo.get("name") or canonical,
                        "url": canonical,
                        "description": (repo.get("description") or "No description").strip(),
                        "stars": repo.get("stargazers_count", 0),
                        "source": "github",
                    }
                )
            print(f"Got {len(items)} GitHub repos")
            return items
        if resp.status_code in (403, 429):
            sleep_time = 30 * (attempt + 1)
            print(f"GitHub rate limited ({resp.status_code}), sleep {sleep_time}s")
            time.sleep(sleep_time)
            continue
        print(f"GitHub API failed: HTTP {resp.status_code}")
        break
    return []


def classify_items(items: list[dict]) -> list[dict]:
    if not items:
        return []

    raw_lines = []
    for item in items:
        stars = f" stars={item['stars']}" if item.get("stars") is not None else ""
        raw_lines.append(
            f"- id: {item['id']}\n  name: {item['name']}\n  url: {item['url']}\n"
            f"  description: {item['description']}{stars}"
        )
    raw_context = "\n".join(raw_lines)

    prompt = f"""
Classify each item into exactly one category:
1. "agents_for_security": AI agents used for cybersecurity tasks
2. "security_of_agents": protecting AI agents from attacks / agent safety

RAW ITEMS:
{raw_context}

RULES:
- Use ONLY the provided items. Do not invent new items.
- For arXiv papers, keep the FULL official paper title (not a short method nickname like "EVA" or "PSEBench").
- Keep each description to one concise English sentence.
- Preserve the given id and url exactly.
- Return JSON only:
{{
  "items": [
    {{
      "id": "...",
      "name": "...",
      "url": "...",
      "description": "...",
      "category": "agents_for_security" | "security_of_agents",
      "stars": null or number
    }}
  ]
}}
"""

    try:
        content = deepseek_chat(prompt)
        payload = extract_json_payload(content)
        classified = payload.get("items", [])
        by_id = {item["id"]: item for item in items}
        result = []
        for row in classified:
            item_id = row.get("id")
            if item_id not in by_id:
                continue
            base = by_id[item_id]
            category = row.get("category")
            if category not in (CATEGORY_AGENTS_FOR_SECURITY, CATEGORY_SECURITY_OF_AGENTS):
                category = heuristic_category(base["name"], base["description"])
            # Prefer scraped arXiv RSS title over any shortened LLM nickname.
            name = row.get("name") or base["name"]
            if item_id.startswith("arxiv:") and base.get("name"):
                name = base["name"]
            entry = {
                "id": item_id,
                "name": name,
                "url": base["url"],
                "description": (row.get("description") or base["description"]).strip(),
                "category": category,
            }
            entry["type"] = resolve_item_type(entry)
            if base.get("stars") is not None:
                entry["stars"] = base["stars"]
            elif row.get("stars") is not None:
                entry["stars"] = row["stars"]
            result.append(entry)
        if result:
            return enrich_arxiv_paper_names(result)
    except Exception as exc:  # noqa: BLE001
        print(f"LLM classify failed, using heuristic: {exc}")

    result = []
    for item in items:
        entry = {
            "id": item["id"],
            "name": item["name"],
            "url": item["url"],
            "description": item["description"],
            "category": heuristic_category(item["name"], item["description"]),
        }
        entry["type"] = resolve_item_type(entry)
        if item.get("stars") is not None:
            entry["stars"] = item["stars"]
        result.append(entry)
    return enrich_arxiv_paper_names(result)


def render_daily_section(date_str: str, items: list[dict]) -> str:
    for_sec = [i for i in items if i["category"] == CATEGORY_AGENTS_FOR_SECURITY]
    of_sec = [i for i in items if i["category"] == CATEGORY_SECURITY_OF_AGENTS]
    lines = [
        f"### Daily Security Intelligence ({date_str})",
        "",
        "> Data fetched via arXiv/GitHub APIs and classified by DeepSeek (deepseek-v4-flash).",
        "",
        "#### Agents for Security",
        "",
    ]
    if for_sec:
        lines.extend(render_bullet(i) for i in for_sec)
    else:
        lines.append("*None today.*")
    lines.extend(["", "#### Security of Agents", ""])
    if of_sec:
        lines.extend(render_bullet(i) for i in of_sec)
    else:
        lines.append("*None today.*")
    lines.extend(["", "---", ""])
    return "\n".join(lines)


DAY_HEADER_RE = re.compile(
    r"^###(?: 📅)? Daily Security Intelligence \((\d{4}-\d{2}-\d{2})\)\s*$",
    re.MULTILINE,
)


def upsert_daily_into_weekly(weekly_body: str, date_str: str, daily_md: str) -> str:
    body = weekly_body.strip()
    if body == empty_weekly_body().strip() or not body:
        return daily_md

    matches = list(DAY_HEADER_RE.finditer(body))
    if not matches:
        return daily_md + "\n" + body

    # Build day blocks
    blocks: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        day = match.group(1)
        blocks.append((day, body[start:end].strip()))

    replaced = False
    new_blocks: list[str] = []
    for day, block in blocks:
        if day == date_str:
            new_blocks.append(daily_md.strip())
            replaced = True
        else:
            new_blocks.append(block)
    if not replaced:
        new_blocks.insert(0, daily_md.strip())
    return "\n\n".join(new_blocks).rstrip() + "\n"


def main() -> int:
    ensure_dirs()
    today = today_beijing_str()
    seen = load_seen()

    raw_items = fetch_arxiv() + fetch_github()
    if not raw_items:
        print("No raw data fetched; exiting without README changes.")
        return 0

    unique_items = []
    for item in raw_items:
        if item["id"] in seen:
            print(f"Skip already seen: {item['id']}")
            continue
        if any(u["id"] == item["id"] for u in unique_items):
            continue
        unique_items.append(item)

    if not unique_items:
        print("All fetched items already seen; exiting without README changes.")
        return 0

    classified = classify_items(unique_items)
    daily_md = render_daily_section(today, classified)

    if not README_PATH.exists() or WEEKLY_START not in README_PATH.read_text(encoding="utf-8"):
        write_readme(weekly_body=daily_md)
    else:
        text = README_PATH.read_text(encoding="utf-8")
        weekly = get_marked_section(text, WEEKLY_START, WEEKLY_END)
        new_weekly = upsert_daily_into_weekly(weekly, today, daily_md)
        update_weekly_section(new_weekly)

    for item in classified:
        seen.add(item["id"])
    save_seen(seen)

    print(f"Updated This Week with {len(classified)} items for {today}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
