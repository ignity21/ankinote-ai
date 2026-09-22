import sys

from ankinote.cli.tui import run_tui


def test_non_tty_short_circuits_without_importing_menu(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.delitem(sys.modules, "ankinote.cli.tui.menu", raising=False)

    run_tui()

    assert "not running interactively" in capsys.readouterr().out
    assert "ankinote.cli.tui.menu" not in sys.modules


def test_tty_opens_the_menu(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    called = {}
    monkeypatch.setattr(
        "ankinote.cli.tui.menu.run_menu",
        lambda settings: called.setdefault("ran", True),
    )

    run_tui()

    assert called == {"ran": True}
