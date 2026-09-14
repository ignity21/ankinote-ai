import sys

import click
from loguru import logger

from ankinote import __version__

from .anki import anki
from .phrase import phrase
from .sentence import sentence
from .stem import stem
from .word import word

_VERSION_BANNER = f"""╔══════════════════════════════════════════════╗
║               AnkiNote v{__version__}                ║
║       AI-powered Anki card generator        ║
╚══════════════════════════════════════════════╝"""


@click.group()
@click.version_option(
    prog_name="ankinote",
    message=_VERSION_BANNER,
)
def cli():
    """AI-powered Anki card generator — vocabulary, phrases, sentences, STEM concepts."""


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
