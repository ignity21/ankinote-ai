"""``ankinote-web``: run the 1.0 web app."""

import click
import uvicorn

from ankinote.web.app import create_app


@click.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
def main(host: str, port: int) -> None:
    """Serve the ankinote web app."""
    uvicorn.run(create_app(), host=host, port=port)
