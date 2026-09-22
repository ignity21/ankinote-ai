"""In-process AnkiConnect-compatible HTTP server backed by a real collection.

Real AnkiConnect only runs inside Anki's Qt desktop process, which is not
something a test suite can spin up. This server implements the small subset
of AnkiConnect actions :class:`~ankinote.services.anki.AnkiConnectClient`
uses, dispatching each one straight to the real ``anki`` library (via
:class:`CollectionRuntime`) rather than a hand-typed fixture. Point
``AnkiConnectClient`` at it to exercise the real HTTP/JSON wire format
against genuine Anki-produced payloads (model dicts, deck configs, note
ids, ...), catching drift between what our client assumes and what the
``anki`` library actually returns — the class of bug hand-written mocks
cannot catch.

It is not a re-implementation of AnkiConnect itself: error messages are
chosen to match the real add-on's known dialect only where
:mod:`ankinote.services.anki` inspects them (e.g. ``"model was not found"``,
``"already exists"``).
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ankinote.services.collection_runtime import CollectionRuntime


class FakeAnkiConnectError(Exception):
    """Mirrors an AnkiConnect business error (the ``error`` response field)."""


def _model_names(col: Any, params: dict[str, Any]) -> list[str]:
    return col.models.all_names()


def _get_model_or_raise(col: Any, model_name: str) -> dict[str, Any]:
    model = col.models.by_name(model_name)
    if model is None:
        raise FakeAnkiConnectError(f"model was not found: {model_name}")
    return model


def _find_models_by_name(col: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
    models = (col.models.by_name(name) for name in params["modelNames"])
    return [dict(model) for model in models if model is not None]


def _create_model(col: Any, params: dict[str, Any]) -> dict[str, Any]:
    from anki.consts import MODEL_CLOZE, MODEL_STD

    mm = col.models
    model_name = params["modelName"]
    if mm.by_name(model_name) is not None:
        raise FakeAnkiConnectError(f"Model name already exists: {model_name}")

    model = mm.new(model_name)
    model["type"] = MODEL_CLOZE if params.get("isCloze") else MODEL_STD
    for field_name in params["inOrderFields"]:
        mm.add_field(model, mm.new_field(field_name))
    for template in params["cardTemplates"]:
        tmpl = mm.new_template(template["Name"])
        tmpl["qfmt"] = template["Front"]
        tmpl["afmt"] = template["Back"]
        mm.add_template(model, tmpl)
    if params.get("css"):
        model["css"] = params["css"]
    mm.add_dict(model)
    return dict(mm.by_name(model_name))


def _model_templates(col: Any, params: dict[str, Any]) -> dict[str, dict[str, str]]:
    model = _get_model_or_raise(col, params["modelName"])
    return {t["name"]: {"Front": t["qfmt"], "Back": t["afmt"]} for t in model["tmpls"]}


def _model_template_add(col: Any, params: dict[str, Any]) -> None:
    mm = col.models
    model = _get_model_or_raise(col, params["modelName"])
    template = params["template"]
    tmpl = mm.new_template(template["Name"])
    tmpl["qfmt"] = template["Front"]
    tmpl["afmt"] = template["Back"]
    mm.add_template(model, tmpl)
    mm.update_dict(model)


def _model_template_rename(col: Any, params: dict[str, Any]) -> None:
    model = _get_model_or_raise(col, params["modelName"])
    for tmpl in model["tmpls"]:
        if tmpl["name"] == params["oldTemplateName"]:
            tmpl["name"] = params["newTemplateName"]
            break
    else:
        raise FakeAnkiConnectError(f"Template not found: {params['oldTemplateName']}")
    col.models.update_dict(model)


def _update_model_templates(col: Any, params: dict[str, Any]) -> None:
    spec = params["model"]
    model = _get_model_or_raise(col, spec["name"])
    by_name = {t["name"]: t for t in model["tmpls"]}
    for name, sides in spec["templates"].items():
        tmpl = by_name.get(name)
        if tmpl is None:
            continue
        if "Front" in sides:
            tmpl["qfmt"] = sides["Front"]
        if "Back" in sides:
            tmpl["afmt"] = sides["Back"]
    col.models.update_dict(model)


def _update_model_styling(col: Any, params: dict[str, Any]) -> None:
    spec = params["model"]
    model = _get_model_or_raise(col, spec["name"])
    model["css"] = spec["css"]
    col.models.update_dict(model)


def _model_field_add(col: Any, params: dict[str, Any]) -> None:
    mm = col.models
    model = _get_model_or_raise(col, params["modelName"])
    if any(fld["name"] == params["fieldName"] for fld in model["flds"]):
        return
    mm.add_field(model, mm.new_field(params["fieldName"]))
    mm.update_dict(model)


def _create_deck(col: Any, params: dict[str, Any]) -> int:
    return col.decks.id(params["deck"])


def _get_deck_config(col: Any, params: dict[str, Any]) -> Any:
    deck = col.decks.by_name(params["deck"])
    if deck is None:
        return False
    return dict(col.decks.config_dict_for_deck_id(deck["id"]))


def _find_notes(col: Any, params: dict[str, Any]) -> list[int]:
    return list(col.find_notes(params["query"]))


def _add_note(col: Any, params: dict[str, Any]) -> int:
    note = params["note"]
    model = _get_model_or_raise(col, note["modelName"])
    deck_id = col.decks.id(note["deckName"])
    new_note = col.new_note(model)
    for field_name, value in note["fields"].items():
        new_note[field_name] = value
    if note.get("tags"):
        new_note.tags = list(note["tags"])
    col.add_note(new_note, deck_id)
    return new_note.id


def _update_note(col: Any, params: dict[str, Any]) -> None:
    note = params["note"]
    existing = col.get_note(note["id"])
    if "fields" in note:
        for field_name, value in note["fields"].items():
            existing[field_name] = value
    if "tags" in note:
        existing.tags = list(note["tags"])
    col.update_note(existing)


def _store_media_file(col: Any, params: dict[str, Any]) -> str:
    data = base64.b64decode(params["data"])
    return col.media.write_data(params["filename"], data)


_ACTIONS: dict[str, Any] = {
    "modelNames": _model_names,
    "findModelsByName": _find_models_by_name,
    "createModel": _create_model,
    "modelTemplates": _model_templates,
    "modelTemplateAdd": _model_template_add,
    "modelTemplateRename": _model_template_rename,
    "updateModelTemplates": _update_model_templates,
    "updateModelStyling": _update_model_styling,
    "modelFieldAdd": _model_field_add,
    "createDeck": _create_deck,
    "getDeckConfig": _get_deck_config,
    "findNotes": _find_notes,
    "addNote": _add_note,
    "updateNote": _update_note,
    "storeMediaFile": _store_media_file,
}


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length))
        try:
            action = payload["action"]
            handler = _ACTIONS.get(action)
            if handler is None:
                raise FakeAnkiConnectError(f"unsupported action: {action}")
            params = payload.get("params") or {}
            future = asyncio.run_coroutine_threadsafe(
                self.server.runtime.submit(lambda col: handler(col, params)),
                self.server.loop,
            )
            response: dict[str, Any] = {
                "result": future.result(timeout=10),
                "error": None,
            }
        except FakeAnkiConnectError as exc:
            response = {"result": None, "error": str(exc)}
        except Exception as exc:  # surfaces as an error body, not a transport failure
            response = {"result": None, "error": f"internal fake-server error: {exc!r}"}
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Server(ThreadingHTTPServer):
    def __init__(
        self, runtime: CollectionRuntime, loop: asyncio.AbstractEventLoop
    ) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.runtime = runtime
        self.loop = loop


@asynccontextmanager
async def fake_anki_connect_server(runtime: CollectionRuntime) -> AsyncIterator[str]:
    """Serve AnkiConnect's JSON API against ``runtime`` over real HTTP.

    Yields the server's base URL.
    """
    server = _Server(runtime, asyncio.get_running_loop())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
