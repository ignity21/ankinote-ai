"""The editable form of a generated card.

Each kind lists, beside its model (``EDIT_FORM``), the parts a user may
change before saving. What isn't listed stays as generated: the headword
(it names the note and its media, so changing it means generating another),
image prompts, example highlights.

``describe`` turns a model into the form the editor shows; ``revise``
applies the values it sends back. Limits (required, how many rows) come
from the model itself, so the two can't drift apart.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

# Far past any real field; keeps a pasted document out of a card and of TTS.
MAX_TEXT_LENGTH = 2000


@dataclass(frozen=True)
class Text:
    """One string, at a dotted path into the model."""

    key: str
    multiline: bool = False


@dataclass(frozen=True)
class Lines:
    """A list of strings, edited one per line."""

    key: str


@dataclass(frozen=True)
class Rows:
    """A list of records; ``columns`` are the parts of each that are edited."""

    key: str
    columns: tuple[str, ...]


type FormField = Text | Lines | Rows
type Form = Sequence[FormField]


class EditError(ValueError):
    """An edit the card can't hold.

    ``blank``: a required text is empty. ``too_few`` / ``too_many``: a list
    is outside the model's limits. ``too_long``: a text is implausibly long.
    ``invalid``: anything else, with the reason in ``detail``.
    """

    def __init__(
        self,
        code: Literal["blank", "too_few", "too_many", "too_long", "invalid"],
        key: str,
        detail: str = "",
    ) -> None:
        super().__init__(f"{key}: {code} {detail}".strip())
        self.code = code
        self.key = key
        self.detail = detail


def _field_info(model: type[BaseModel], key: str) -> FieldInfo:
    *parents, name = key.split(".")
    for parent in parents:
        nested = model.model_fields[parent].annotation
        assert isinstance(nested, type) and issubclass(nested, BaseModel), key
        model = nested
    return model.model_fields[name]


def _limits(info: FieldInfo) -> tuple[int, int | None]:
    low, high = 0, None
    for constraint in info.metadata:
        low = getattr(constraint, "min_length", low)
        high = getattr(constraint, "max_length", high)
    return low, high


def _value(data: Mapping[str, Any], key: str) -> Any:
    value: Any = data
    for part in key.split("."):
        value = value[part]
    return value


def describe(model: BaseModel, form: Form) -> list[dict[str, Any]]:
    """The form filled with the model's values, as JSON for the editor."""
    data = model.model_dump()
    fields: list[dict[str, Any]] = []
    for field in form:
        info = _field_info(type(model), field.key)
        value = _value(data, field.key)
        if isinstance(field, Text):
            fields.append(
                {
                    "key": field.key,
                    "type": "area" if field.multiline else "text",
                    "required": info.is_required(),
                    "value": value or "",
                }
            )
            continue
        low, high = _limits(info)
        described: dict[str, Any] = {"key": field.key, "min": low, "max": high}
        if isinstance(field, Lines):
            described |= {"type": "lines", "value": list(value)}
        else:
            described |= {
                "type": "rows",
                "columns": list(field.columns),
                "value": [
                    {"id": index, "cells": {c: row[c] or "" for c in field.columns}}
                    for index, row in enumerate(value)
                ],
            }
        fields.append(described)
    return fields


def _text(key: str, raw: Any, previous: Any = None) -> str:
    """``raw`` trimmed; the previous value when only its spacing differs."""
    if not isinstance(raw, str):
        raise EditError("invalid", key, "expected text")
    text = raw.strip()
    if len(text) > MAX_TEXT_LENGTH:
        raise EditError("too_long", key)
    if isinstance(previous, str) and previous.strip() == text:
        return previous
    return text


def _lines(key: str, raw: Any) -> list[str]:
    if not isinstance(raw, list):
        raise EditError("invalid", key, "expected a list")
    return [line for line in (_text(key, item) for item in raw) if line]


def _rows(field: Rows, raw: Any, previous: list[dict[str, Any]]) -> list[dict]:
    """Rows with every column filled; a row left entirely blank is dropped.

    A row keeps what the form doesn't show (an example's highlights) by the
    ``id`` it was described with; a row without one is new.
    """
    key = field.key
    if not isinstance(raw, list):
        raise EditError("invalid", key, "expected a list")
    rows: list[dict] = []
    used: set[int] = set()
    for item in raw:
        cells = item.get("cells") if isinstance(item, dict) else None
        if not isinstance(cells, dict):
            raise EditError("invalid", key, "expected rows of cells")
        index = item.get("id")
        known = isinstance(index, int) and 0 <= index < len(previous)
        base = previous[index] if known and index not in used else {}
        texts = {
            column: _text(key, cells.get(column, ""), base.get(column))
            for column in field.columns
        }
        if not any(texts.values()):
            continue
        if not all(texts.values()):
            raise EditError("blank", key)
        if base:
            used.add(index)
        rows.append({**base, **texts})
    return rows


def revise[M: BaseModel](model: M, form: Form, values: Mapping[str, Any]) -> M:
    """``model`` with the edited ``values`` (by field key) applied.

    Raises:
        EditError: a value the form doesn't offer or the model can't hold.
    """
    fields = {field.key: field for field in form}
    data = model.model_dump()
    for key, raw in values.items():
        field = fields.get(key)
        if field is None:
            raise EditError("invalid", key, "not editable")
        info = _field_info(type(model), key)
        *parents, name = key.split(".")
        holder = data
        for parent in parents:
            holder = holder[parent]
        if isinstance(field, Text):
            text = _text(key, raw, holder[name])
            if not text and info.is_required():
                raise EditError("blank", key)
            holder[name] = text or None
            continue
        if isinstance(field, Lines):
            items: list = _lines(key, raw)
        else:
            items = _rows(field, raw, holder[name])
        low, high = _limits(info)
        if len(items) < low:
            raise EditError("too_few", key)
        if high is not None and len(items) > high:
            raise EditError("too_many", key)
        holder[name] = items
    try:
        return type(model).model_validate(data)
    except ValidationError as exc:
        error = exc.errors()[0]
        where = ".".join(str(part) for part in error["loc"])
        raise EditError("invalid", where, error["msg"]) from exc
