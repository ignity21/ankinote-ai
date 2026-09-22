"""The top-level ``cli`` group applies settings before any subcommand runs."""

from click.testing import CliRunner

from ankinote.cli.main import cli
from ankinote.settings import Settings, save_settings


def test_bare_invocation_is_not_a_tty_short_circuits_without_the_tui():
    """CliRunner's stdin is never a TTY, so the interactive menu never opens.

    Regression test for the bare-invocation behavior change: it used to print
    ``ctx.get_help()`` here; now a non-interactive bare invocation (a script
    or CI job that forgot a subcommand) gets a one-line hint instead, while an
    interactive terminal gets the TUI (see ``ankinote.cli.tui.run_tui``, smoke
    tested manually — not by ``CliRunner``, which never presents a TTY).
    """
    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0
    assert "not running interactively" in result.output


def test_bare_invocation_help_flag_still_prints_help():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "AI-powered Anki card generator" in result.output


def test_settings_json_backend_reaches_a_subcommand(monkeypatch):
    """A backend saved by the GUI/TUI is visible to CLI subcommands too.

    Regression test for the bug this Phase fixed: the CLI used to read only
    the bare ``ANKI_BACKEND`` env var, never ``settings.json``, so a backend
    switch made in the Web UI had no effect on ``ankinote anki ...``.
    """
    monkeypatch.delenv("ANKI_BACKEND", raising=False)
    save_settings(
        Settings(anki_backend="collection", anki_collection_path="/tmp/x.anki2")
    )

    result = CliRunner().invoke(cli, ["anki", "status"])

    # The command itself fails without a real collection at that path, but
    # by the time it does, ``apply_env`` has already pushed the saved
    # backend into the process — this asserts on that error, not "collection
    # backend requires ANKI_BACKEND=collection" (the failure mode this test
    # guards against).
    assert "Use Anki desktop to sync" not in result.output
