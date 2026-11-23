#!/usr/bin/env python3
"""Shared helpers for daily update, weekly rollup, and migration."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ARCHIVE_WEEKLY = ROOT / "archive" / "weekly"
ARCHIVE_LEGACY = ROOT / "archive" / "legacy"
README_PATH = ROOT / "README.md"
SEEN_PATH = DATA_DIR / "seen.json"
CATALOG_PATH = DATA_DIR / "catalog.json"
HIGHLIGHTS_PATH = DATA_DIR / "highlights.md"

WEEKLY_START = "<!-- WEEKLY_START -->"
WEEKLY_END = "<!-- WEEKLY_END -->"
CATALOG_START = "<!-- CATALOG_START -->"
CATALOG_END = "<!-- CATALOG_END -->"

BEIJING = timezone(timedelta(hours=8))

CATEGORY_AGENTS_FOR_SECURITY = "agents_for_security"
CATEGORY_SECURITY_OF_AGENTS = "security_of_agents"
CATEGORY_LABELS = {
    CATEGORY_AGENTS_FOR_SECURITY: "Agents for Security",
    CATEGORY_SECURITY_OF_AGENTS: "Security of Agents",
}
TYPE_PAPER = "paper"
TYPE_PROJECT = "project"
TYPE_BENCHMARK = "benchmark"
TYPE_BLOG = "blog"

RESOURCE_ORDER = (
    (TYPE_PAPER, "## 🔬 *Research Papers*"),
    (TYPE_PROJECT, "## 💻 *Open-Source Projects*"),
    (TYPE_BLOG, "## ✍️ *Technical Blogs*"),
    (TYPE_BENCHMARK, "## 📂 *Benchmarks*"),
)

MONTH_ABBR = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

URL_RE = re.compile(r"https?://[^\s\)\]\>\"']+")
GITHUB_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)
ARXIV_RE = re.compile(
    r"https?://(?:export\.)?arxiv\.org/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5})(?:v\d+)?",
    re.IGNORECASE,
)
DOI_RE = re.compile(r"https?://(?:dx\.)?doi\.org/[^\s\)\]\>\"']+", re.IGNORECASE)
ACM_RE = re.compile(r"https?://dl\.acm\.org/[^\s\)\]\>\"']+", re.IGNORECASE)

PLACEHOLDER_HOSTS = {"notfoundco.com", "www.notfoundco.com", "example.com", "www.example.com"}


def now_beijing() -> datetime:
    return datetime.now(BEIJING)


def today_beijing_str() -> str:
    return now_beijing().strftime("%Y-%m-%d")


def iso_week_id(dt: datetime | None = None) -> str:
    dt = dt or now_beijing()
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_WEEKLY.mkdir(parents=True, exist_ok=True)
    ARCHIVE_LEGACY.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_seen() -> set[str]:
    data = load_json(SEEN_PATH, {"ids": []})
    return set(data.get("ids", []))


def save_seen(ids: set[str]) -> None:
    save_json(SEEN_PATH, {"ids": sorted(ids)})


def load_catalog() -> dict[str, Any]:
    return load_json(
        CATALOG_PATH,
        {"entries": [], "last_rollup_week": None},
    )


def save_catalog(catalog: dict[str, Any]) -> None:
    catalog["entries"] = sorted(
        catalog.get("entries", []),
        key=lambda e: (e.get("type", ""), e.get("category", ""), e.get("name", "").lower()),
    )
    save_json(CATALOG_PATH, catalog)


def catalog_ids(catalog: dict[str, Any]) -> set[str]:
    return {e["id"] for e in catalog.get("entries", []) if e.get("id")}


def normalize_url(url: str) -> tuple[str | None, str | None]:
    """Return (stable_id, canonical_url) or (None, None) if invalid/placeholder."""
    if not url:
        return None, None
    url = url.strip().rstrip(".,);]")
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host in PLACEHOLDER_HOSTS:
        return None, None

    gh = GITHUB_RE.match(url)
    if gh:
        owner, repo = gh.group(1), gh.group(2)
        if owner.lower() in {"topics", "search", "orgs", "settings", "marketplace"}:
            return None, None
        repo = repo.removesuffix(".git")
        if repo.lower() in {"issues", "pulls", "actions", "wiki", "releases", "tree", "blob"}:
            return None, None
        stable = f"github:{owner.lower()}/{repo.lower()}"
        return stable, f"https://github.com/{owner}/{repo}"

    arxiv = ARXIV_RE.match(url)
    if arxiv:
        paper_id = arxiv.group(1)
        return f"arxiv:{paper_id}", f"https://arxiv.org/abs/{paper_id}"

    if DOI_RE.match(url) or ACM_RE.match(url):
        # Keep full URL as id for non-arxiv papers
        clean = url.split("?")[0].rstrip("/")
        return f"web:{clean.lower()}", clean

    # Reject generic/unknown hosts for catalog quality
    return None, None


def github_owner_repo(url: str) -> tuple[str, str] | None:
    match = GITHUB_RE.match(url or "")
    if not match:
        return None
    owner, repo = match.group(1), match.group(2).removesuffix(".git")
    return owner, repo


def looks_like_benchmark(name: str = "", description: str = "", url: str = "") -> bool:
    text = f"{name} {description} {url}".lower()
    return any(token in text for token in ("benchmark", "bench", "-bench", "_bench"))


def item_type_from_id(item_id: str, name: str = "", description: str = "", url: str = "") -> str:
    if item_id.startswith("arxiv:") or item_id.startswith("web:"):
        return TYPE_PAPER
    if item_id.startswith("github:") and looks_like_benchmark(name, description, url):
        return TYPE_BENCHMARK
    return TYPE_PROJECT


def resolve_item_type(entry: dict[str, Any]) -> str:
    return item_type_from_id(
        entry.get("id", ""),
        name=entry.get("name", ""),
        description=entry.get("description", ""),
        url=entry.get("url", ""),
    )


def format_month_label(date_str: str | None) -> str:
    if not date_str:
        return "Unknown"
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    except ValueError:
        return "Unknown"
    return f"{MONTH_ABBR[dt.month - 1]} {dt.year}"


def fetch_arxiv_titles(paper_ids: list[str]) -> dict[str, str]:
    """Fetch official arXiv titles for a list of paper ids like 2505.14289."""
    import xml.etree.ElementTree as ET

    ids = [pid.strip() for pid in paper_ids if pid and re.fullmatch(r"\d{4}\.\d{4,5}", pid.strip())]
    if not ids:
        return {}

    titles: dict[str, str] = {}
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for i in range(0, len(ids), 20):
        batch = ids[i : i + 20]
        url = (
            "http://export.arxiv.org/api/query?id_list="
            + ",".join(batch)
            + f"&max_results={len(batch)}"
        )
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "awesome-ai-security-agents/1.0"},
                timeout=60,
            )
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.text)
            for entry in root.findall("a:entry", ns):
                id_url = (entry.find("a:id", ns).text or "") if entry.find("a:id", ns) is not None else ""
                match = re.search(r"(\d{4}\.\d{4,5})", id_url)
                title_node = entry.find("a:title", ns)
                if not match or title_node is None or not title_node.text:
                    continue
                titles[match.group(1)] = " ".join(title_node.text.split())
        except Exception:  # noqa: BLE001
            continue
        if i + 20 < len(ids):
            time.sleep(1.0)
    return titles


def enrich_arxiv_paper_names(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace short/nickname paper names with official arXiv titles when available."""
    paper_ids = [
        e["id"].split(":", 1)[1]
        for e in entries
        if e.get("id", "").startswith("arxiv:")
    ]
    titles = fetch_arxiv_titles(paper_ids)
    for entry in entries:
        item_id = entry.get("id", "")
        if not item_id.startswith("arxiv:"):
            continue
        pid = item_id.split(":", 1)[1]
        official = titles.get(pid)
        if official:
            entry["name"] = official
    return entries


MIN_GITHUB_STARS_FOR_CATALOG = 50


def github_api_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Awesome-Security-Agents-Daily-Action",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _parse_shields_star_count(value: str | int | float | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower().replace(",", "")
    if not text or text in {"repo not found", "invalid", "none"}:
        return None
    mult = 1.0
    if text.endswith("k"):
        mult = 1000.0
        text = text[:-1]
    elif text.endswith("m"):
        mult = 1_000_000.0
        text = text[:-1]
    try:
        return int(float(text) * mult)
    except ValueError:
        return None


def fetch_github_repo_meta(owner: str, repo: str, retries: int = 2) -> dict[str, Any]:
    """Fetch repo metadata via GitHub API, with HTML/shields fallback.

    Returns a dict with keys:
    - ok: True when repo exists
    - not_found: True only when the repo is confirmed missing
    - stars / error for callers
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    last_error = "unknown"

    for attempt in range(retries):
        try:
            resp = requests.get(api_url, headers=github_api_headers(), timeout=30)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code == 404:
            return {"ok": False, "not_found": True, "error": "404"}
        if resp.status_code in (403, 429):
            last_error = f"rate_limited:{resp.status_code}"
            break
        if resp.status_code != 200:
            last_error = f"http:{resp.status_code}"
            time.sleep(1.5 * (attempt + 1))
            continue
        data = resp.json()
        return {
            "ok": True,
            "not_found": False,
            "stars": int(data.get("stargazers_count") or 0),
            "full_name": data.get("full_name") or f"{owner}/{repo}",
            "html_url": data.get("html_url") or f"https://github.com/{owner}/{repo}",
            "description": data.get("description") or "",
        }

    # Fallback path that does not depend on GitHub REST quota.
    page_url = f"https://github.com/{owner}/{repo}"
    try:
        page = requests.get(
            page_url,
            headers={"User-Agent": "Awesome-Security-Agents-Daily-Action"},
            timeout=30,
            allow_redirects=True,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "not_found": False, "error": f"page:{exc}"}

    if page.status_code == 404:
        return {"ok": False, "not_found": True, "error": "404"}
    if page.status_code != 200:
        return {"ok": False, "not_found": False, "error": f"page_http:{page.status_code};{last_error}"}

    stars = None
    try:
        badge = requests.get(
            f"https://img.shields.io/github/stars/{owner}/{repo}.json",
            headers={"User-Agent": "Awesome-Security-Agents-Daily-Action"},
            timeout=30,
        )
        if badge.status_code == 200:
            payload = badge.json()
            message = str(payload.get("message", "")).lower()
            if "not found" in message:
                return {"ok": False, "not_found": True, "error": "shields_not_found"}
            stars = _parse_shields_star_count(payload.get("message") or payload.get("value"))
    except Exception:  # noqa: BLE001
        stars = None

    if stars is None:
        # Last-resort parse from HTML social count label.
        match = re.search(
            r'aria-label="([0-9,]+)\s+users?\s+starred\s+this\s+repository"',
            page.text,
            re.IGNORECASE,
        )
        if match:
            stars = int(match.group(1).replace(",", ""))

    if stars is None:
        return {"ok": False, "not_found": False, "error": f"stars_unavailable;{last_error}"}

    return {
        "ok": True,
        "not_found": False,
        "stars": stars,
        "full_name": f"{owner}/{repo}",
        "html_url": page_url,
        "description": "",
    }


def filter_github_entries_for_catalog(
    entries: list[dict[str, Any]],
    min_stars: int = MIN_GITHUB_STARS_FOR_CATALOG,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Keep papers; drop 404 GitHub repos and repos below min_stars.

    Prefer live GitHub stars. If the API is unavailable, fall back to stored
    stars when present; entries with neither live nor stored stars are dropped
    (cannot verify the >=50 threshold).
    """
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    for entry in entries:
        item_id = entry.get("id", "")
        if not item_id.startswith("github:"):
            kept.append(entry)
            continue
        owner_repo = github_owner_repo(entry.get("url", ""))
        if not owner_repo:
            parts = item_id.split(":", 1)[1].split("/", 1)
            if len(parts) != 2:
                dropped.append(f"{item_id} (bad id)")
                continue
            owner_repo = (parts[0], parts[1])

        meta = fetch_github_repo_meta(owner_repo[0], owner_repo[1])
        time.sleep(0.35)

        if meta.get("not_found"):
            dropped.append(f"{item_id} (not found)")
            continue

        entry = dict(entry)
        if meta.get("ok"):
            entry["stars"] = meta["stars"]
            stars = meta["stars"]
        elif entry.get("stars") is not None:
            stars = int(entry["stars"])
        else:
            dropped.append(f"{item_id} (unverified stars; {meta.get('error', 'no data')})")
            continue

        if stars < min_stars:
            dropped.append(f"{item_id} (stars={stars}<{min_stars})")
            continue
        kept.append(entry)
    return kept, dropped


def extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text)


def replace_marked_section(text: str, start: str, end: str, body: str) -> str:
    if start not in text or end not in text:
        raise ValueError(f"Missing markers {start} / {end}")
    pattern = re.compile(
        re.escape(start) + r".*?" + re.escape(end),
        re.DOTALL,
    )
    replacement = f"{start}\n{body.rstrip()}\n{end}"
    new_text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise ValueError(f"Failed to replace section {start}")
    return new_text


def get_marked_section(text: str, start: str, end: str) -> str:
    if start not in text or end not in text:
        return ""
    pattern = re.compile(
        re.escape(start) + r"(.*?)" + re.escape(end),
        re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def deepseek_chat(prompt: str, system: str = "You are an expert AI cybersecurity analyst.") -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")

    endpoint = "https://api.deepseek.com/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }

    last_error = None
    for attempt in range(3):
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=90)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            if resp.status_code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            last_error = f"HTTP {resp.status_code}: {resp.text[:500]}"
            time.sleep(10)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(10)
    raise RuntimeError(f"DeepSeek request failed: {last_error}")


def extract_json_payload(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def heuristic_category(name: str, description: str) -> str:
    """Fallback classifier when LLM is unavailable."""
    text = f"{name} {description}".lower()
    for_security_signals = [
        "pentest",
        "penetration",
        "honeypot",
        "threat detection",
        "vulnerability scanning",
        "vuln",
        "soc",
        "blue team",
        "defense agent",
        "security automation",
        "incident response",
        "recon",
        "cyber defense",
    ]
    of_agents_signals = [
        "prompt injection",
        "jailbreak",
        "agent safety",
        "agent security",
        "guardrail",
        "red team",
        "mcp attack",
        "tool poisoning",
        "exfiltration",
        "sandbox",
        "threat-rule",
        "owasp agent",
        "agentic security",
    ]
    for_score = sum(1 for s in for_security_signals if s in text)
    of_score = sum(1 for s in of_agents_signals if s in text)
    if for_score > of_score:
        return CATEGORY_AGENTS_FOR_SECURITY
    return CATEGORY_SECURITY_OF_AGENTS


def render_bullet(entry: dict[str, Any]) -> str:
    """Compact one-line bullet for This Week daily reports."""
    name = entry["name"]
    desc = entry.get("description", "").strip()
    url = entry["url"]
    if desc:
        return f"* **{name}** - {desc} {url}"
    return f"* **{name}** {url}"


def render_paper_entry(entry: dict[str, Any]) -> str:
    name = entry["name"].strip().strip('"')
    desc = entry.get("description", "").strip()
    url = entry["url"]
    month = format_month_label(entry.get("first_seen"))
    lines = [f'* [{month}] **"{name}"** [[paper]({url})]']
    if desc:
        lines.append(f"  > {desc}")
    return "\n".join(lines)


def render_repo_entry(entry: dict[str, Any]) -> str:
    name = entry["name"].strip()
    desc = entry.get("description", "").strip()
    url = entry["url"]
    owner_repo = github_owner_repo(url)
    if owner_repo:
        owner, repo = owner_repo
        safe_name = name.replace("]", "").replace("[", "")
        badge = f"![{safe_name} Stars](https://img.shields.io/github/stars/{owner}/{repo})"
        link = f"[{name}]({url})"
        if desc:
            return f"* {badge} {link} - {desc}"
        return f"* {badge} {link}"
    if desc:
        return f"* [{name}]({url}) - {desc}"
    return f"* [{name}]({url})"


def render_catalog_entry(entry: dict[str, Any]) -> str:
    entry_type = entry.get("type") or resolve_item_type(entry)
    if entry_type == TYPE_PAPER:
        return render_paper_entry(entry)
    return render_repo_entry(entry)


def sort_catalog_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Newest first_seen first.
    return sorted(
        entries,
        key=lambda e: (
            e.get("first_seen") or "0000-00-00",
            e.get("name", "").lower(),
        ),
        reverse=True,
    )


def parse_highlight_sections(text: str) -> dict[str, list[str]]:
    """Split highlights.md into resource-type bullet blocks (raw markdown lines)."""
    sections: dict[str, list[str]] = {
        TYPE_PAPER: [],
        TYPE_PROJECT: [],
        TYPE_BLOG: [],
        TYPE_BENCHMARK: [],
    }
    if not text.strip():
        return sections

    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer, current
        if current is None:
            buffer = []
            return
        # Keep original bullets; for blogs keep all non-header content lines as one block list
        if current == TYPE_BLOG:
            block = "\n".join(line for line in buffer if line.strip()).strip()
            if block:
                sections[current].append(block)
        else:
            item_lines: list[str] = []
            for line in buffer:
                if line.startswith("* "):
                    if item_lines:
                        sections[current].append("\n".join(item_lines).rstrip())
                    item_lines = [line]
                elif item_lines:
                    # continuation (e.g. wrapped blog/project lines)
                    item_lines.append(line)
            if item_lines:
                sections[current].append("\n".join(item_lines).rstrip())
        buffer = []

    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("## ") and "Research Papers" in stripped:
            flush()
            current = TYPE_PAPER
            continue
        if stripped.startswith("## ") and "Open-Source Projects" in stripped:
            flush()
            current = TYPE_PROJECT
            continue
        if stripped.startswith("## ") and "Technical Blogs" in stripped:
            flush()
            current = TYPE_BLOG
            continue
        if stripped.startswith("## ") and "Benchmarks" in stripped:
            flush()
            current = TYPE_BENCHMARK
            continue
        if current is None:
            continue
        if current != TYPE_BLOG and stripped.startswith(">"):
            continue
        buffer.append(raw.rstrip())
    flush()
    return sections


def classify_highlight_bullet(bullet: str) -> str:
    urls = extract_urls(bullet)
    name_match = re.search(r"\*\*([^*]+)\*\*", bullet) or re.search(r"\[([^\]]+)\]\(", bullet)
    name = name_match.group(1) if name_match else ""
    return heuristic_category(name, bullet)


def render_manual_items(items: list[str]) -> list[str]:
    lines: list[str] = []
    for item in items:
        if lines:
            lines.append("")
        lines.append(item.rstrip())
    return lines


def render_auto_items(entries: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for entry in sort_catalog_entries(entries):
        if lines:
            lines.append("")
        lines.append(render_catalog_entry(entry))
    return lines


def render_catalog_markdown(
    catalog: dict[str, Any],
    highlights_text: str | None = None,
) -> str:
    if highlights_text is None:
        highlights_text = HIGHLIGHTS_PATH.read_text(encoding="utf-8") if HIGHLIGHTS_PATH.exists() else ""
    manual = parse_highlight_sections(highlights_text)
    entries = catalog.get("entries", [])

    normalized = []
    for entry in entries:
        row = dict(entry)
        row["type"] = resolve_item_type(row)
        normalized.append(row)

    lines: list[str] = []
    for type_key, heading in RESOURCE_ORDER:
        lines.append(heading)
        lines.append("")

        if type_key == TYPE_PAPER:
            lines.append("> 📖 Papers collected from daily recommendations. Manual curated entries stay at the top.")
            lines.append("")
        if type_key == TYPE_BLOG:
            blog_items = manual.get(TYPE_BLOG, [])
            if blog_items:
                # blogs stored as one or more blocks; split into bullets with spacing
                blog_text = blog_items[0]
                blog_bullets = []
                current: list[str] = []
                for line in blog_text.splitlines():
                    if line.startswith("* "):
                        if current:
                            blog_bullets.append("\n".join(current).rstrip())
                        current = [line]
                    elif current:
                        current.append(line)
                if current:
                    blog_bullets.append("\n".join(current).rstrip())
                lines.extend(render_manual_items(blog_bullets))
            else:
                lines.append("*No entries yet.*")
            lines.append("")
            continue

        for category, label in CATEGORY_LABELS.items():
            lines.append(f"### {label}")
            lines.append("")

            manual_for_cat = [
                b for b in manual.get(type_key, []) if classify_highlight_bullet(b) == category
            ]
            auto_for_cat = [
                e for e in normalized if e.get("type") == type_key and e.get("category") == category
            ]

            section_lines: list[str] = []
            section_lines.extend(render_manual_items(manual_for_cat))
            auto_lines = render_auto_items(auto_for_cat)
            if section_lines and auto_lines:
                section_lines.append("")
            section_lines.extend(auto_lines)

            if not section_lines:
                lines.append("*No entries yet.*")
                lines.append("")
            else:
                lines.extend(section_lines)
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def intro_markdown() -> str:
    return """# An Awesome List for AI Security Agents

We curate an Awesome List of **AI security agents**, specifically addressing:

- **Agents for Security**: Research and tools using AI agents to enhance cybersecurity defenses
- **Security of Agents**: Techniques to protect AI agents themselves from adversarial attacks

**Curated resources** including:

🔬 *Research Papers* | 💻 *Open-Source Projects* | ✍️ *Technical Blogs* | 📂 *Benchmarks*

> Continuously updated with state-of-the-art developments in AI-powered security agents.
> Daily finds appear under **This Week**; Sunday rollup merges novel items into the sections below.
"""


def empty_weekly_body() -> str:
    return "_No updates yet this week._\n"
