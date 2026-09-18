from __future__ import annotations

import os
import logging

from flask import Flask, jsonify

from autosolve.logging_config import configure_logging
from autosolve.api import build_api_blueprint
from autosolve.browser_chat_provider import get_browser_provider
from autosolve.deepseek_provider import DeepSeekApiProvider
from autosolve.providers import NullSolverProvider
from autosolve.services import SolverService

LOG_PATH = configure_logging()


def create_app(provider=None) -> Flask:
    """创建 Flask 应用；测试时可注入自定义 provider。"""
    app = Flask(__name__)
    if provider is None:
        provider_mode = os.getenv("AUTOSOLVE_PROVIDER", "browser").lower()
        if provider_mode == "browser":
            provider = get_browser_provider()
        elif provider_mode == "deepseek":
            provider = DeepSeekApiProvider(os.getenv("DEEPSEEK_API_KEY", ""))
        elif provider_mode == "disabled":
            provider = NullSolverProvider()
        else:
            raise ValueError(
                "AUTOSOLVE_PROVIDER must be browser, deepseek, or disabled"
            )
    service = SolverService(provider)
    app.register_blueprint(build_api_blueprint(service))
    app.logger.info("autoSolve 应用已创建，provider=%s，日志=%s", type(provider).__name__, LOG_PATH)

    @app.get("/")
    def index():
        return jsonify({
            "name": "autoSolve",
            "status": "ok",
            "interfaces": {
                "native": "/api/v1/solve",
                "ocs": "/api/ocs/solve",
            },
        })

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app


app = create_app()


if __name__ == "__main__":
    # Playwright sync API 绑定创建它的线程；必须关闭 Flask 开发服务器的多线程，
    # 否则连续题目请求可能触发 greenlet.error: cannot switch to a different thread。
    app.run(host="127.0.0.1", port=8080, debug=False, threaded=False, use_reloader=False)
