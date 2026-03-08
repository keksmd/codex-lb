from __future__ import annotations

import pytest

from app import cli

pytestmark = pytest.mark.unit


def test_main_disables_access_log_and_passes_custom_log_config(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_run(app: str, **kwargs: object) -> None:
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(
        cli,
        "_parse_args",
        lambda: cli.argparse.Namespace(
            host="0.0.0.0",
            port=2455,
            ssl_certfile=None,
            ssl_keyfile=None,
        ),
    )
    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.setenv("CODEX_LB_LOG_LEVEL", "debug")

    cli.main()

    assert captured["app"] == "app.main:app"
    kwargs = captured["kwargs"]
    assert kwargs["access_log"] is False
    assert kwargs["log_config"]["root"]["level"] == "DEBUG"
    assert "Starting codex-lb" in capsys.readouterr().out
