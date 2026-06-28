import pytest

import core


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
