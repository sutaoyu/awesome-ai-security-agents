#!/usr/bin/env python3
"""One-time migration: parse legacy README into weekly/catalog/highlights structure."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    ARCHIVE_LEGACY,
    CATEGORY_AGENTS_FOR_SECURITY,
    CATEGORY_SECURITY_OF_AGENTS,
    HIGHLIGHTS_PATH,
    README_PATH,
    catalog_ids,
    empty_weekly_body,
    ensure_dirs,
    extract_urls,
    heuristic_category,
    normalize_url,
    resolve_item_type,
    save_catalog,
    save_seen,
)
from render_readme import write_readme

DAY_SPLIT_RE = re.compile(
    r"(?=^###(?: 📅)? Daily Security Intelligence \(\d{4}-\d{2}-\d{2}\)\s*$)",
    re.MULTILINE,
)
DAY_HEADER_RE = re.compile(
    r"^###(?: 📅)? Daily Security Intelligence \((\d{4}-\d{2}-\d{2})\)\s*$",
    re.MULTILINE,
)
BULLET_RE = re.compile(r"^\*\s+(.+)$")
STARS_RE = re.compile(r"⭐\s*(\d+)")
BOLD_NAME_RE = re.compile(r"\*\*(.+?)\*\*")
HIGHLIGHTS_START_RE = re.compile(
    r"^# An Awesome List for AI Security Agents\s*$",
    re.MULTILINE,
)


def split_daily_and_highlights(text: str) -> tuple[str, str]:
    match = HIGHLIGHTS_START_RE.search(text)
    if not match:
        return text, ""
    return text[: match.start()].rstrip(), text[match.start() :].strip()


def clean_description(desc: str) -> str:
    desc = re.sub(r"\[([^\]]*)\]\((https?://[^)]+)\)", r"\1", desc)
    desc = re.sub(r"\(⭐[^)]*\)", "", desc)
    desc = re.sub(r"^\*+\s*", "", desc)
    desc = re.sub(r"^[-–—:\s]+", "", desc)
    desc = re.sub(r"\bLink\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\[\s*\]", "", desc)
    desc = re.sub(r"\s+", " ", desc).strip(" -–—:*")
    return desc


def parse_name_and_desc(line: str, urls: list[str]) -> tuple[str, str]:
    working = re.sub(r"^\*\s+", "", line).strip()

    # Prefer markdown link label as name: [SysEvolve](https://...)
    link_name = re.match(r"^\[([^\]]+)\]\((https?://[^)]+)\)\s*", working)
    if link_name and not working.startswith("**"):
        name = link_name.group(1).strip()
        working = working[link_name.end() :]
        for url in urls:
            working = working.replace(url, " ")
        desc = clean_description(working)
        return name, desc

    # Convert remaining markdown links to "label url" then strip urls
    working = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 \2", working)
    for url in urls:
        working = working.replace(url, " ")
    working = re.sub(r"\[(https?://[^\]]+)\]", " ", working)

    name = ""
    bold = BOLD_NAME_RE.search(working)
    if bold:
        name = bold.group(1).strip()
        working = working[: bold.start()] + working[bold.end() :]
    name = re.sub(r"^\[|\]$", "", name).strip()
    name = re.sub(r"\s*\(⭐[^)]*\)\s*", " ", name).strip()
    name = name.strip()

    desc = clean_description(working)

    # Recover title when name is missing/id-like and description starts with "Title - ..."
    if (not name or re.fullmatch(r"\d{4}\.\d{4,5}", name)) and " - " in desc:
        maybe_name, maybe_desc = desc.split(" - ", 1)
        maybe_name = maybe_name.strip().strip("*")
        if maybe_name and not maybe_name.lower().startswith("http"):
            name = maybe_name
            desc = clean_description(maybe_desc)

    if not name:
        item_id, _ = normalize_url(urls[0]) if urls else (None, None)
        if item_id and item_id.startswith("github:"):
            name = item_id.split("/")[-1]
        elif item_id and item_id.startswith("arxiv:"):
            name = item_id.split(":", 1)[1]
        else:
            name = "Untitled"

    return name, desc


def parse_daily_block(block: str) -> list[dict]:
    header = DAY_HEADER_RE.search(block)
    if not header:
        return []
    date_str = header.group(1)
    current_category = None
    items: list[dict] = []

    for raw_line in block.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if line.startswith("#") and "agents for security" in lower:
            current_category = CATEGORY_AGENTS_FOR_SECURITY
            continue
        if line.startswith("#") and "security of agents" in lower:
            current_category = CATEGORY_SECURITY_OF_AGENTS
            continue
        if not line.startswith("*"):
            continue
        if current_category is None:
            continue
        if "none" in lower and "identified" in lower:
            continue
        if lower in {"*none today.*", "*none identified from the provided raw data.*"}:
            continue

        urls = extract_urls(line)
        if not urls:
            continue

        chosen_id = None
        chosen_url = None
        for url in urls:
            item_id, canonical = normalize_url(url)
            if item_id:
                chosen_id, chosen_url = item_id, canonical
                break
        if not chosen_id:
            continue

        name, desc = parse_name_and_desc(line, urls)
        stars_match = STARS_RE.search(line)
        entry = {
            "id": chosen_id,
            "name": name,
            "url": chosen_url,
            "description": desc,
            "category": current_category,
            "first_seen": date_str,
        }
        entry["type"] = resolve_item_type(entry)
        if stars_match:
            entry["stars"] = int(stars_match.group(1))
        items.append(entry)
    return items


def parse_highlight_ids(highlights: str) -> set[str]:
    ids: set[str] = set()
    for url in extract_urls(highlights):
        item_id, _ = normalize_url(url)
        if item_id:
            ids.add(item_id)
    return ids


def dedupe_entries(entries: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for entry in entries:
        item_id = entry["id"]
        if item_id not in best:
            best[item_id] = entry
            continue
        prev = best[item_id]
        # Keep earliest first_seen
        if entry["first_seen"] < prev["first_seen"]:
            merged = dict(entry)
            # Prefer longer description
            if len(prev.get("description", "")) > len(merged.get("description", "")):
                merged["description"] = prev["description"]
            if prev.get("stars") is not None and merged.get("stars") is None:
                merged["stars"] = prev["stars"]
            best[item_id] = merged
        else:
            if len(entry.get("description", "")) > len(prev.get("description", "")):
                prev["description"] = entry["description"]
            if entry.get("stars") is not None:
                prev["stars"] = entry["stars"]
            if not prev.get("name") and entry.get("name"):
                prev["name"] = entry["name"]
    return list(best.values())


def extract_highlights_body(highlights_full: str) -> str:
    """Keep curated sections under Highlights, without repeating the top H1 intro twice."""
    if not highlights_full.strip():
        return "_No curated highlights yet._\n"

    # Drop the leading H1 + short intro; keep from first ## section.
    parts = highlights_full.splitlines()
    start_idx = 0
    for i, line in enumerate(parts):
        if line.startswith("## "):
            start_idx = i
            break
    body = "\n".join(parts[start_idx:]).strip()
    return body + "\n" if body else highlights_full.strip() + "\n"


def main() -> int:
    ensure_dirs()
    legacy_path = ARCHIVE_LEGACY / "README-before-migration.md"

    # Prefer previously archived full history so re-runs stay idempotent.
    if legacy_path.exists() and "Daily Security Intelligence" in legacy_path.read_text(
        encoding="utf-8"
    ):
        original = legacy_path.read_text(encoding="utf-8")
        print(f"Using archived legacy README: {legacy_path}")
    elif README_PATH.exists():
        original = README_PATH.read_text(encoding="utf-8")
        if "Daily Security Intelligence" not in original:
            print("README has no daily history and no usable archive; aborting.")
            return 1
        legacy_path.write_text(original, encoding="utf-8")
        print(f"Archived original README to {legacy_path}")
    else:
        print("README.md not found")
        return 1

    daily_text, highlights_full = split_daily_and_highlights(original)
    highlights_body = extract_highlights_body(highlights_full)
    HIGHLIGHTS_PATH.write_text(highlights_body, encoding="utf-8")
    highlight_ids = parse_highlight_ids(highlights_body)
    print(f"Highlights links: {len(highlight_ids)}")

    blocks = [b for b in DAY_SPLIT_RE.split(daily_text) if b.strip()]
    all_entries: list[dict] = []
    for block in blocks:
        all_entries.extend(parse_daily_block(block))
    print(f"Parsed daily bullets: {len(all_entries)}")

    deduped = dedupe_entries(all_entries)
    print(f"Unique valid entries: {len(deduped)}")

    # Catalog excludes highlights to avoid double listing
    catalog_entries = []
    for entry in deduped:
        if entry["id"] in highlight_ids:
            continue
        if not entry.get("description"):
            entry["description"] = entry["name"]
        # Ensure category exists
        if entry.get("category") not in (
            CATEGORY_AGENTS_FOR_SECURITY,
            CATEGORY_SECURITY_OF_AGENTS,
        ):
            entry["category"] = heuristic_category(entry["name"], entry.get("description", ""))
        catalog_entries.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "url": entry["url"],
                "description": entry.get("description", ""),
                "category": entry["category"],
                "type": entry["type"],
                "first_seen": entry["first_seen"],
                **({"stars": entry["stars"]} if entry.get("stars") is not None else {}),
            }
        )

    catalog = {
        "entries": catalog_entries,
        "last_rollup_week": None,
    }
    save_catalog(catalog)

    seen_ids = set(catalog_ids(catalog)) | highlight_ids | {e["id"] for e in deduped}
    save_seen(seen_ids)

    write_readme(weekly_body=empty_weekly_body(), catalog=catalog)

    print(
        f"Migration done: catalog={len(catalog_entries)} "
        f"seen={len(seen_ids)} highlights={HIGHLIGHTS_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
