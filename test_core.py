import json

import pytest

import core


def test_get_known_sites_path_uses_source_directory_when_not_frozen(monkeypatch, tmp_path):
    source_file = tmp_path / "core.py"
    known_sites_file = tmp_path / "known_sites.json"
    known_sites_file.write_text('{"source": ["source.example"]}', encoding="utf-8")
    monkeypatch.setattr(core, "__file__", str(source_file))
    monkeypatch.delattr(core.sys, "_MEIPASS", raising=False)

    assert core.get_known_sites_path() == known_sites_file
    assert core.load_known_sites() == {"source": ["source.example"]}


def test_get_known_sites_path_uses_pyinstaller_bundle_when_frozen(monkeypatch, tmp_path):
    bundle_dir = tmp_path / "_MEI12345"
    monkeypatch.setattr(core.sys, "_MEIPASS", str(bundle_dir), raising=False)

    assert core.get_known_sites_path() == bundle_dir / "known_sites.json"


def test_load_known_sites_reads_pyinstaller_bundle_file(monkeypatch, tmp_path):
    bundle_dir = tmp_path / "_MEI12345"
    bundle_dir.mkdir()
    (bundle_dir / "known_sites.json").write_text(
        '{"example": ["example.com"]}', encoding="utf-8"
    )
    monkeypatch.setattr(core.sys, "_MEIPASS", str(bundle_dir), raising=False)

    assert core.load_known_sites() == {"example": ["example.com"]}


def test_results_dir_uses_localappdata_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(core.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

    assert core.get_results_dir() == (
        tmp_path / "AppData" / "Local" / "Domain Finder" / "results"
    )


def test_results_dir_falls_back_to_home_and_is_created(monkeypatch, tmp_path):
    results_dir = tmp_path / "Domain Finder" / "results"
    monkeypatch.setattr(core.sys, "platform", "linux")
    monkeypatch.setattr(core.Path, "home", lambda: tmp_path)

    assert core._ensure_results_dir() == results_dir
    assert results_dir.is_dir()


def test_save_json_uses_the_configured_results_directory(monkeypatch, tmp_path):
    results_dir = tmp_path / "results"
    monkeypatch.setattr(core, "get_results_dir", lambda: results_dir)

    saved_path = core.save_json("Example Site", {"domains": ["example.com"]})

    assert saved_path.parent == results_dir
    assert json.loads(saved_path.read_text(encoding="utf-8")) == {
        "domains": ["example.com"]
    }


def test_resolve_keyword_normalizes_domain_like_input():
    assert core.resolve_keyword("https://Example.com/path?q=1") == ["example.com"]
    assert core.resolve_keyword("*.Example.com") == ["example.com"]
    assert core.resolve_keyword("EXAMPLE.COM.") == ["example.com"]


@pytest.mark.parametrize(
    "value",
    [
        "bad_domain.com",
        "a..b.com",
        "-a.example.com",
        "a-.example.com",
        f"{'a' * 64}.example.com",
    ],
)
def test_invalid_domains_are_rejected(value):
    assert not core._is_valid_domain(value)
    assert core.resolve_keyword(value) == []


def test_clean_deduplicates_normalizes_and_filters_garbage():
    raw = [
        "*.API.Example.com\nwww.example.com",
        "api.example.com",
        "bad_domain.com",
        "a..example.com",
        "-broken.example.com",
    ]

    assert core._clean(raw) == {"api.example.com", "www.example.com"}


def test_search_empty_keyword_does_not_call_sources(monkeypatch):
    def fail_query(domain):
        raise AssertionError(f"unexpected network query for {domain}")

    monkeypatch.setattr(core, "_query_crtsh", fail_query)
    monkeypatch.setattr(core, "_query_hackertarget", fail_query)

    events = []
    payload = core.search("", ["crt.sh"], lambda *event: events.append(event))

    assert payload["total_unique"] == 0
    assert payload["domains"] == []
    assert payload["logs"][0][0] == "warn"
    assert not any(message.startswith("Done.") for message, _level, _pct in events)


def test_search_empty_sources_does_not_call_sources(monkeypatch):
    def fail_query(domain):
        raise AssertionError(f"unexpected network query for {domain}")

    monkeypatch.setattr(core, "_query_crtsh", fail_query)
    monkeypatch.setattr(core, "_query_hackertarget", fail_query)

    events = []
    payload = core.search("example.com", [], lambda *event: events.append(event))

    assert payload["total_unique"] == 0
    assert payload["domains"] == []
    assert payload["logs"][0][0] == "warn"
    assert not any(message.startswith("Done.") for message, _level, _pct in events)


def test_search_marks_source_partial_when_error_precedes_success(monkeypatch):
    monkeypatch.setattr(
        core,
        "resolve_keyword",
        lambda _keyword: ["bad.example.com", "good.example.com"],
    )

    def fake_crtsh(domain):
        if domain == "bad.example.com":
            return set(), "boom"
        return {"api.good.example.com"}, None

    monkeypatch.setattr(core, "_query_crtsh", fake_crtsh)

    payload = core.search("brand", ["crt.sh"])
    stats = payload["sources"]["crt.sh"]

    assert payload["total_unique"] == 1
    assert payload["domains"] == [
        {"domain": "api.good.example.com", "sources": ["crt.sh"]}
    ]
    assert stats["count"] == 1
    assert stats["status"] == "partial"
    assert stats["errors"] == ["bad.example.com: boom"]
    assert stats["error"] == "bad.example.com: boom"
