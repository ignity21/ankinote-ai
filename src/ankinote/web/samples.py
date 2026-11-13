"""Sample answers for the Note types page's preview, one per note type.

Each is shaped like the model's answer for that kind, so the sample note goes
through the same parsing and field formatting as a generated one. English
cards for a Simplified Chinese speaker; no audio or pictures.
"""

from typing import Any

WORD: list[dict[str, Any]] = [
    {
        "lemma": "lantern",
        "part_of_speech": "noun",
        "pronunciation": "/ˈlæn.tən/",
        "difficulty": "B1",
        "morphology": "plural: lanterns",
        "core_meaning": {
            "target_text": "a lamp in a case that protects its flame or bulb, "
            "often carried by a handle",
            "native_text": "灯笼；提灯",
            "image_prompt": "A paper lantern glowing above a wooden door at dusk",
            "is_visualizable": True,
        },
        "examples": [
            {
                "sentence": "She hung a paper lantern above the door.",
                "translation": "她在门上方挂了一盏纸灯笼。",
                "highlights": ["lantern"],
            },
            {
                "sentence": "We walked home by the light of a lantern.",
                "translation": "我们借着提灯的光走回了家。",
                "highlights": ["lantern"],
            },
        ],
        "collocations": ["paper lantern", "light a lantern", "lantern festival"],
        "confusions": ["lamp: any device that gives light; a lantern is enclosed"],
        "etymology_or_memory": "From Latin lanterna, “lamp”.",
    }
]

PHRASE: dict[str, Any] = {
    "phrase": "break the ice",
    "difficulty": "B1",
    "core_meaning": {
        "target_text": "to make people who have just met feel more relaxed",
        "native_text": "打破僵局；活跃气氛",
    },
    "supporting_meanings": [],
    "examples": [
        {
            "sentence": "He told a joke to break the ice.",
            "translation": "他讲了个笑话来活跃气氛。",
            "highlights": ["break the ice"],
        },
        {
            "sentence": "A quick game helped break the ice at the meeting.",
            "translation": "一个小游戏让会议的气氛轻松了起来。",
            "highlights": ["break the ice"],
        },
    ],
    "usage_pattern": "break the ice (with someone)",
    "production_hint": "初次见面时，让大家不再拘谨",
    "confusions": ["break the news: tell someone bad news"],
    "etymology_or_memory": "Ships once needed the ice broken to open a route.",
    "associations": ["icebreaker", "small talk", "warm up"],
}

SENTENCE: dict[str, Any] = {
    "target_sentence": "I'd rather walk than wait for the bus.",
    "native_sentence": "我宁愿走路，也不想等公交车。",
    "notes": ["would rather A than B: 宁愿 A 也不 B", "I'd = I would"],
    "phrases": [
        {
            "phrase": "would rather",
            "translation": "宁愿",
            "example": "I'd rather stay home tonight.",
        }
    ],
}

STEM: dict[str, dict[str, Any]] = {
    "concept": {
        "card_type": "concept",
        "front": "What is entropy?",
        "back_brief": "A measure of how many microscopic arrangements match a "
        "system's macroscopic state; loosely, its disorder.",
        "back_detail": "For a reversible process at temperature \\(T\\), "
        "\\(\\Delta S = \\frac{Q_{\\text{rev}}}{T}\\). The entropy of an isolated "
        "system never decreases.",
        "tags": ["Physics", "Thermodynamics"],
        "image_description": None,
    },
    "formula": {
        "card_type": "formula",
        "front": "Kinetic energy of a moving body?",
        "latex": "E_k = \\frac{1}{2} m v^2",
        "meaning": "The energy a body has because it moves.",
        "variables": [
            {"symbol": "m", "description": "mass"},
            {"symbol": "v", "description": "speed"},
        ],
        "conditions": "Speeds well below light speed (\\(v \\ll c\\)).",
        "derivation": "The work done accelerating it from rest: "
        "\\(W = \\int F\\,dx = \\int m v\\,dv = \\tfrac{1}{2} m v^2\\).",
        "tags": ["Physics", "Mechanics"],
        "image_description": None,
    },
    "procedure": {
        "card_type": "procedure",
        "front": "How do you complete the square for \\(x^2 + bx + c\\)?",
        "summary": "Rewrite it as a squared binomial plus a constant.",
        "steps": [
            "Take half of \\(b\\): \\(\\frac{b}{2}\\).",
            "Add and subtract \\(\\left(\\frac{b}{2}\\right)^2\\).",
            "Group: \\(\\left(x + \\frac{b}{2}\\right)^2 + c - \\frac{b^2}{4}\\).",
        ],
        "conditions": "The coefficient of \\(x^2\\) is 1; divide through first "
        "if it isn't.",
        "tags": ["Math", "Algebra"],
        "image_description": None,
    },
    "example": {
        "card_type": "example",
        "front": "Solve \\(x^2 - 5x + 6 = 0\\).",
        "answer": "\\(x = 2\\) or \\(x = 3\\)",
        "steps": [
            "Find two numbers with product 6 and sum −5: −2 and −3.",
            "Factor: \\((x - 2)(x - 3) = 0\\).",
            "Set each factor to zero: \\(x = 2\\) or \\(x = 3\\).",
        ],
        "explanation": "A product is zero only when one of its factors is.",
        "tags": ["Math", "Algebra"],
        "image_description": None,
    },
}
