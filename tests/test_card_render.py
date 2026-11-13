"""Rendering Anki card templates for the in-app preview."""

import dataclasses

from ankinote.card_render import render_card
from ankinote.collections.word.collection import WordCollection
from ankinote.collections.word.models import WordNoteType


def url(name: str) -> str:
    return f"/media/{name}"


def test_fields_and_sections() -> None:
    html = render_card(
        "{{#a}}<p>{{a}}</p>{{/a}}{{#b}}<p>B</p>{{/b}}{{^b}}<i>no b</i>{{/b}}",
        {"a": "<b>x</b>", "b": " <br> "},
        media_url=url,
    )
    # Field HTML is kept; a field holding only whitespace/<br> counts as empty.
    assert html == "<p><b>x</b></p><i>no b</i>"


def test_nested_sections() -> None:
    html = render_card(
        "{{#a}}[{{#b}}{{b}}{{/b}}]{{/a}}", {"a": "1", "b": "2"}, media_url=url
    )
    assert html == "[2]"


def test_front_side_and_type_answer() -> None:
    front = render_card("Q {{type:lemma}}", {"lemma": "moon"}, media_url=url)
    back = render_card(
        "{{FrontSide}}<hr id=answer>{{type:lemma}}",
        {"lemma": "moon"},
        front_side=front,
        answer=True,
        media_url=url,
    )
    assert '<input type="text" id="typeans"' in front
    # The back shows the expected answer; its FrontSide has no second input.
    assert back.count('id="typeans"') == 1
    assert '<code id="typeans">' in back and "moon" in back


def test_sound_tags_become_replay_buttons_and_images_get_urls() -> None:
    html = render_card(
        "{{audio}}{{img}}",
        {"audio": "[sound:a b.mp3]", "img": "<img class='x' src='p.png'>"},
        media_url=url,
    )
    assert "[sound:" not in html
    assert 'class="replay-button soundLink"' in html
    assert 'data-src="/media/a b.mp3"' in html
    assert "src='/media/p.png'" in html


def test_unknown_field_is_visible() -> None:
    assert "missing" in render_card("{{missing}}", {}, media_url=url)


def test_word_templates_render_cleanly_without_audio_or_image() -> None:
    fields = {field.name: "" for field in dataclasses.fields(WordNoteType)}
    fields |= {
        "lemma": "moon",
        "core_meaning": "the moon",
        "target_language": "English",
    }

    for template in WordCollection.card_templates():
        front = render_card(template["Front"], fields, media_url=url)
        back = render_card(
            template["Back"], fields, front_side=front, answer=True, media_url=url
        )
        for html in (front, back):
            assert "{{" not in html and "}}" not in html
            assert "replay-button" not in html
            assert "<img" not in html
            assert "Visuals" not in html
