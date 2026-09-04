"""core.py — search logic for domain_finder.

Provides a single entry point `search(keyword, sources, progress_callback)`
that resolves a keyword to base domains, then enumerates subdomains via
crt.sh and HackerTarget. Returns a dict with domains, stats, and logs.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import quote, urlsplit

import requests

CRT_SH_URL = "https://crt.sh/?q={q}&output=json"
HACKERTARGET_URL = "https://api.hackertarget.com/hostsearch/?q={q}"
TIMEOUT = 15
USER_AGENT = "domain-finder/1.0 (+local)"

DATA_DIR = Path(__file__).parent
KNOWN_SITES_PATH = DATA_DIR / "known_sites.json"
APP_NAME = "Domain-Finder"


def _get_results_dir() -> Path:
    """Return a persistent, per-user directory for exported search results."""
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            base_dir = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            if base_dir:
                return Path(base_dir) / APP_NAME / "results"
        return Path.home() / ".local" / "share" / APP_NAME / "results"

    return DATA_DIR / "results"


RESULTS_DIR = _get_results_dir()
SUPPORTED_SOURCES = ("crt.sh", "hackertarget")


def load_known_sites() -> dict[str, list[str]]:
    if not KNOWN_SITES_PATH.exists():
        return {}
    try:
        with KNOWN_SITES_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _normalize_domain_input(value: str) -> str:
    """Extract and normalize a hostname from domain-like user input."""
    value = str(value or "").strip().lower()
    if not value:
        return ""

    if "://" in value or value.startswith("//"):
        parsed = urlsplit(value if "://" in value else f"https:{value}")
        host = parsed.hostname or ""
    else:
        candidate = value.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if "@" in candidate:
            candidate = candidate.rsplit("@", 1)[-1]
        parsed = urlsplit(f"//{candidate}")
        host = parsed.hostname or candidate

    while host.startswith("*."):
        host = host[2:]
    host = host.strip(".")

    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""


def _unique_valid_domains(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        domain = _normalize_domain_input(value)
        if domain in seen or not _is_valid_domain(domain):
            continue
        seen.add(domain)
        out.append(domain)
    return out


def resolve_keyword(keyword: str) -> list[str]:
    """Resolve a known keyword or validated domain-like input to base domains."""
    raw_keyword = str(keyword or "").strip()
    keyword = raw_keyword.lower()
    if not keyword:
        return []

    domain = _normalize_domain_input(raw_keyword)
    if _is_valid_domain(domain):
        return [domain]

    sites = load_known_sites()
    normalized_sites = {k.lower(): v for k, v in sites.items()}
    if keyword in normalized_sites:
        return _unique_valid_domains(normalized_sites[keyword])

    for key, domains in normalized_sites.items():
        if key in keyword or keyword in key:
            return _unique_valid_domains(domains)

    return []


def _is_valid_domain(value: str) -> bool:
    value = _normalize_domain_input(value)
    if not value or "." not in value:
        return False
    if len(value) > 253 or ".." in value:
        return False
    labels = value.split(".")
    return all(
        0 < len(label) <= 63
        and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    )


def _clean(raw: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for item in raw:
        if not item:
            continue
        for part in str(item).split("\n"):
            d = _normalize_domain_input(part)
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
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


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
    keyword = str(keyword or "").strip()
    selected_sources = [
        source
        for source in dict.fromkeys(sources or [])
        if source in SUPPORTED_SOURCES
    ]

    def build_payload(
        resolved: list[str],
        stats: dict[str, dict],
        domains: list[dict],
        logs: list[tuple[str, str]],
    ) -> dict:
        return {
            "keyword": keyword,
            "resolved": resolved,
            "timestamp": timestamp,
            "duration_seconds": round(time.time() - started, 2),
            "sources": stats,
            "total_unique": len(domains),
            "domains": domains,
            "logs": logs,
        }

    if not keyword:
        msg = "Empty keyword; nothing to search."
        emit(msg, "warn", 100)
        return build_payload([], {}, [], [("warn", msg)])

    if not selected_sources:
        msg = "No supported sources selected."
        emit(msg, "warn", 100)
        return build_payload([], {}, [], [("warn", msg)])

    emit(f"Resolving keyword: {keyword}", "info", 5)
    base_domains = resolve_keyword(keyword)
    if not base_domains:
        msg = f"No valid base domains resolved for keyword: {keyword}"
        emit(msg, "warn", 100)
        return build_payload([], {}, [], [("warn", msg)])

    emit(f"Resolved to base domains: {', '.join(base_domains)}", "ok", 10)

    all_domains: dict[str, set[str]] = {}
    stats: dict[str, dict] = {}
    source_successes: dict[str, int] = {}
    log_lines: list[tuple[str, str]] = []
    log_lines.append(("info", f"Keyword '{keyword}' -> {', '.join(base_domains)}"))

    total_steps = max(1, len(base_domains) * len(selected_sources))
    step = 0
    base_pct = 15
    pct_range = 80  # 15 -> 95

    def record_result(source: str, base: str, found: set[str], err: str | None) -> None:
        entry = stats.setdefault(source, {"count": 0, "status": "ok", "errors": []})
        if err:
            error = f"{base}: {err}"
            entry["errors"].append(error)
            entry.setdefault("error", error)
            return

        source_successes[source] = source_successes.get(source, 0) + 1
        entry["count"] = entry.get("count", 0) + len(found)
        for domain in found:
            all_domains.setdefault(domain, set()).add(source)

    for base in base_domains:
        if "crt.sh" in selected_sources:
            step += 1
            pct = base_pct + int(pct_range * step / total_steps)
            emit(f"Querying crt.sh for *.{base} ...", "info", pct)
            found, err = _query_crtsh(base)
            if err:
                emit(f"crt.sh failed for {base}: {err}", "warn", pct)
                log_lines.append(("warn", f"crt.sh({base}): {err}"))
                record_result("crt.sh", base, found, err)
            else:
                emit(f"crt.sh returned {len(found)} subdomains for {base}", "ok", pct)
                log_lines.append(("ok", f"crt.sh({base}): {len(found)} subdomains"))
                record_result("crt.sh", base, found, None)

        if "hackertarget" in selected_sources:
            step += 1
            pct = base_pct + int(pct_range * step / total_steps)
            emit(f"Querying HackerTarget for {base} ...", "info", pct)
            found, err = _query_hackertarget(base)
            if err:
                emit(f"HackerTarget failed for {base}: {err}", "warn", pct)
                log_lines.append(("warn", f"hackertarget({base}): {err}"))
                record_result("hackertarget", base, found, err)
            else:
                emit(f"HackerTarget returned {len(found)} hosts for {base}", "ok", pct)
                log_lines.append(("ok", f"hackertarget({base}): {len(found)} hosts"))
                record_result("hackertarget", base, found, None)

    merged: list[dict] = []
    for d, srcs in all_domains.items():
        merged.append({"domain": d, "sources": sorted(srcs)})
    merged.sort(key=lambda x: x["domain"])

    for source, entry in stats.items():
        errors = entry.get("errors", [])
        successes = source_successes.get(source, 0)
        if errors and successes:
            entry["status"] = "partial"
        elif errors:
            entry["status"] = "error"
        else:
            entry["status"] = "ok"

    duration = round(time.time() - started, 2)
    emit(f"Done. Total unique domains: {len(merged)} ({duration}s)", "ok", 100)
    return build_payload(base_domains, stats, merged, log_lines)
