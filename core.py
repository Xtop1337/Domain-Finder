"""core.py — search logic for domain_finder.

Provides a single entry point `search(keyword, sources, progress_callback)`
that resolves a keyword to base domains, then enumerates subdomains via
crt.sh and HackerTarget. Returns a dict with domains, stats, and logs.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import quote

import requests

CRT_SH_URL = "https://crt.sh/?q={q}&output=json"
HACKERTARGET_URL = "https://api.hackertarget.com/hostsearch/?q={q}"
TIMEOUT = 15
USER_AGENT = "domain-finder/1.0 (+local)"

DATA_DIR = Path(__file__).parent
KNOWN_SITES_PATH = DATA_DIR / "known_sites.json"
RESULTS_DIR = DATA_DIR / "results"


def load_known_sites() -> dict[str, list[str]]:
    if not KNOWN_SITES_PATH.exists():
        return {}
    try:
        with KNOWN_SITES_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_keyword(keyword: str) -> list[str]:
    """If `keyword` looks like a domain — return as-is.
    Otherwise look it up in known_sites.json.
    """
    keyword = keyword.strip().lower()
    if not keyword:
        return []

    if "." in keyword and re.match(r"^[a-z0-9.-]+$", keyword):
        return [keyword]

    sites = load_known_sites()
    if keyword in sites:
        return list(sites[keyword])

    for key, domains in sites.items():
        if key in keyword or keyword in key:
            return list(domains)

    return []


def _is_valid_domain(value: str) -> bool:
    value = value.strip().lower().lstrip("*.")
    if not value or "." not in value:
        return False
    if " " in value or "\n" in value:
        return False
    if value.startswith(".") or value.endswith("."):
        return False
    return bool(re.match(r"^[a-z0-9.\-_]{1,253}$", value))


def _clean(raw: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for item in raw:
        if not item:
            continue
        for part in str(item).split("\n"):
            d = part.strip().lower().lstrip("*.")
            if _is_valid_domain(d):
                out.add(d)
    return out


def _query_crtsh(domain: str) -> tuple[set[str], str | None]:
    url = CRT_SH_URL.format(q=quote(f"%.{domain}"))
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        return set(), f"network error: {exc}"
    if resp.status_code != 200:
        return set(), f"HTTP {resp.status_code}"
    try:
        data = resp.json()
    except json.JSONDecodeError:
        return set(), "invalid JSON"
    raw_values: list[str] = []
    for entry in data:
        nv = entry.get("name_value") or entry.get("common_name")
        if nv:
            raw_values.append(nv)
    return _clean(raw_values), None


def _query_hackertarget(domain: str) -> tuple[set[str], str | None]:
    url = HACKERTARGET_URL.format(q=quote(domain))
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        return set(), f"network error: {exc}"
    if resp.status_code == 429:
        return set(), "rate-limited (HTTP 429)"
    if resp.status_code != 200:
        return set(), f"HTTP {resp.status_code}"
    text = resp.text or ""
    if "API count" in text and "exceeded" in text.lower():
        return set(), "rate-limited"
    raw_values: list[str] = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if row:
            raw_values.append(row[0])
    return _clean(raw_values), None


def _ensure_results_dir() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)


def save_json(keyword: str, payload: dict) -> Path:
    _ensure_results_dir()
    safe = re.sub(r"[^a-z0-9._-]+", "_", keyword.lower()) or "result"
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = RESULTS_DIR / f"{safe}_{ts}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def search(
    keyword: str,
    sources: list[str],
    progress_callback: Callable[[str, str, int], None] | None = None,
) -> dict:
    """Run the full search pipeline.

    progress_callback(message: str, level: str, percent: int) is invoked
    for status updates. `level` is one of: info, ok, warn, error.
    """

    def emit(msg: str, level: str = "info", pct: int = -1) -> None:
        if progress_callback:
            try:
                progress_callback(msg, level, pct)
            except Exception:
                pass

    started = time.time()
    timestamp = datetime.now().isoformat(timespec="seconds")

    emit(f"Resolving keyword: {keyword}", "info", 5)
    base_domains = resolve_keyword(keyword)
    if not base_domains:
        emit(
            f"Keyword '{keyword}' not found in known_sites.json. "
            f"Add it or pass a full domain (e.g. example.com).",
            "error",
            100,
        )
        return {
            "keyword": keyword,
            "resolved": [],
            "timestamp": timestamp,
            "duration_seconds": round(time.time() - started, 2),
            "sources": {},
            "total_unique": 0,
            "domains": [],
            "logs": [],
            "error": "unknown_keyword",
        }

    emit(f"Resolved to base domains: {', '.join(base_domains)}", "ok", 10)

    all_domains: dict[str, set[str]] = {}
    stats: dict[str, dict] = {}
    log_lines: list[tuple[str, str]] = []
    log_lines.append(("info", f"Keyword '{keyword}' → {', '.join(base_domains)}"))

    total_steps = max(1, len(base_domains) * len(sources))
    step = 0
    base_pct = 15
    pct_range = 80  # 15 -> 95

    for base in base_domains:
        if "crt.sh" in sources:
            step += 1
            pct = base_pct + int(pct_range * step / total_steps)
            emit(f"Querying crt.sh for *.{base} ...", "info", pct)
            found, err = _query_crtsh(base)
            if err:
                emit(f"crt.sh failed for {base}: {err}", "warn", pct)
                log_lines.append(("warn", f"crt.sh({base}): {err}"))
                stats.setdefault("crt.sh", {"count": 0, "status": "error", "error": err})
            else:
                emit(f"crt.sh returned {len(found)} subdomains for {base}", "ok", pct)
                log_lines.append(("ok", f"crt.sh({base}): {len(found)} subdomains"))
                existing = stats.setdefault("crt.sh", {"count": 0, "status": "ok"})
                existing["count"] = existing.get("count", 0) + len(found)
                for d in found:
                    all_domains.setdefault(d, set()).add("crt.sh")

        if "hackertarget" in sources:
            step += 1
            pct = base_pct + int(pct_range * step / total_steps)
            emit(f"Querying HackerTarget for {base} ...", "info", pct)
            found, err = _query_hackertarget(base)
            if err:
                emit(f"HackerTarget failed for {base}: {err}", "warn", pct)
                log_lines.append(("warn", f"hackertarget({base}): {err}"))
                stats.setdefault("hackertarget", {"count": 0, "status": "error", "error": err})
            else:
                emit(f"HackerTarget returned {len(found)} hosts for {base}", "ok", pct)
                log_lines.append(("ok", f"hackertarget({base}): {len(found)} hosts"))
                existing = stats.setdefault("hackertarget", {"count": 0, "status": "ok"})
                existing["count"] = existing.get("count", 0) + len(found)
                for d in found:
                    all_domains.setdefault(d, set()).add("hackertarget")

    merged: list[dict] = []
    for d, srcs in all_domains.items():
        merged.append({"domain": d, "sources": sorted(srcs)})
    merged.sort(key=lambda x: x["domain"])

    duration = round(time.time() - started, 2)
    emit(f"Done. Total unique domains: {len(merged)} ({duration}s)", "ok", 100)

    return {
        "keyword": keyword,
        "resolved": base_domains,
        "timestamp": timestamp,
        "duration_seconds": duration,
        "sources": stats,
        "total_unique": len(merged),
        "domains": merged,
        "logs": log_lines,
    }
