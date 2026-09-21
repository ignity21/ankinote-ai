"""Tests for the Anki backend selection factory."""

from __future__ import annotations

from pathlib import Path

import pytest

from ankinote.services.anki import AnkiConnectClient
from ankinote.services.anki_direct import DirectCollectionClient
from ankinote.services.anki_factory import (
    AnkiBackendConfigError,
    anki_backend_scope,
    create_anki_client,
    get_shared_runtime,
    stop_anki_backend,
    switch_backend,
)
from ankinote.services.anki_sync import (
    SyncSnapshot,
    SyncState,
    SyncStateStore,
    SyncWriteBlocked,
)

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "ankinote"
_FACTORY_MODULE = _SRC_ROOT / "services" / "anki_factory.py"
_DEFINING_MODULE = _SRC_ROOT / "services" / "anki.py"


class TestBackendSelection:
    def test_defaults_to_ankiconnect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("ankinote.config.envs.ANKI_BACKEND", "connect")
        assert isinstance(create_anki_client(), AnkiConnectClient)

    def test_blank_backend_defaults_to_ankiconnect(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("ankinote.config.envs.ANKI_BACKEND", "")
        assert isinstance(create_anki_client(), AnkiConnectClient)

    def test_unknown_backend_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("ankinote.config.envs.ANKI_BACKEND", "nonsense")
        with pytest.raises(AnkiBackendConfigError, match="Unknown ANKI_BACKEND"):
            create_anki_client()

    def test_collection_backend_requires_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("ankinote.config.envs.ANKI_BACKEND", "collection")
        monkeypatch.setattr("ankinote.config.envs.ANKI_COLLECTION_PATH", "")
        with pytest.raises(AnkiBackendConfigError, match="ANKI_COLLECTION_PATH"):
            create_anki_client()

    def test_collection_backend_without_active_scope_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("ankinote.config.envs.ANKI_BACKEND", "collection")
        monkeypatch.setattr(
            "ankinote.config.envs.ANKI_COLLECTION_PATH", "/tmp/collection"
        )
        with pytest.raises(AnkiBackendConfigError, match="not started"):
            create_anki_client()


@pytest.fixture
def collection_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("ankinote.config.envs.ANKI_BACKEND", "collection")
    monkeypatch.setattr("ankinote.config.envs.ANKIWEB_USERNAME", "")
    monkeypatch.setattr("ankinote.config.envs.ANKIWEB_PASSWORD", "")
    monkeypatch.setattr(
        "ankinote.config.envs.ANKI_COLLECTION_PATH",
        str(tmp_path / "collection.anki2"),
    )


class TestBackendScope:
    async def test_scope_shares_one_runtime_across_clients(
        self, collection_env: None
    ) -> None:
        async with anki_backend_scope():
            a = create_anki_client()
            b = create_anki_client()
            assert isinstance(a, DirectCollectionClient)
            assert a._runtime is b._runtime is get_shared_runtime()  # type: ignore[attr-defined]
        assert get_shared_runtime() is None

    async def test_scope_closes_runtime_on_exception(
        self, collection_env: None
    ) -> None:
        with pytest.raises(RuntimeError, match="boom"):
            async with anki_backend_scope():
                assert get_shared_runtime() is not None
                raise RuntimeError("boom")
        assert get_shared_runtime() is None

    async def test_nested_scope_reuses_and_defers_close(
        self, collection_env: None
    ) -> None:
        async with anki_backend_scope():
            outer = get_shared_runtime()
            async with anki_backend_scope():
                assert get_shared_runtime() is outer
            # inner exit must not close the runtime the outer scope owns
            assert get_shared_runtime() is outer
        assert get_shared_runtime() is None

    async def test_connect_backend_scope_is_noop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("ankinote.config.envs.ANKI_BACKEND", "connect")
        async with anki_backend_scope():
            assert get_shared_runtime() is None
            assert isinstance(create_anki_client(), AnkiConnectClient)

    async def test_concurrent_collection_calls_serialize_and_complete(
        self, collection_env: None
    ) -> None:
        import asyncio

        from ankinote.config import envs

        # An initialized collection remains writable while logged out/offline.
        SyncStateStore(Path(f"{envs.ANKI_COLLECTION_PATH}.sync.json")).save(
            SyncSnapshot(initialized=True)
        )
        async with anki_backend_scope():
            client = create_anki_client()
            await client.decks.create("D")
            results = await asyncio.gather(
                client.decks.create("D"),
                client.decks.create("D"),
                client.models.exists("nope"),
            )
        assert results[0] == results[1]
        assert results[2] is False

    async def test_fresh_collection_starts_logged_out_and_blocks_writes(
        self, collection_env: None
    ) -> None:
        async with anki_backend_scope():
            runtime = get_shared_runtime()
            assert runtime is not None
            assert runtime.sync_service is not None
            assert runtime.sync_service.status.state == SyncState.NOT_LOGGED_IN
            client = create_anki_client()
            assert await client.models.exists("Basic")
            with pytest.raises(SyncWriteBlocked):
                await client.decks.create("D")


class TestSwitchBackend:
    async def test_switch_from_collection_to_connect_closes_the_runtime(
        self, collection_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        try:
            await switch_backend()
            assert get_shared_runtime() is not None
            monkeypatch.setattr("ankinote.config.envs.ANKI_BACKEND", "connect")
            await switch_backend()
            assert get_shared_runtime() is None
            assert isinstance(create_anki_client(), AnkiConnectClient)
        finally:
            await stop_anki_backend()

    async def test_switch_between_two_collection_paths_reopens_the_runtime(
        self, collection_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        other_path = other_dir / "collection.anki2"
        try:
            await switch_backend()
            first = get_shared_runtime()
            assert first is not None

            monkeypatch.setattr(
                "ankinote.config.envs.ANKI_COLLECTION_PATH", str(other_path)
            )
            await switch_backend()
            second = get_shared_runtime()
            assert second is not None
            assert second is not first
            assert second.path == str(other_path)
        finally:
            await stop_anki_backend()


def test_no_direct_backend_construction_outside_factory() -> None:
    """Only the factory (and the module that defines it) may name the concrete
    ``AnkiConnectClient`` backend; every other module goes through the factory."""
    offenders: list[str] = []
    for path in _SRC_ROOT.rglob("*.py"):
        if path in (_FACTORY_MODULE, _DEFINING_MODULE):
            continue
        if "AnkiConnectClient(" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(_SRC_ROOT)))
    assert not offenders, (
        f"modules construct AnkiConnectClient directly instead of "
        f"create_anki_client(): {offenders}"
    )
