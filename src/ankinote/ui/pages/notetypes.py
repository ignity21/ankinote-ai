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
from dataclasses import dataclass
from typing import Literal

from nicegui import ui

from ankinote.app import Application
from ankinote.note_types import NoteTypeSpec, TypeStatus, build_specs, load_status
from ankinote.services.anki_factory import create_anki_client
from ankinote.settings import load_settings
from ankinote.ui.i18n import set_locale, t
from ankinote.ui.pages.word import format_error
from ankinote.ui.sync import save_allowed, sync_feedback


@dataclass(frozen=True, slots=True)
class _Look:
    icon: str  # Material icon name
    accent: str  # CSS hex accent for this card type
    title: str  # Learner-facing name, e.g. "Word cards"


_LOOKS = {
    "word": _Look("translate", "#2563eb", "Word cards"),
    "phrase": _Look("chat_bubble_outline", "#6366f1", "Phrase & idiom cards"),
    "sentence": _Look("subject", "#0d9488", "Sentence cards"),
}


def _look(spec: NoteTypeSpec) -> _Look:
    kind = spec.key.removeprefix("stem_")
    return _LOOKS.get(spec.key) or _Look(
        "science", "#7c3aed", f"STEM {kind.title()} cards"
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
    spec, state = status.spec, status.state
    look = _look(spec)
    accent = look.accent
    with ui.element("div").classes("nt-card-head"):
        with ui.element("div").classes("nt-type-mark"):
            with ui.element("div").classes("nt-icon").style(f"--nt-accent: {accent}"):
                ui.icon(look.icon).classes("text-[1.35rem]")
            with ui.column().classes("gap-0"):
                with ui.row().classes("items-baseline gap-0"):
                    ui.label(look.title).classes("nt-title")
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
        .style(f"--nt-accent: {_look(status.spec).accent}")
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
    specs = build_specs()

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
                    await load_status(anki_client, spec) for spec in specs
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
            _notify(f"{_look(spec).title}: {t('notetypes.updated')}", "positive")
        except Exception as exc:
            _notify(f"{_look(spec).title}: {format_error(exc)}", "negative")
        finally:
            state["busy"].discard(spec.key)
        await _load()  # re-scan so the panel reflects the new state

    async def _sync_all() -> None:
        for spec in specs:
            await _sync_one(spec)

    _workspace()
    ui.timer(0.01, _load, once=True)
