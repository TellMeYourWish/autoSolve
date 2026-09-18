from __future__ import annotations

import os
import threading
import time
import logging
from pathlib import Path
from typing import Any

from .deepseek_provider import build_prompt, parse_solution
from .models import NormalizedQuestion, Solution
from .providers import SolverProvider

logger = logging.getLogger(__name__)
VISIBLE_ITEMS_SELECTOR = ".ds-virtual-list-visible-items"
ASSISTANT_CONTENT_SELECTOR = ".ds-markdown.ds-assistant-message-main-content"
RESPONSE_TRIGGER_SELECTOR = ".ds-flex._0a3d93b"
NEW_SESSION_ICON_SELECTOR = ".ds-icon._1c42ad7"


class BrowserChatProvider(SolverProvider):
    """使用 chat.deepseek.com 网页端的持久化浏览器会话。

    首次使用时只打开登录页并等待用户手动完成登录；本类不填写密码、验证码，
    也不读取 Cookie。Playwright 的 persistent context 会在 profile 目录保存会话。
    """

    def __init__(
        self,
        profile_dir: str | Path = "browser-profile",
        headless: bool = False,
        login_timeout: float = 300,
        response_timeout: float = 90,
        launch_url: str = "https://chat.deepseek.com/",
        debug_dir: str | Path = "debug-artifacts",
    ) -> None:
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self.login_timeout = login_timeout
        self.response_timeout = response_timeout
        self.launch_url = launch_url
        self.debug_dir = Path(debug_dir)
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._lock = threading.RLock()
        self._request_count = 0
        self._last_event = "created"
        self._last_error: str | None = None
        self._last_request_id: int | None = None
        self._last_started_at: float | None = None
        self._last_finished_at: float | None = None
        self._playwright_thread_id: int | None = None
        self._active_session_id: str | None = None

    def solve(self, question: NormalizedQuestion) -> Solution:
        with self._lock:
            current_thread_id = threading.get_ident()
            if self._playwright_thread_id is not None and self._playwright_thread_id != current_thread_id:
                raise RuntimeError(
                    "Playwright 浏览器会话跨线程复用。请使用 threaded=False 启动 Flask，"
                    "并重启服务以清理旧浏览器会话。"
                )
            self._request_count += 1
            self._last_request_id = self._request_count
            self._last_started_at = time.time()
            self._last_error = None
            try:
                for browser_attempt in range(2):
                    try:
                        self._set_event("starting_browser")
                        self._ensure_browser()
                        self._ensure_session(question.session_id)
                        return self._solve_in_current_browser(question)
                    except Exception as exc:
                        if browser_attempt == 0 and self._is_stale_browser_error(exc):
                            self._set_event("stale_browser_recovering")
                            self._reset_browser()
                            continue
                        raise
                raise RuntimeError("网页端未返回可解析答案")
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._set_event("error")
                self._capture_debug_artifact("error")
                logger.exception("browser solve failed, request_id=%s", self._last_request_id)
                raise
            finally:
                self._last_finished_at = time.time()

    def close(self) -> None:
        with self._lock:
            self._reset_browser()
            self._set_event("closed")

    def _solve_in_current_browser(self, question: NormalizedQuestion) -> Solution:
        prompt = build_prompt(question)
        for attempt in range(2):
            answer_baseline, answer_baseline_text = self._answer_snapshot()
            self._send_prompt(prompt, repair=attempt > 0)
            raw = self._read_latest_answer(
                answer_baseline,
                answer_baseline_text,
            )
            try:
                result = parse_solution(raw)
                self._set_event("answer_parsed")
                return result
            except ValueError:
                self._set_event("invalid_answer_format_retry")
                if attempt == 1:
                    raise
        raise RuntimeError("网页端未返回可解析答案")

    @staticmethod
    def _is_stale_browser_error(exc: Exception) -> bool:
        name = type(exc).__name__.lower()
        message = str(exc).lower()
        return "targetclosed" in name or any(
            marker in message
            for marker in (
                "target page, context or browser has been closed",
                "browser has been closed",
                "context has been closed",
                "page has been closed",
            )
        )

    def _reset_browser(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                logger.debug("browser context was already closed", exc_info=True)
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                logger.debug("playwright was already stopped", exc_info=True)
        self._context = None
        self._playwright = None
        self._page = None
        self._playwright_thread_id = None
        self._active_session_id = None

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "provider": type(self).__name__,
                "browser_started": self._context is not None,
                "page_closed": self._page is None or self._page.is_closed(),
                "page_url": self._page.url if self._page is not None and not self._page.is_closed() else None,
                "headless": self.headless,
                "playwright_thread_id": self._playwright_thread_id,
                "current_thread_id": threading.get_ident(),
                "active_session_id": self._active_session_id,
                "profile_dir": str(self.profile_dir.resolve()),
                "request_count": self._request_count,
                "last_request_id": self._last_request_id,
                "last_event": self._last_event,
                "last_error": self._last_error,
                "last_started_at": self._last_started_at,
                "last_finished_at": self._last_finished_at,
            }

    def _set_event(self, event: str) -> None:
        self._last_event = event
        logger.info("browser provider event=%s request_id=%s", event, self._last_request_id)

    def _ensure_session(self, session_id: str | None) -> None:
        target = session_id or "default"
        if self._active_session_id is None:
            self._active_session_id = target
            self._set_event("session_initialized")
            return
        if target == self._active_session_id:
            return
        self._set_event("session_switching")
        self._start_new_session()
        self._active_session_id = target
        self._set_event("session_switched")

    def _start_new_session(self) -> None:
        icons = self._page.locator(NEW_SESSION_ICON_SELECTOR)
        if icons.count() == 0:
            raise RuntimeError("未找到新会话按钮图标 .ds-icon._1c42ad7")
        icon = icons.last
        if not icon.is_visible():
            raise RuntimeError("新会话按钮图标不可见: .ds-icon._1c42ad7")

        candidates = [
            icon,
            icon.locator("xpath=ancestor-or-self::button[1]"),
            icon.locator("xpath=ancestor-or-self::*[@role='button'][1]"),
            icon.locator("xpath=.."),
        ]
        clicked = False
        for candidate in candidates:
            try:
                if candidate.count() and candidate.is_visible() and candidate.is_enabled():
                    candidate.click(timeout=3000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            raise RuntimeError("找到新会话图标但无法点击: .ds-icon._1c42ad7")
        self._page.wait_for_timeout(500)
        logger.info("new session clicked selector=%s", NEW_SESSION_ICON_SELECTOR)

    def _ensure_browser(self) -> None:
        if self._page is not None and not self._page.is_closed():
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("未安装 Playwright，请安装依赖并执行 playwright install chromium") from exc

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        self._playwright_thread_id = threading.get_ident()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir.resolve()),
            headless=self.headless,
            viewport={"width": 1440, "height": 900},
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._set_event("browser_launched")
        self._page.goto(self.launch_url, wait_until="domcontentloaded")
        self._set_event("page_loaded")
        self._wait_until_logged_in()

    def _wait_until_logged_in(self) -> None:
        deadline = time.monotonic() + self.login_timeout
        while time.monotonic() < deadline:
            if self._looks_logged_in():
                self._set_event("logged_in")
                return
            if self.headless:
                raise RuntimeError("浏览器会话未登录；首次登录必须使用有头模式")
            self._page.wait_for_timeout(1000)
        raise TimeoutError("等待手动登录超时，请重新启动服务")

    def _looks_logged_in(self) -> bool:
        url = self._page.url.lower()
        if "login" in url or "signin" in url:
            return False
        login_text = self._page.get_by_text("登录", exact=True)
        for index in range(min(login_text.count(), 5)):
            if login_text.nth(index).is_visible():
                return False
        return self._find_input() is not None

    def _answer_snapshot(self) -> tuple[int, str]:
        snapshot = self._dom_snapshot()
        return snapshot["answer_count"], snapshot["answer"]

    def _dom_snapshot(self) -> dict[str, Any]:
        """读取可见列表的最后一项及其回答状态。"""
        return self._page.evaluate(
            """
            ({listSelector, answerSelector, triggerSelector}) => {
                const list = document.querySelector(listSelector);
                const lastItem = list?.lastElementChild;
                const answer = lastItem?.matches(answerSelector)
                    ? lastItem
                    : lastItem?.querySelector(answerSelector);
                return {
                    answer: (answer?.innerText || answer?.textContent || '').trim(),
                    answer_count: list
                        ? list.querySelectorAll(answerSelector).length
                        : 0,
                    response_finished: Boolean(lastItem?.querySelector(triggerSelector)),
                };
            }
            """,
            {
                "listSelector": VISIBLE_ITEMS_SELECTOR,
                "triggerSelector": RESPONSE_TRIGGER_SELECTOR,
                "answerSelector": ASSISTANT_CONTENT_SELECTOR,
            },
        )

    def _find_input(self) -> Any:
        selectors = [
            "textarea",
            "[contenteditable='true']",
            "textarea[placeholder*='消息']",
            "textarea[placeholder*='输入']",
        ]
        for selector in selectors:
            locator = self._page.locator(selector).last
            if locator.count() > 0 and locator.is_visible():
                return locator
        return None

    def _send_prompt(self, prompt: str, repair: bool = False) -> None:
        if repair:
            prompt += "\n上一次输出格式不合格。请只返回合法 JSON，不要 Markdown 代码块。"
        input_box = self._find_input()
        if input_box is None:
            raise RuntimeError("未找到 DeepSeek 聊天输入框")
        input_box.fill(prompt)
        self._set_event("prompt_filled")
        send = self._page.get_by_role("button", name="发送")
        if send.count() == 0:
            send = self._page.locator("button[type='submit']").last
        if send.count() > 0 and send.is_visible():
            send.click()
        else:
            input_box.press("Enter")
        self._set_event("prompt_sent")

    def _read_latest_answer(
        self,
        answer_baseline_count: int = 0,
        answer_baseline_text: str = "",
    ) -> str:
        deadline = time.monotonic() + self.response_timeout
        previous = answer_baseline_text
        last_count = answer_baseline_count
        last_length = len(answer_baseline_text)
        last_log_at = 0.0
        while time.monotonic() < deadline:
            snapshot = self._dom_snapshot()
            text = snapshot["answer"]
            count = snapshot["answer_count"]
            is_new_answer = count > answer_baseline_count or text != answer_baseline_text
            if is_new_answer and text:
                last_count = count
                last_length = len(text)
                previous = text
                if snapshot["response_finished"]:
                    self._set_event("answer_dom_detected")
                    logger.info(
                        "answer response finished selector=%s count=%s length=%s",
                        ASSISTANT_CONTENT_SELECTOR,
                        count,
                        len(text),
                    )
                    return text
            now = time.monotonic()
            if now - last_log_at >= 2:
                last_log_at = now
                logger.info(
                    "dom poll response_finished=%s answer_count=%s current_length=%s last_length=%s",
                    snapshot["response_finished"],
                    count,
                    len(text),
                    last_length,
                )
            self._page.wait_for_timeout(100)
        logger.warning(
            "response timeout answer_selector=%s answer_count=%s last_length=%s preview=%r",
            ASSISTANT_CONTENT_SELECTOR,
            last_count,
            last_length,
            previous[:120],
        )
        raise TimeoutError("等待 DeepSeek 网页回复超时")

    def _capture_debug_artifact(self, stage: str) -> None:
        if os.getenv("AUTOSOLVE_CAPTURE_DEBUG", "false").lower() != "true":
            return
        if self._page is None or self._page.is_closed():
            return
        try:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            filename = self.debug_dir / f"request-{self._last_request_id or 'unknown'}-{stage}.png"
            self._page.screenshot(path=str(filename), full_page=True)
            logger.info("debug screenshot saved: %s", filename)
        except Exception:
            logger.exception("failed to save debug screenshot")

_default_provider: BrowserChatProvider | None = None
_default_lock = threading.Lock()


def get_browser_provider() -> BrowserChatProvider:
    global _default_provider
    with _default_lock:
        if _default_provider is None:
            profile = os.getenv("AUTOSOLVE_BROWSER_PROFILE", "browser-profile")
            headless = os.getenv("AUTOSOLVE_BROWSER_HEADLESS", "false").lower() == "true"
            timeout = float(os.getenv("AUTOSOLVE_LOGIN_TIMEOUT", "300"))
            _default_provider = BrowserChatProvider(profile, headless, timeout)
        return _default_provider
