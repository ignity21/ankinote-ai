"""Card Types page — create or refresh Anki note types and decks from the GUI.

This is the visual counterpart of the CLI ``init`` commands (``word init``,
``phrase init``, ...). Instead of running a terminal command, the learner sees
each of ankinote's note types as a physical flashcard that shows its anatomy —
the fields it stores and the front/back templates it renders — plus a live
status computed from AnkiConnect: not created yet, up to date, or needing an
update because fields, templates or styling have drifted from the app's current
definitions.

Nothing here generates cards or starts TTS/LLM services; it only inspects and
upserts Anki note-type/deck definitions through the collections' public
``ensure_in_anki()`` method.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from nicegui import ui

from ankinote.app import Application
from ankinote.collections.phrase import PhraseCollection
from ankinote.collections.phrase.models import PhraseNoteType
from ankinote.collections.phrase.templates import (
    load_card_style as _phrase_style,
)
from ankinote.collections.sentence import SentenceCollection
from ankinote.collections.sentence.models import SentenceNoteType
from ankinote.collections.sentence.templates import (
    load_card_style as _sentence_style,
)
from ankinote.collections.stem import StemCollection
from ankinote.collections.stem.models import NOTE_FIELDS, CardType, note_type_name
from ankinote.collections.stem.templates import (
    load_card_style as _stem_style,
)
from ankinote.collections.word import WordCollection
from ankinote.collections.word.models import WordNoteType
from ankinote.collections.word.templates import (
    load_card_style as _word_style,
)
from ankinote.consts import Language
from ankinote.services.ai import LiteLLMTextService
from ankinote.services.anki import AnkiCollectionClient
from ankinote.services.anki_factory import create_anki_client
from ankinote.ui.config import load_settings
from ankinote.ui.i18n import set_locale, t
from ankinote.ui.pages.word import format_error
from ankinote.ui.sync import save_allowed, sync_feedback

# ---------------------------------------------------------------------------
# Note type specs — one per collection. These mirror the definitions that the
# collections themselves write into Anki (fields, template names, styling), so
# the status computed here matches what ``ensure_in_anki()`` will actually do.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NoteTypeSpec:
    """Static description of one note type ankinote can create/update."""

    key: str
    icon: str  # Material icon name
    accent: str  # CSS hex accent for this card type
    title: str  # Learner-facing name, e.g. "Word cards"
    notetype_name: str  # Anki model name
    deck_name: str  # Anki deck path
    fields: tuple[str, ...]
    templates: tuple[str, ...]
    css: str
    sync: Callable[[AnkiCollectionClient], Awaitable[None]]

    @property
    def css_size_kb(self) -> str:
        """Human-readable size of the note type styling."""
        return f"{len(self.css.encode()) / 1024:.1f} KB"


@dataclass(frozen=True, slots=True)
class TypeStatus:
    """Live status of one note type as seen in Anki."""

    spec: NoteTypeSpec
    exists: bool
    deck_exists: bool
    missing_fields: list[str]
    missing_templates: list[str]
    css_differs: bool

    @property
    def state(self) -> str:
        """One of ``synced``, ``update`` or ``missing``."""
        if not self.exists:
            return "missing"
        if self.missing_fields or self.missing_templates or self.css_differs:
            return "update"
        return "synced"


def _field_names(note_type) -> tuple[str, ...]:
    return tuple(field.name for field in note_type.__dataclass_fields__.values())


def _build_specs() -> list[NoteTypeSpec]:
    """Assemble the fixed set of note types managed by ankinote."""

    def sync_word(notetype_name: str, deck_name: str):
        async def _sync(client: AnkiCollectionClient) -> None:
            collection = WordCollection(
                client,
                native_language=Language.CHINESE_S,
                target_language=Language.ENGLISH,
                notetype_name=notetype_name,
                deck_name=deck_name,
                text_model="",
                text_service=LiteLLMTextService(),
                image_service=None,
            )
            await collection.ensure_in_anki()

        return _sync

    def sync_language(clazz, notetype_name: str, deck_name: str):
        async def _sync(client: AnkiCollectionClient) -> None:
            collection = clazz(
                client,
                native_language=Language.CHINESE_S,
                target_language=Language.ENGLISH,
                notetype_name=notetype_name,
                deck_name=deck_name,
                text_model="",
                text_service=LiteLLMTextService(),
            )
            await collection.ensure_in_anki()

        return _sync

    def sync_stem(card_type: CardType):
        async def _sync(client: AnkiCollectionClient) -> None:
            collection = StemCollection(
                client,
                card_type=card_type,
                text_model="",
                text_service=LiteLLMTextService(),
            )
            await collection.ensure_in_anki()

        return _sync

    return [
        NoteTypeSpec(
            key="word",
            icon="translate",
            accent="#2563eb",
            title="Word cards",
            notetype_name="AINote Word V2",
            deck_name="AINote::Words",
            fields=_field_names(WordNoteType),
            templates=("Recognition", "Recall", "Spelling"),
            css=_word_style(),
            sync=sync_word("AINote Word V2", "AINote::Words"),
        ),
        NoteTypeSpec(
            key="phrase",
            icon="chat_bubble_outline",
            accent="#6366f1",
            title="Phrase & idiom cards",
            notetype_name="AINote Phrase V2",
            deck_name="AINote::Phrases",
            fields=_field_names(PhraseNoteType),
            templates=("Recognition", "Recall"),
            css=_phrase_style(),
            sync=sync_language(PhraseCollection, "AINote Phrase V2", "AINote::Phrases"),
        ),
        NoteTypeSpec(
            key="sentence",
            icon="subject",
            accent="#0d9488",
            title="Sentence cards",
            notetype_name="AINote Sentence V2",
            deck_name="AINote::Sentences",
            fields=_field_names(SentenceNoteType),
            templates=("Production",),
            css=_sentence_style(),
            sync=sync_language(
                SentenceCollection, "AINote Sentence V2", "AINote::Sentences"
            ),
        ),
        *[
            NoteTypeSpec(
                key=f"stem_{kind}",
                icon="science",
                accent="#7c3aed",
                title=f"STEM {kind.title()} cards",
                notetype_name=note_type_name(kind),
                deck_name="AINote::STEM",
                fields=NOTE_FIELDS[kind],
                templates=("Card 1",),
                css=_stem_style(),
                sync=sync_stem(kind),
            )
            for kind in CardType
        ],
    ]


# ---------------------------------------------------------------------------
# Anki introspection
# ---------------------------------------------------------------------------


async def _load_status(client: AnkiCollectionClient, spec: NoteTypeSpec) -> TypeStatus:
    """Compute one note type's live status from AnkiConnect."""
    model = await client.models.get(spec.notetype_name)
    deck_exists = await client.decks.exists(spec.deck_name)
    if model is None:
        return TypeStatus(
            spec=spec,
            exists=False,
            deck_exists=deck_exists,
            missing_fields=[],
            missing_templates=[],
            css_differs=False,
        )

    existing_fields = {f.name for f in model.fields}
    existing_templates = {t.name for t in model.templates}
    return TypeStatus(
        spec=spec,
        exists=True,
        deck_exists=deck_exists,
        missing_fields=[f for f in spec.fields if f not in existing_fields],
        missing_templates=[t for t in spec.templates if t not in existing_templates],
        css_differs=model.css != spec.css,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_STATE_LABEL = {
    "synced": "Up to date",
    "update": "Update",
    "missing": "Not created",
}


def _inject_styles() -> None:
    """Add the page's small design system."""
    ui.add_css(
        """
        /* ---- workspace ---- */
        .nt-eyebrow {
            color: #64748b;
            font-size: .68rem;
            font-weight: 800;
            letter-spacing: .16em;
            text-transform: uppercase;
        }
        .nt-lede { color: #64748b; font-size: .92rem; max-width: 46rem; }

        /* desk surface the flashcards sit on */
        .nt-desk {
            background-color: #f3f6fb;
            background-image: radial-gradient(circle, #d7dfeb 1.1px, transparent 1.2px);
            background-size: 22px 22px;
            border: 1px solid #e3e9f2;
            border-radius: 20px;
            padding: .9rem;
        }

        /* ---- flashcard panel ---- */
        .nt-card {
            background: #ffffff;
            border: 1px solid #e4e9f1;
            border-left: 5px solid var(--nt-accent, #2563eb);
            border-radius: 16px;
            box-shadow: 0 1px 2px rgb(15 23 42 / .04), 0 14px 30px -20px rgb(15 23 42 / .35);
            overflow: hidden;
        }
        .nt-card-head {
            align-items: flex-start;
            display: flex;
            gap: 1rem;
            justify-content: space-between;
            padding: 1rem 1.1rem .9rem;
        }
        .nt-type-mark { align-items: flex-start; display: flex; gap: .75rem; min-width: 0; }
        .nt-icon {
            align-items: center;
            background: color-mix(in srgb, var(--nt-accent, #2563eb) 13%, #ffffff);
            border: 1px solid color-mix(in srgb, var(--nt-accent, #2563eb) 30%, #ffffff);
            border-radius: 12px;
            color: var(--nt-accent, #2563eb);
            display: flex;
            flex: none;
            font-size: 1.3rem;
            height: 2.5rem;
            justify-content: center;
            width: 2.5rem;
        }
        .nt-icon .q-icon { font-size: 1.35rem; }
        .nt-title {
            color: #0f172a;
            font-size: 1.05rem;
            font-weight: 750;
            letter-spacing: -0.01em;
            line-height: 1.25;
        }
        .nt-ntname {
            color: var(--nt-accent, #2563eb);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: .72rem;
            font-weight: 600;
            margin-left: .4rem;
        }
        .nt-meta { color: #64748b; font-size: .8rem; margin-top: .22rem; }
        .nt-head-actions { align-items: center; display: flex; flex: none; gap: .6rem; }

        /* status stamp */
        .nt-stamp {
            border-radius: 999px;
            display: inline-flex;
            font-size: .62rem;
            font-weight: 800;
            letter-spacing: .12em;
            padding: .32rem .6rem;
            text-transform: uppercase;
            white-space: nowrap;
        }
        .nt-stamp-ok { background: #ecfdf5; border: 1px solid #a7f3d0; color: #047857; }
        .nt-stamp-warn { background: #fffbeb; border: 1px solid #fde68a; color: #b45309; }
        .nt-stamp-bad { background: #fff1f2; border: 1px solid #fecdd3; color: #be123c; }

        /* anatomy zones */
        .nt-anatomy {
            border-top: 1px dashed #e4e9f1;
            border-bottom: 1px dashed #e4e9f1;
            display: grid;
            gap: 1.1rem;
            grid-template-columns: minmax(0, 5fr) minmax(0, 6fr);
            padding: .9rem 1.1rem 1.05rem;
        }
        .nt-zone-label {
            color: #94a3b8;
            font-size: .64rem;
            font-weight: 800;
            letter-spacing: .13em;
            margin-bottom: .5rem;
            text-transform: uppercase;
        }
        .nt-field-grid { display: flex; flex-wrap: wrap; gap: .32rem; }
        .nt-field-chip {
            background: #f6f8fb;
            border: 1px solid #e7ecf3;
            border-radius: 7px;
            color: #334155;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: .68rem;
            padding: .22rem .5rem;
        }
        .nt-field-more {
            color: #94a3b8;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: .68rem;
            padding: .22rem .5rem;
        }

        /* template mini-cards */
        .nt-tpl-list { display: flex; flex-wrap: wrap; gap: .55rem; }
        .nt-tpl {
            background: #fff;
            border: 1px solid #e4e9f1;
            border-left: 3px solid var(--nt-accent, #2563eb);
            border-radius: 9px;
            box-shadow: 0 2px 6px -3px rgb(15 23 42 / .18);
            min-width: 8.2rem;
            overflow: hidden;
        }
        .nt-tpl-name {
            background: #f6f8fb;
            border-bottom: 1px solid #e4e9f1;
            color: #334155;
            font-size: .68rem;
            font-weight: 700;
            letter-spacing: .02em;
            padding: .3rem .55rem;
            white-space: nowrap;
        }
        .nt-tpl-side {
            color: #94a3b8;
            font-size: .66rem;
            padding: .34rem .55rem;
        }
        .nt-tpl-side b {
            color: var(--nt-accent, #2563eb);
            font-size: .6rem;
            font-weight: 800;
            letter-spacing: .1em;
            text-transform: uppercase;
        }
        .nt-tpl-front { border-bottom: 1px dashed #dbe2ec; }
        .nt-tpl-back { color: #b6bfcc; }

        /* footer / drift */
        .nt-foot {
            align-items: center;
            display: flex;
            flex-wrap: wrap;
            gap: .5rem 1rem;
            padding: .7rem 1.1rem;
        }
        .nt-foot-note { color: #64748b; font-size: .78rem; }
        .nt-foot-meta { color: #94a3b8; font-size: .72rem; }
        .nt-diff {
            border-radius: 999px;
            font-size: .7rem;
            font-weight: 700;
            padding: .24rem .55rem;
        }
        .nt-diff-ok { background: #ecfdf5; color: #047857; }
        .nt-diff-warn { background: #fffbeb; color: #b45309; }
        .nt-diff-bad { background: #fff1f2; color: #be123c; }

        /* summary chips */
        .nt-stat {
            align-items: center;
            border: 1px solid #e4e9f1;
            border-radius: 999px;
            background: #ffffff;
            display: inline-flex;
            font-size: .78rem;
            font-weight: 700;
            gap: .4rem;
            padding: .38rem .7rem;
        }
        .nt-stat b { font-size: .82rem; font-variant-numeric: tabular-nums; }

        /* generic buttons */
        .nt-btn {
            border-radius: 10px !important;
            font-weight: 700 !important;
            min-height: 2.3rem;
        }
        .nt-btn-accent { background: var(--nt-accent, #2563eb) !important; }
        .nt-btn-ghost { color: #475569 !important; }

        /* connection error */
        .nt-error {
            background: #fff;
            border: 1px solid #fecdd3;
            border-radius: 16px;
            padding: 1.2rem 1.3rem;
        }

        /* dark desk */
        .body--dark .nt-eyebrow { color: #94a3b8; }
        .body--dark .nt-lede { color: #94a3b8; }
        .body--dark .nt-desk { background-color: #0b1220; border-color: #22304a; }
        .body--dark .nt-desk {
            background-image: radial-gradient(circle, #1c2b47 1.1px, transparent 1.2px);
        }
        .body--dark .nt-card { background: #141e33; border-color: #263650; }
        .body--dark .nt-title { color: #eef2f8; }
        .body--dark .nt-meta { color: #8ba0bd; }
        .body--dark .nt-ntname { color: var(--nt-accent, #60a5fa); }
        .body--dark .nt-icon {
            background: color-mix(in srgb, var(--nt-accent, #2563eb) 18%, #141e33);
            border-color: color-mix(in srgb, var(--nt-accent, #2563eb) 42%, #141e33);
        }
        .body--dark .nt-anatomy { border-color: #2a3a56; }
        .body--dark .nt-zone-label { color: #64748b; }
        .body--dark .nt-field-chip {
            background: #1c2942;
            border-color: #2c3d5c;
            color: #cbd5e1;
        }
        .body--dark .nt-field-more { color: #64748b; }
        .body--dark .nt-tpl { background: #17223a; border-color: #2c3d5c; }
        .body--dark .nt-tpl-name { background: #1c2942; border-color: #2c3d5c; color: #cbd5e1; }
        .body--dark .nt-tpl-front { border-color: #33456a; }
        .body--dark .nt-tpl-back { color: #5a6c8c; }
        .body--dark .nt-foot-note { color: #8ba0bd; }
        .body--dark .nt-foot-meta { color: #64748b; }
        .body--dark .nt-stat { background: #141e33; border-color: #2a3a56; color: #cbd5e1; }
        .body--dark .nt-error { background: #141e33; border-color: #5b2333; }
        .body--dark .nt-btn-ghost { color: #cbd5e1 !important; }

        @media (max-width: 640px) {
            .nt-anatomy { grid-template-columns: 1fr; }
            .nt-card-head { flex-direction: column; }
            .nt-head-actions { width: 100%; justify-content: space-between; }
        }
        @media (prefers-reduced-motion: no-preference) {
            .nt-card, .nt-tpl, .nt-btn { transition: box-shadow .18s ease, transform .18s ease, border-color .18s ease; }
            .nt-card:hover { box-shadow: 0 2px 4px rgb(15 23 42 / .06), 0 20px 34px -18px rgb(15 23 42 / .4); }
        }
        """
    )


def _render_header(status: TypeStatus, busy: bool, on_sync) -> None:
    """The type mark, name/deck summary, sync status stamp, and action button."""
    spec, state, accent = status.spec, status.state, status.spec.accent
    with ui.element("div").classes("nt-card-head"):
        with ui.element("div").classes("nt-type-mark"):
            with ui.element("div").classes("nt-icon").style(f"--nt-accent: {accent}"):
                ui.icon(spec.icon).classes("text-[1.35rem]")
            with ui.column().classes("gap-0"):
                with ui.row().classes("items-baseline gap-0"):
                    ui.label(spec.title).classes("nt-title")
                    ui.label(spec.notetype_name).classes("nt-ntname")
                ui.label(
                    f"{spec.deck_name} · {len(spec.fields)} fields · "
                    f"{len(spec.templates)} {'card' if len(spec.templates) == 1 else 'cards'}"
                ).classes("nt-meta")
        with ui.element("div").classes("nt-head-actions"):
            stamp_class = {
                "synced": "nt-stamp-ok",
                "update": "nt-stamp-warn",
                "missing": "nt-stamp-bad",
            }[state]
            ui.label(_STATE_LABEL[state]).classes(f"nt-stamp {stamp_class}")
            if state == "missing":
                ui.button(
                    t("notetypes.create"),
                    on_click=lambda: asyncio.ensure_future(on_sync(spec)),
                    icon="add_circle_outline",
                ).props("unelevated no-caps").classes("nt-btn nt-btn-accent").style(
                    f"--nt-accent: {accent}"
                )
            else:
                ui.button(
                    t("notetypes.sync_again")
                    if state == "synced"
                    else t("notetypes.update"),
                    on_click=lambda: asyncio.ensure_future(on_sync(spec)),
                    icon="sync",
                ).props("outline no-caps").classes("nt-btn nt-btn-ghost")
            if busy:
                ui.spinner(size="1.2em").classes("text-slate-400")


def _render_anatomy(spec: NoteTypeSpec) -> None:
    """The fields grid and the front/back preview for each card template."""
    with ui.element("div").classes("nt-anatomy"):
        with ui.element("div"):
            ui.label(f"Fields · {len(spec.fields)}").classes("nt-zone-label")
            with ui.element("div").classes("nt-field-grid"):
                for name in spec.fields[:4]:
                    ui.label(name).classes("nt-field-chip")
                if len(spec.fields) > 4:
                    ui.label(f"+{len(spec.fields) - 4} more").classes("nt-field-more")
        with ui.element("div"):
            ui.label(f"Cards · {len(spec.templates)}").classes("nt-zone-label")
            with ui.element("div").classes("nt-tpl-list"):
                for template in spec.templates:
                    with ui.element("div").classes("nt-tpl"):
                        ui.label(template).classes("nt-tpl-name")
                        ui.html("<b>front</b>&nbsp; question").classes(
                            "nt-tpl-side nt-tpl-front"
                        )
                        ui.html("<b>back</b>&nbsp; answer").classes(
                            "nt-tpl-side nt-tpl-back"
                        )


def _render_footer(status: TypeStatus) -> None:
    """Drift/reassurance note: what's missing, what changed, or that it matches."""
    spec, state = status.spec, status.state
    with ui.element("div").classes("nt-foot"):
        if state == "missing":
            ui.label(t("notetypes.not_in_anki")).classes("nt-foot-note")
        elif state == "update":
            if status.missing_fields:
                ui.label(
                    f"{len(status.missing_fields)} field(s) will be added"
                ).classes("nt-diff nt-diff-bad")
            if status.missing_templates:
                ui.label(
                    f"{len(status.missing_templates)} card template(s) will be added"
                ).classes("nt-diff nt-diff-bad")
            if status.css_differs:
                ui.label(t("notetypes.styling_changed")).classes("nt-diff nt-diff-warn")
                ui.label(t("notetypes.notes_preserved")).classes("nt-foot-note")
        else:
            if status.deck_exists:
                ui.label(t("notetypes.match")).classes("nt-foot-note")
            else:
                ui.label(t("notetypes.deck_recreated")).classes("nt-foot-note")
            ui.label(
                f"{spec.css_size_kb} styling · AINote::… deck ready"
                if status.deck_exists
                else f"{spec.css_size_kb} styling · deck missing"
            ).classes("nt-foot-meta").style("margin-left:auto")


def _render_panel(status: TypeStatus, busy: bool, on_sync) -> None:
    """Render one note type as a physical flashcard showing its anatomy."""
    with (
        ui.element("div")
        .classes("nt-card w-full")
        .style(f"--nt-accent: {status.spec.accent}")
    ):
        _render_header(status, busy, on_sync)
        _render_anatomy(status.spec)
        _render_footer(status)


def _render_summary(statuses: list[TypeStatus], busy_all: bool, on_rescan, on_sync_all):
    """Header row with counts and the global controls."""
    counts = {"synced": 0, "update": 0, "missing": 0}
    for status in statuses:
        counts[status.state] += 1

    chip_style = {
        "synced": (t("notetypes.matched"), "#047857"),
        "update": ("Needs update", "#b45309"),
        "missing": ("Not created", "#be123c"),
    }
    with ui.row().classes("w-full items-center justify-between gap-3 flex-wrap"):
        with ui.row().classes("items-center gap-2 flex-wrap"):
            for state, (label, color) in chip_style.items():
                if counts[state] == 0:
                    continue
                with ui.element("span").classes("nt-stat"):
                    ui.element("span").classes("w-2 h-2 rounded-full").style(
                        f"background:{color}"
                    )
                    ui.label(f"{counts[state]} {label}").style(f"color:{color}")
        with ui.row().classes("items-center gap-2"):
            ui.button(
                t("notetypes.rescan"),
                on_click=lambda: asyncio.ensure_future(on_rescan()),
                icon="refresh",
            ).props("flat no-caps").classes("nt-btn nt-btn-ghost")
            if busy_all:
                with ui.element("span").classes("nt-stat"):
                    ui.spinner(size="1em")
                    ui.label(t("notetypes.syncing")).classes("text-slate-500")
            else:
                ui.button(
                    t("notetypes.sync_all"),
                    on_click=lambda: asyncio.ensure_future(on_sync_all()),
                    icon="bolt",
                ).props("unelevated no-caps").classes("nt-btn nt-btn-accent").style(
                    "--nt-accent: #2563eb"
                )


def notetypes_page() -> None:  # noqa: C901 - UI composition
    """Render the Card Types management page."""
    _inject_styles()
    set_locale(load_settings().ui_language)
    specs = _build_specs()

    # Mutable state shared by the refreshable workspace below.
    state: dict = {"statuses": None, "error": None, "busy": set()}
    client = ui.context.client

    with ui.column().classes("w-full max-w-5xl mx-auto px-6 pt-4"):
        sync_feedback()

    def _notify(
        message: str,
        kind: Literal["positive", "negative", "warning", "info", "ongoing"],
    ) -> None:
        with client:
            ui.notify(message, type=kind)  # type: ignore[arg-type]

    @ui.refreshable
    def _workspace() -> None:
        with ui.column().classes(
            "nt-workspace w-full max-w-5xl mx-auto px-6 py-8 md:px-10 gap-5"
        ):
            with ui.column().classes("gap-1"):
                ui.label(t("notetypes.setup")).classes("nt-eyebrow")
                ui.label(t("notetypes.title")).classes(
                    "text-3xl font-bold tracking-tight text-slate-900"
                )
                ui.label(t("notetypes.description")).classes("nt-lede")

            if state["error"]:
                _render_error(state["error"], on_retry=_load)
                return
            if state["statuses"] is None:
                with ui.row().classes("w-full items-center gap-3 py-10 justify-center"):
                    ui.spinner(size="1.6em").classes("text-slate-400")
                    ui.label(t("notetypes.scanning")).classes("text-slate-500 text-sm")
                return

            _render_summary(
                state["statuses"],
                busy_all=bool(state["busy"]),
                on_rescan=_load,
                on_sync_all=_sync_all,
            )
            with ui.column().classes("nt-desk w-full gap-4"):
                for status in state["statuses"]:
                    _render_panel(
                        status,
                        busy=status.spec.key in state["busy"],
                        on_sync=_sync_one,
                    )

    def _render_error(message: str, on_retry) -> None:
        with (
            ui.element("div").classes("nt-error w-full"),
            ui.row().classes("items-start gap-3 w-full"),
        ):
            ui.icon("wifi_off").classes("text-2xl text-rose-500")
            with ui.column().classes("gap-1 flex-1"):
                ui.label(t("notetypes.cant_reach")).classes(
                    "text-base font-bold text-slate-900"
                )
                ui.label(message).classes("text-sm text-slate-500")
                ui.label(t("notetypes.open_anki")).classes("text-sm text-slate-500")
            ui.button(
                t("notetypes.retry"),
                on_click=lambda: asyncio.ensure_future(on_retry()),
                icon="refresh",
            ).props("outline no-caps").classes("nt-btn nt-btn-ghost")

    async def _load() -> None:
        state["error"] = None
        state["statuses"] = None
        _workspace.refresh()
        try:
            async with Application():
                anki_client = create_anki_client()
                state["statuses"] = [
                    await _load_status(anki_client, spec) for spec in specs
                ]
        except Exception as exc:
            state["error"] = format_error(exc)
        _workspace.refresh()

    async def _sync_one(spec: NoteTypeSpec) -> None:
        if not save_allowed():
            _notify(t("sync.write_blocked"), "warning")
            return
        state["busy"].add(spec.key)
        _workspace.refresh()
        try:
            async with Application():
                anki_client = create_anki_client()
                await spec.sync(anki_client)
            _notify(f"{spec.title}: {t('notetypes.updated')}", "positive")
        except Exception as exc:
            _notify(f"{spec.title}: {format_error(exc)}", "negative")
        finally:
            state["busy"].discard(spec.key)
        await _load()  # re-scan so the panel reflects the new state

    async def _sync_all() -> None:
        for spec in specs:
            await _sync_one(spec)

    _workspace()
    ui.timer(0.01, _load, once=True)
