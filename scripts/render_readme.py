#!/usr/bin/env python3
"""Render README.md from structured data files."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    CATALOG_END,
    CATALOG_START,
    HIGHLIGHTS_PATH,
    README_PATH,
    WEEKLY_END,
    WEEKLY_START,
    empty_weekly_body,
    ensure_dirs,
    get_marked_section,
    intro_markdown,
    load_catalog,
    render_catalog_markdown,
    replace_marked_section,
)


def load_highlights() -> str:
    if HIGHLIGHTS_PATH.exists():
        return HIGHLIGHTS_PATH.read_text(encoding="utf-8")
    return ""


def build_readme(weekly_body: str | None = None, catalog: dict | None = None) -> str:
    ensure_dirs()
    catalog = catalog if catalog is not None else load_catalog()

    if weekly_body is None and README_PATH.exists():
        existing = README_PATH.read_text(encoding="utf-8")
        weekly_body = get_marked_section(existing, WEEKLY_START, WEEKLY_END)
    if not weekly_body:
        weekly_body = empty_weekly_body()

    catalog_md = render_catalog_markdown(catalog, highlights_text=load_highlights())

    parts = [
        intro_markdown().rstrip(),
        "",
        "## This Week",
        "",
        WEEKLY_START,
        weekly_body.rstrip(),
        WEEKLY_END,
        "",
        CATALOG_START,
        catalog_md.rstrip(),
        CATALOG_END,
        "",
    ]
    return "\n".join(parts)


def write_readme(weekly_body: str | None = None, catalog: dict | None = None) -> Path:
    text = build_readme(weekly_body=weekly_body, catalog=catalog)
    README_PATH.write_text(text, encoding="utf-8")
    return README_PATH


def update_weekly_section(weekly_body: str) -> None:
    if not README_PATH.exists():
        write_readme(weekly_body=weekly_body)
        return
    text = README_PATH.read_text(encoding="utf-8")
    if WEEKLY_START not in text or WEEKLY_END not in text:
        write_readme(weekly_body=weekly_body)
        return
    text = replace_marked_section(text, WEEKLY_START, WEEKLY_END, weekly_body)
    README_PATH.write_text(text, encoding="utf-8")


def update_catalog_section(catalog: dict | None = None) -> None:
    catalog = catalog if catalog is not None else load_catalog()
    body = render_catalog_markdown(catalog, highlights_text=load_highlights())
    if not README_PATH.exists():
        write_readme(catalog=catalog)
        return
    text = README_PATH.read_text(encoding="utf-8")
    if CATALOG_START not in text or CATALOG_END not in text:
        write_readme(catalog=catalog)
        return
    text = replace_marked_section(text, CATALOG_START, CATALOG_END, body)
    README_PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    path = write_readme()
    print(f"Rendered {path}")
