"""Run the collection-client contract against a real AnkiConnectClient.

Companion to ``test_anki_direct.py``: that file proves the ``collection``
backend against a real local collection, this proves the ``connect`` backend
against the same behavioral cases — talking real HTTP/JSON to a server
backed by the real ``anki`` library (see ``fake_anki_connect_server.py``)
instead of the hand-typed dicts in ``test_anki.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from collection_client_contract import CollectionClientContract
from fake_anki_connect_server import fake_anki_connect_server

from ankinote.services.anki import AnkiConnectClient
from ankinote.services.collection_runtime import CollectionRuntime
from ankinote.utils.httpcli import close_session, init_session

pytestmark = pytest.mark.asyncio


class TestAnkiConnectClient(CollectionClientContract):
    @pytest.fixture
    async def client(self, tmp_path: Path) -> AsyncIterator[AnkiConnectClient]:
        runtime = CollectionRuntime(str(tmp_path / "collection.anki2"))
        await runtime.open()
        init_session()
        try:
            async with fake_anki_connect_server(runtime) as url:
                yield AnkiConnectClient(url=url)
        finally:
            await close_session()
            await runtime.close()
