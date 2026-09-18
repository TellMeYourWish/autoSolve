from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autosolve.browser_chat_provider import BrowserChatProvider
from autosolve.models import NormalizedQuestion


def main() -> None:
    provider = BrowserChatProvider(
        profile_dir=os.getenv("AUTOSOLVE_BROWSER_PROFILE", "browser-profile"),
        headless=False,
        login_timeout=float(os.getenv("AUTOSOLVE_LOGIN_TIMEOUT", "300")),
    )
    try:
        print("已打开有头浏览器。请在窗口中手动登录 chat.deepseek.com。")
        print("不会读取或保存密码、验证码；登录态只由 Playwright 保存在 browser-profile。")
        result = provider.solve(NormalizedQuestion(
            question="1 + 1 等于多少？",
            question_type=0,
            options=["1", "2", "3"],
        ))
        print({
            "answer": result.answer,
            "confidence": result.confidence,
            "explanation": result.explanation,
        })
    finally:
        provider.close()


if __name__ == "__main__":
    main()
