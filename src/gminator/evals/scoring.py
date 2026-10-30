"""Scores a model's answer with deterministic checks; no model judges another."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from gminator.ai.context import sentences
from gminator.ai.factcheck import rules_talk
from gminator.ai.tasks import NARRATION_SENTENCES, NPC_SENTENCES, Intent
from gminator.evals.cases import Expected

Speaker = Literal["narrator", "npc"]

LENGTHS: dict[Speaker, range] = {
    "narrator": range(2, NARRATION_SENTENCES + 1),
    "npc": range(1, NPC_SENTENCES + 1),
}

# The narrator speaks to the player. An NPC may say anything in character, so is not checked.
_SECOND_PERSON = re.compile(r"\byou(r|rs|rself)?\b", re.IGNORECASE)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool


def intent_check(got: Intent, expected: Sequence[Expected]) -> Check:
    """Whether `got` is one of the `expected` intents."""
    return Check("intent", any(_matches(got, e) for e in expected))


def prose_checks(
    told: str,
    *,
    retracted: bool,
    speaker: Speaker,
    mentions: Sequence[str] = (),
    forbidden: Sequence[str] = (),
) -> list[Check]:
    """Checks on the text the player was finally told, and whether any of it was retracted."""
    checks = [
        Check("answered", bool(told.strip())),
        Check("fact_check", not retracted),
        Check("no_rules_talk", not rules_talk(told)),
        Check("length", len(sentences(told)) in LENGTHS[speaker]),
    ]
    if speaker == "narrator":
        checks.append(Check("speaker", bool(_SECOND_PERSON.search(told))))
    return [
        *checks,
        Check("mentions", not mentions or any(_mentioned(word, told) for word in mentions)),
        Check("forbidden", not any(_mentioned(word, told) for word in forbidden)),
    ]


def _matches(got: Intent, expected: Expected) -> bool:
    return (
        got.kind == expected.kind
        and got.move_id == expected.move_id
        and got.target == expected.target
        and got.then == expected.then
        and (expected.stat is None or got.stat == expected.stat)
    )


def _mentioned(word: str, text: str) -> bool:
    """`word` in `text`, ignoring case, as a whole word or the start of one."""
    return re.search(rf"\b{re.escape(word)}", text, re.IGNORECASE) is not None
