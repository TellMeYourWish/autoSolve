from __future__ import annotations

import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler


_CONFIGURED = False


def configure_logging(log_dir: str | Path = "logs") -> Path:
    """配置控制台和文件日志，返回日志文件路径。"""
    global _CONFIGURED
    target_dir = Path(log_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = target_dir / "autosolve.log"
    if any(isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_path for handler in logging.getLogger().handlers):
        _CONFIGURED = True
        return log_path

    level_name = os.getenv("AUTOSOLVE_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_path for handler in root.handlers):
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    if not any(isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler) for handler in root.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    _CONFIGURED = True
    logging.getLogger(__name__).info("日志已启用: %s", log_path.resolve())
    return log_path
