from autosolve.browser_chat_provider import (
    ASSISTANT_CONTENT_SELECTOR,
    NEW_SESSION_ICON_SELECTOR,
    RESPONSE_TRIGGER_SELECTOR,
    VISIBLE_ITEMS_SELECTOR,
    BrowserChatProvider,
)
from autosolve.models import NormalizedQuestion, Solution


def test_browser_provider_keeps_session_configuration(tmp_path):
    provider = BrowserChatProvider(tmp_path / "profile", headless=False, login_timeout=12)
    assert provider.headless is False
    assert provider.profile_dir == tmp_path / "profile"
    assert provider.login_timeout == 12


def test_diagnostics_does_not_expose_browser_credentials(tmp_path):
    provider = BrowserChatProvider(tmp_path / "profile", headless=False)
    diagnostics = provider.diagnostics()
    assert diagnostics["provider"] == "BrowserChatProvider"
    assert "cookie" not in str(diagnostics).lower()
    assert "password" not in str(diagnostics).lower()


def test_answer_container_selector_targets_requested_dom():
    assert RESPONSE_TRIGGER_SELECTOR == ".ds-flex._0a3d93b"
    assert VISIBLE_ITEMS_SELECTOR == ".ds-virtual-list-visible-items"
    assert ASSISTANT_CONTENT_SELECTOR == ".ds-markdown.ds-assistant-message-main-content"
    assert NEW_SESSION_ICON_SELECTOR == ".ds-icon._1c42ad7"


def test_read_latest_answer_waits_for_last_item_to_finish(tmp_path):
    provider = BrowserChatProvider(tmp_path / "profile", response_timeout=1)
    snapshots = iter([
        {"answer": "old", "answer_count": 1, "response_finished": True},
        {"answer": '{"answer":"', "answer_count": 2, "response_finished": False},
        {"answer": "not-json", "answer_count": 2, "response_finished": True},
    ])
    provider._dom_snapshot = lambda: next(snapshots)
    provider._page = type("Page", (), {"wait_for_timeout": lambda self, _: None})()

    result = provider._read_latest_answer(1, "old")

    assert result == "not-json"


def test_browser_provider_recovers_once_from_closed_target(tmp_path):
    provider = BrowserChatProvider(tmp_path / "profile")
    calls = {"ensure": 0, "solve": 0, "reset": 0}

    def ensure_browser():
        calls["ensure"] += 1

    def solve_current(_question):
        calls["solve"] += 1
        if calls["solve"] == 1:
            raise RuntimeError("Target page, context or browser has been closed")
        return Solution(answer="2", confidence=1.0)

    def reset_browser():
        calls["reset"] += 1
        provider._active_session_id = None

    provider._ensure_browser = ensure_browser
    provider._ensure_session = lambda _session_id: None
    provider._solve_in_current_browser = solve_current
    provider._reset_browser = reset_browser

    result = provider.solve(NormalizedQuestion("1+1=?", None, []))

    assert result.answer == "2"
    assert calls == {"ensure": 2, "solve": 2, "reset": 1}


def test_browser_provider_does_not_retry_unrelated_errors(tmp_path):
    provider = BrowserChatProvider(tmp_path / "profile")
    assert provider._is_stale_browser_error(RuntimeError("network failed")) is False
