from pathlib import Path

from autosolve.logging_config import configure_logging


def test_configure_logging_creates_file(tmp_path):
    log_path = configure_logging(tmp_path / "logs")
    assert log_path == (tmp_path / "logs" / "autosolve.log")
    assert log_path.exists()
