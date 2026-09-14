from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from ankinote.config import envs
from ankinote.utils.httpcli import post


class AnkiServiceError(Exception):
    """Base exception for Anki service errors."""


class AnkiTransportError(AnkiServiceError):
    """Raised when AnkiConnect cannot be reached."""


class AnkiConnectError(AnkiServiceError):
    """Raised when AnkiConnect returns a business error."""


class AnkiResponseError(AnkiServiceError):
    """Raised when AnkiConnect returns an unexpected response."""


class ModelAlreadyExists(AnkiConnectError):
    """Raised when attempting to create a model that already exists."""


class ModelNotFound(AnkiServiceError):
    """Raised when a specified model is not found."""


@dataclass
class ModelField:
    """Represents a field in an Anki note model."""

    id: int
    name: str
    description: str = field(default="")
    order: int | None = field(doc="Display order in the note type", default=None)
    font: str = field(default="Arial")
    size: int = field(doc="Font size in points", default=20)
    plain_text: bool = field(
        doc="Whether to store as plain text without formatting", default=False
    )
    collapsed: bool = field(
        doc="Whether the field is collapsed in the editor", default=True
    )
    exclude_from_search: bool = field(default=False)


@dataclass
class ModelTemplate:
    """Represents a card template in an Anki note model."""

    name: str
    question_format: str = field(doc="HTML/template for the question side")
    answer_format: str = field(doc="HTML/template for the answer side")
    id: int | None = field(doc="Template ID (assigned by Anki)", default=None)
    order: int | None = field(doc="Display order of this template", default=None)


@dataclass
class NoteModel:
    """Represents an Anki note model (note type)."""

    id: int
    name: str
    type: int = field(doc="Model type (0 for standard)", default=0)
    sort_field: int = field(doc="Index of the field used for sorting", default=0)
    deck_id: int | None = field(
        doc="Optional default deck for this note type", default=None
    )
    templates: list[ModelTemplate] = field(default_factory=list, repr=False)
    fields: list[ModelField] = field(default_factory=list)
    css: str = field(doc="CSS styling for cards", default="", repr=False)
    latex_pre: str = field(doc="LaTeX preamble", default="")
    latex_post: str = field(doc="LaTeX postamble", default="")
    latex_svg: bool = field(doc="Whether to render LaTeX as SVG", default=False)
    requirements: list[list[Any]] = field(
        doc="Card generation requirements", default_factory=list
    )


@dataclass(frozen=True, slots=True)
class TemplateUpsert:
    """Template update request keyed by stable template names."""

    name: str
    question_format: str
    answer_format: str
    previous_name: str | None = None


class _AnkiInvoker(Protocol):
    """Internal protocol for client groups that can invoke Anki actions."""

    async def _invoke(self, action: str, params: dict[str, Any] | None = None) -> Any:
        """Dispatch an AnkiConnect action."""


class AnkiModelService(Protocol):
    """Subset of model operations required by collections."""

    async def exists(self, model_name: str) -> bool:
        """Return whether a model exists."""
        ...

    async def get(self, model_name: str) -> NoteModel | None:
        """Return note model details if it exists."""
        ...

    async def create(
        self,
        model_name: str,
        fields: list[str],
        templates: list[dict[str, str]],
        css: str = "",
        is_cloze: bool = False,
    ) -> NoteModel:
        """Create a new note model."""
        ...

    async def update_templates(
        self, model_name: str, templates: list[TemplateUpsert]
    ) -> None:
        """Update existing note model templates."""
        ...

    async def update_styling(self, model_name: str, css: str) -> None:
        """Update note model CSS."""
        ...

    async def add_field(self, model_name: str, field_name: str) -> None:
        """Add a new field to an existing note model."""
        ...

    async def ensure_fields(self, model_name: str, field_names: list[str]) -> None:
        """Ensure note model contains all listed fields, adding missing ones."""
        ...


class AnkiDeckService(Protocol):
    """Subset of deck operations required by collections."""

    async def create(self, deck_name: str) -> int:
        """Create a deck or return the existing deck id."""
        ...

    async def exists(self, deck_name: str) -> bool:
        """Check whether a deck with the given name exists."""
        ...


class AnkiNoteService(Protocol):
    """Subset of note operations required by collections."""

    async def find(
        self,
        deck_name: str,
        unique_fields: dict[str, str],
        *,
        model_name: str | None = None,
    ) -> int | None:
        """Find a note by deck and unique fields."""
        ...

    async def add(
        self,
        deck_name: str,
        model_name: str,
        fields: dict[str, str],
        tags: list[str] | None = None,
        allow_duplicate: bool = False,
    ) -> int:
        """Add a new note."""
        ...

    async def update_fields(self, note_id: int, fields: dict[str, str]) -> None:
        """Update note fields."""
        ...

    async def update_tags(self, note_id: int, tags: list[str]) -> None:
        """Replace note tags."""
        ...


class AnkiMediaService(Protocol):
    """Subset of media operations required by collections."""

    async def store_file(self, filename: str, data: bytes) -> str:
        """Store a media file."""
        ...


class AnkiCollectionClient(Protocol):
    """Narrow client contract required by collection classes."""

    @property
    def models(self) -> AnkiModelService:
        """Model service facade."""
        ...

    @property
    def decks(self) -> AnkiDeckService:
        """Deck service facade."""
        ...

    @property
    def notes(self) -> AnkiNoteService:
        """Note service facade."""
        ...

    @property
    def media(self) -> AnkiMediaService:
        """Media service facade."""
        ...


class ModelClient:
    """Client for managing Anki note models."""

    def __init__(self, client: _AnkiInvoker) -> None:
        """Initialize ModelClient.

        Args:
            client: The parent AnkiConnectClient instance
        """
        self._client = client

    async def list_names(self) -> list[str]:
        """List all note types (models) in Anki.

        Returns:
            List of note type names
        """
        return await self._client._invoke("modelNames")

    async def exists(self, model_name: str) -> bool:
        """Check whether a model exists.

        Uses ``modelNames`` rather than fetching the full model payload — it is
        cheaper and keeps this working against AnkiConnect servers that do not
        implement ``findModelsByName`` (e.g. headless anki-connect-server).

        Raises:
            AnkiServiceError: If AnkiConnect cannot answer the request cleanly.
        """
        return model_name in await self.list_names()

    async def get(self, model_name: str) -> NoteModel | None:
        """Get details of a note type (model) by name.

        Args:
            model_name: The note type name

        Returns:
            NoteModel instance if present, otherwise ``None``.
        """
        try:
            model_list = await self._find_models_by_name(model_name)
        except AnkiConnectError as exc:
            if "model was not found" in str(exc):
                return None
            raise
        if not model_list:
            return None

        model_dict = model_list[0]
        return self._model_dict_to_notemodel(model_dict)

    async def require(self, model_name: str) -> NoteModel:
        """Get a model or raise if it does not exist."""
        if (model := await self.get(model_name)) is None:
            raise ModelNotFound(f"Model '{model_name}' not found")
        return model

    async def _find_models_by_name(self, model_name: str) -> list[dict[str, Any]]:
        result = await self._client._invoke(
            "findModelsByName",
            params={"modelNames": [model_name]},
        )
        if not isinstance(result, list):
            raise AnkiResponseError(
                f"Expected list from findModelsByName, got {type(result).__name__}"
            )
        if len(result) > 1:
            raise AnkiResponseError(
                f"Expected at most one model named '{model_name}', got {len(result)}"
            )
        if result and not isinstance(result[0], dict):
            raise AnkiResponseError(
                "Expected model payload to be a dictionary from findModelsByName"
            )
        return result

    def _model_dict_to_notemodel(self, model_dict: dict[str, Any]) -> NoteModel:
        """Convert a model dictionary from AnkiConnect to a NoteModel instance."""
        required_keys = {
            "id",
            "name",
            "type",
            "sortf",
            "did",
            "tmpls",
            "flds",
            "css",
            "latexPre",
            "latexPost",
            "latexsvg",
            "req",
        }
        missing_keys = required_keys - model_dict.keys()
        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise AnkiResponseError(f"Model payload missing required keys: {missing}")

        # Convert field dictionaries to Field objects
        fields = [
            ModelField(
                id=fld["id"],
                name=fld["name"],
                description=fld["description"],
                order=fld["ord"],
                font=fld["font"],
                size=fld["size"],
                plain_text=fld["plainText"],
                collapsed=fld["collapsed"],
                exclude_from_search=fld["excludeFromSearch"],
            )
            for fld in model_dict["flds"]
        ]

        # Convert template dictionaries to Template objects
        templates = [
            ModelTemplate(
                id=tmpl["id"],
                name=tmpl["name"],
                question_format=tmpl["qfmt"],
                answer_format=tmpl["afmt"],
                order=tmpl["ord"],
            )
            for tmpl in model_dict["tmpls"]
        ]

        # Create NoteModel instance
        return NoteModel(
            id=model_dict["id"],
            name=model_dict["name"],
            type=model_dict["type"],
            sort_field=model_dict["sortf"],
            deck_id=model_dict["did"],
            templates=templates,
            fields=fields,
            css=model_dict["css"],
            latex_pre=model_dict["latexPre"],
            latex_post=model_dict["latexPost"],
            latex_svg=model_dict["latexsvg"],
            requirements=model_dict["req"],
        )

    async def create(
        self,
        model_name: str,
        fields: list[str],
        templates: list[dict[str, str]],
        css: str = "",
        is_cloze: bool = False,
    ) -> NoteModel:
        """Create a new note model.

        Args:
            model_name: Name of the new model
            fields: List of field names in order
            templates: List of card templates, each with 'Name', 'Front', 'Back' keys
            css: Optional CSS styling (defaults to builtin CSS if empty)
            is_cloze: Whether this is a cloze deletion model

        Returns:
            The created NoteModel instance

        Raises:
            ModelAlreadyExistsError: If a model with this name already exists
            RuntimeError: For other AnkiConnect errors

        Example:
            >>> templates = [
            ...     {
            ...         "Name": "Card 1",
            ...         "Front": "{{Field1}}",
            ...         "Back": "{{FrontSide}}<hr>{{Field2}}"
            ...     }
            ... ]
            >>> await client.models.create(
            ...     model_name="My Model",
            ...     fields=["Field1", "Field2"],
            ...     templates=templates
            ... )
        """
        try:
            model_dict = await self._client._invoke(
                "createModel",
                params={
                    "modelName": model_name,
                    "inOrderFields": fields,
                    "css": css,
                    "isCloze": is_cloze,
                    "cardTemplates": templates,
                },
            )
        except RuntimeError as exc_:
            error_msg = str(exc_)
            if "already exists" in error_msg.lower():
                raise ModelAlreadyExists(
                    f"Model '{model_name}' already exists"
                ) from exc_
            raise
        else:
            return self._model_dict_to_notemodel(model_dict)

    async def update_templates(self, model_name: str, templates: list[TemplateUpsert]):
        """Update the templates of a note model.

        Args:
            model_name: The name of the note model
            templates: List of template upserts with stable template names

        Raises:
            RuntimeError: If AnkiConnect returns an error
        """
        existing_templates = await self._client._invoke(
            "modelTemplates",
            params={
                "modelName": model_name,
            },
        )
        if not isinstance(existing_templates, dict):
            raise AnkiResponseError("Expected dictionary from modelTemplates response")
        known_template_names = set(existing_templates)
        for tmpl in templates:
            match_name = tmpl.previous_name or tmpl.name

            if match_name not in known_template_names:
                await self._client._invoke(
                    "modelTemplateAdd",
                    params={
                        "modelName": model_name,
                        "template": {
                            "Name": tmpl.name,
                            "Front": tmpl.question_format,
                            "Back": tmpl.answer_format,
                        },
                    },
                )
                known_template_names.add(tmpl.name)
                continue

            if tmpl.previous_name is not None and tmpl.name != tmpl.previous_name:
                await self._client._invoke(
                    "modelTemplateRename",
                    params={
                        "modelName": model_name,
                        "oldTemplateName": tmpl.previous_name,
                        "newTemplateName": tmpl.name,
                    },
                )
                known_template_names.discard(tmpl.previous_name)
                known_template_names.add(tmpl.name)

            await self._client._invoke(
                "updateModelTemplates",
                params={
                    "model": {
                        "name": model_name,
                        "templates": {
                            tmpl.name: {
                                "Front": tmpl.question_format,
                                "Back": tmpl.answer_format,
                            }
                        },
                    }
                },
            )

    async def update_styling(self, model_name: str, css: str) -> None:
        """Update the CSS styling of a note model.

        Args:
            model_name: The name of the note model
            css: The new CSS styling

        Raises:
            RuntimeError: If AnkiConnect returns an error
        """
        await self._client._invoke(
            "updateModelStyling",
            params={
                "model": {
                    "name": model_name,
                    "css": css,
                }
            },
        )

    async def add_field(self, model_name: str, field_name: str) -> None:
        """Add a new field to an existing note model.

        Args:
            model_name: The name of the note model
            field_name: The field name to add
        """
        await self._client._invoke(
            "modelFieldAdd",
            params={
                "modelName": model_name,
                "fieldName": field_name,
            },
        )

    async def ensure_fields(self, model_name: str, field_names: list[str]) -> None:
        """Ensure note model contains all listed fields, adding missing ones."""
        model = await self.get(model_name)
        if model is None:
            return
        existing = {field.name for field in model.fields}
        for field_name in field_names:
            if field_name not in existing:
                await self.add_field(model_name, field_name)


class MediaClient:
    """Client for managing Anki media files."""

    def __init__(self, client: _AnkiInvoker) -> None:
        """Initialize MediaClient.

        Args:
            client: The parent AnkiConnectClient instance
        """
        self._client = client

    async def store_file(self, filename: str, data: bytes) -> str:
        """Store a media file in Anki's media folder.

        Args:
            filename: Name of the file to store
            data: Binary content of the file

        Returns:
            The filename of the stored file

        Raises:
            RuntimeError: If AnkiConnect returns an error

        Note:
            To prevent Anki from removing files not used by any cards,
            prefix the filename with an underscore (e.g. "_config.txt")

        Example:
            >>> with open("image.png", "rb") as f:
            ...     data = f.read()
            >>> filename = await client.media.store_file("word_image.png", data)
        """

        encoded_data = base64.b64encode(data).decode("utf-8")
        return await self._client._invoke(
            "storeMediaFile",
            params={
                "filename": filename,
                "data": encoded_data,
            },
        )


class DeckClient:
    """Client for managing Anki decks."""

    def __init__(self, client: _AnkiInvoker) -> None:
        """Initialize DeckClient.

        Args:
            client: The parent AnkiConnectClient instance
        """
        self._client = client

    async def create(self, deck_name: str) -> int:
        """Create a new deck if doesn't already exist.

        Args:
            deck_name: Name of the deck to create

        Returns:
            The ID of the created deck or the existing deck

        """
        return await self._client._invoke("createDeck", params={"deck": deck_name})

    async def exists(self, deck_name: str) -> bool:
        """Check if a deck with the given name exists.

        Args:
            deck_name: Name of the deck to check

        Returns:
            True if the deck exists, False otherwise
        """
        resp = await self._client._invoke(
            "getDeckConfig",
            params={
                "deck": deck_name,
            },
        )
        return resp is not False


class NoteClient:
    """Client for managing Anki notes."""

    def __init__(self, client: _AnkiInvoker) -> None:
        """Initialize NoteClient.

        Args:
            client: The parent AnkiConnectClient instance
        """
        self._client = client

    async def find(
        self,
        deck_name: str,
        unique_fields: dict[str, str],
        *,
        model_name: str | None = None,
    ) -> int | None:
        """Query for a note ID based on unique field values.

        Args:
            deck_name: Name of the deck to search within
            unique_fields: Dictionary of field names and their unique values

        Returns:
            The ID of the matching note or None if no match is found

        Raises:
            RuntimeError: If AnkiConnect returns an error or if no matching note is found

        Example:
            >>> note_id = await client.notes.query(
            ...     deck_name="My Vocabulary",
            ...     unique_fields={"Front": "hello"}
            ... )
        """

        def escape(value: str) -> str:
            return (
                value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("*", "\\*")
                .replace("_", "\\_")
            )

        query_parts = [f'deck:"{escape(deck_name)}"']
        if model_name is not None:
            query_parts.append(f'note:"{escape(model_name)}"')
        for field_, value in unique_fields.items():
            query_parts.append(f'{field_}:"{escape(value)}"')
        query_str = " ".join(query_parts)

        note_ids = await self._client._invoke("findNotes", params={"query": query_str})
        if not note_ids:
            return None
        if len(note_ids) > 1:
            raise KeyError(
                f"Expected exactly one note matching {unique_fields} in deck '{deck_name}', but found {len(note_ids)}"
            )
        return note_ids[0]

    async def add(
        self,
        deck_name: str,
        model_name: str,
        fields: dict[str, str],
        tags: list[str] | None = None,
        allow_duplicate: bool = False,
    ) -> int:
        """Add a new note to Anki.

        Args:
            deck_name: Name of the deck to add the note to
            model_name: Name of the note model/type
            fields: Dictionary mapping field names to their values
            tags: Optional list of tags to add to the note

        Returns:
            The ID of the created note

        Raises:
            RuntimeError: If AnkiConnect returns an error

        Example:
            >>> note_id = await client.notes.add(
            ...     deck_name="My Vocabulary",
            ...     model_name="Basic",
            ...     fields={
            ...         "Front": "hello",
            ...         "Back": "你好"
            ...     },
            ...     tags=["chinese", "greetings"]
            ... )
        """
        note_data = {
            "deckName": deck_name,
            "modelName": model_name,
            "fields": fields,
            "tags": tags or [],
            "options": {"allowDuplicate": allow_duplicate},
        }

        try:
            return await self._client._invoke("addNote", params={"note": note_data})
        except AnkiConnectError as e:
            error_msg = str(e)
            if "model was not found" in error_msg:
                raise ModelNotFound(f"Model '{model_name}' not found") from e
            raise

    async def update_fields(self, note_id: int, fields: dict[str, str]) -> None:
        """Update the fields of an existing note.

        Args:
            note_id: ID of the note to update
            fields: Dictionary of field names and their new values

        Raises:
            RuntimeError: If AnkiConnect returns an error
        """
        note_data: dict[str, Any] = {"id": note_id, "fields": fields}
        await self._client._invoke("updateNote", params={"note": note_data})

    async def update_tags(self, note_id: int, tags: list[str]) -> None:
        """Update the tags of an existing note.

        Args:
            note_id: ID of the note to update
            tags: List of tags to replace existing tags

        Raises:
            RuntimeError: If AnkiConnect returns an error
        """
        note_data: dict[str, Any] = {"id": note_id, "tags": tags}
        await self._client._invoke("updateNote", params={"note": note_data})

    async def replace_tag_in_all_notes(self, to_replace: str, replacement: str) -> None:
        """Replace a tag with another tag across all notes.

        Args:
            to_replace: The tag to be replaced
            replacement: The tag to replace with

        Raises:
            RuntimeError: If AnkiConnect returns an error
        """
        await self._client._invoke(
            "replaceTagsInAllNotes",
            params={
                "tag_to_replace": to_replace,
                "replace_with_tag": replacement,
            },
        )

    async def clear_all_unused_tags(self) -> None:
        """Clear all tags that are not currently used by any notes.

        Raises:
            RuntimeError: If AnkiConnect returns an error
        """
        await self._client._invoke("clearUnusedTags")


class AnkiConnectClient:
    """Client for interacting with AnkiConnect API."""

    def __init__(self, url: str | None = None) -> None:
        """Initialize AnkiConnect client.

        Args:
            url: AnkiConnect server URL. Defaults to ``ANKI_CONNECT_URL``
                (env var), otherwise ``http://localhost:8765``.
        """
        self._url = url or envs.ANKI_CONNECT_URL
        self.models = ModelClient(self)
        self.notes = NoteClient(self)
        self.decks = DeckClient(self)
        self.media = MediaClient(self)

    async def _invoke(self, action: str, params: dict[str, Any] | None = None) -> Any:
        """Invoke an AnkiConnect action.

        Args:
            action: The action to perform
            params: Parameters for the action

        Returns:
            The result from AnkiConnect

        Raises:
            RuntimeError: If AnkiConnect returns an error
        """
        payload: dict[str, Any] = {"action": action, "version": 6}
        if params is not None:
            payload["params"] = params
        try:
            response = await post(self._url, json=payload)
        except httpx.RequestError as exc:
            raise AnkiTransportError(
                f"Failed to reach AnkiConnect at {self._url}"
            ) from exc

        try:
            result = response.json()
        except ValueError as exc:
            raise AnkiResponseError("AnkiConnect returned invalid JSON") from exc

        if not isinstance(result, dict):
            raise AnkiResponseError(
                f"AnkiConnect returned {type(result).__name__}, expected dict"
            )
        if "error" not in result or "result" not in result:
            raise AnkiResponseError(
                "AnkiConnect response must include both 'error' and 'result'"
            )

        error = result["error"]
        if error is not None:
            raise AnkiConnectError(f"AnkiConnect error: {error}")

        return result["result"]
