import sys

import click
from loguru import logger

from ankinote import __version__
from ankinote.settings import apply_env, load_settings

from .anki import anki
from .phrase import phrase
from .sentence import sentence
from .stem import stem
from .word import word

_VERSION_BANNER = f"""╔══════════════════════════════════════════════╗
║               AnkiNote v{__version__}                ║
║       AI-powered Anki card generator        ║
╚══════════════════════════════════════════════╝"""


@click.group(invoke_without_command=True)
@click.version_option(
    prog_name="ankinote",
    message=_VERSION_BANNER,
)
@click.pass_context
def cli(ctx: click.Context):
    """AI-powered Anki card generator — vocabulary, phrases, sentences, STEM concepts."""
    # Push the GUI's persisted settings.json (Anki backend, TTS key) into the
    # process env before any subcommand runs, so a backend switch made in the
    # Web UI or the TUI is visible here too — previously only the GUI process
    # ever saw it.
    apply_env(load_settings())
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


cli.add_command(word)
cli.add_command(phrase)
cli.add_command(sentence)
cli.add_command(stem)
cli.add_command(anki)


def main():
    logger.remove()  # Remove default logger
    logger.add(
        sys.stderr,
        colorize=True,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    )
    cli()
