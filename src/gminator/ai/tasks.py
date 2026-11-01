"""The jobs the AI may do: classify the player's words, narrate an outcome the engine has
already decided, voice an NPC, and answer the player as the GM. None of them changes the
game."""

import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict

from gminator.ai.context import Context
from gminator.ai.factcheck import FactCheck, rules_talk
from gminator.ai.provider import (
    Answers,
    DecisionProvider,
    LLMProvider,
    Message,
    ProviderError,
    Schema,
)

Kind = Literal["move", "travel", "talk", "look", "inventory", "ooc", "unclear"]

CLASSIFY_TEMPERATURE = 0.0
NARRATE_TEMPERATURE = 0.7
NARRATION_SENTENCES = 4
NPC_SENTENCES = 3
GM_SENTENCES = 4

# A sentence ends at . ! or ?, then any closing quotes or brackets, then a space.
_SENTENCE_END = re.compile(r"[.!?]+[\"'\u201d\u2019)]*(?=\s)")
# Quoted speech: double or curly quotes, or single quotes that aren't apostrophes.
_QUOTED = re.compile(r"\"[^\"]*\"|\u201c[^\u201d]*\u201d|(?<!\w)'[^']*'(?!\w)")
# Words in place names that say nothing about which place it is.
_COMMON = {"a", "an", "the", "of", "to", "in", "on", "at", "and", "s"}


class Intent(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Kind
    move_id: str | None = None
    stat: str | None = None
    target: str | None = None
    then: str | None = None
    """For a move: the place the player goes on to once it is made."""


@dataclass(frozen=True)
class MoveOption:
    description: str
    stats: list[str] = field(default_factory=list)
    """The stats the player may choose to roll with, if any."""
    targeted: bool | Literal["obstacle"] = False
    """Whether the move is made against someone here, or an obstacle."""


@dataclass(frozen=True)
class Options:
    """What the player can do right now: moves, people here, places to go and obstacles in
    the way, by id."""

    moves: dict[str, MoveOption] = field(default_factory=dict)
    people: dict[str, str] = field(default_factory=dict)
    places: dict[str, str] = field(default_factory=dict)
    obstacles: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Retract:
    """Throw away the text streamed so far: it failed, and what follows replaces it."""


Part = str | Retract

CLASSIFY_SYSTEM = """\
You turn a player's words into one action in a fantasy tabletop roleplaying game.
Choose only from the options listed. Kinds of action:
- move: the player does something that triggers one of the moves. Give move_id, the stat if \
the move lets the player choose one, and the target if the move is aimed at someone here or \
at an obstacle. If the player also says they go on to one of the places once it is done, \
give that place as then.
- travel: the player goes to one of the places. Give the place as target.
- talk: the player speaks to someone here, without making a move. Give them as target.
- look: the player looks around.
- inventory: the player checks their character or gear.
- ooc: the player talks to the game itself, not in the story.
- unclear: nothing else fits.
Answer with JSON only."""

# For a decision model: what each kind of action means, and the answer for "none of these".
DECISION_KINDS = {
    "move": "the player does something in the story that triggers one of the listed moves: "
    "fighting, sneaking, persuading, studying, recalling lore, resting, helping",
    "travel": "the player goes, walks or heads to another place",
    "talk": "the player just speaks to or asks a person here something, without a move",
    "look": "the player looks around at where they are",
    "inventory": "the player checks their own character, health or gear",
    "ooc": "the player talks to the game itself or about real life, not in the story",
    "unclear": "the words make no sense or fit nothing else",
}
NONE = "none of these"

NARRATE_SYSTEM = """\
You narrate a fantasy tabletop roleplaying game for one player.
Write 2 to 4 sentences of vivid prose in the second person and present tense.
The game has already decided what happened: describe only what the facts say.
Do not invent people, places, items or outcomes. Never mention dice, numbers, HP or rules."""

VOICE_SYSTEM = """\
You speak as one character in a fantasy tabletop roleplaying game.
Answer the player character in 1 to 3 sentences of spoken dialogue, in character.
Say only what this character would know. Do not decide what anyone else does.

{profile}"""

GM_SYSTEM = """\
You are the game master of a fantasy tabletop roleplaying game, answering the player out of \
character. Answer in 1 to 4 plain sentences, from the facts and options below only.
You may explain the moves and how they work. Do not decide what happens in the story, and \
do not tell anything the facts don't say: if they don't answer the question, say so."""


def split_speech(text: str) -> tuple[str, str]:
    """The player's `text` as the action and the quoted speech in it. Only the action is
    classified: a small model tells one action apart better without the speech around it."""
    speech = " ".join(match.group()[1:-1].strip() for match in _QUOTED.finditer(text))
    action = " ".join(_QUOTED.sub(" ", text).split())
    return action, speech


def classify(provider: LLMProvider, context: Context, options: Options, text: str) -> Intent:
    """The player's `text` as an intent, or `unclear` after two answers that can't be used."""
    if isinstance(provider, DecisionProvider) and provider.decides():
        state = f"{context.render()}\n\nPlayer: {text}"
        return _decided(provider.decide(state, _questions(options)), options, text)
    messages = [
        Message("system", CLASSIFY_SYSTEM),
        Message("user", f"{context.render()}\n\n{_render_options(options)}\n\nPlayer: {text}"),
    ]
    schema = _intent_schema(options)
    for _ in range(2):
        reply = provider.complete(messages, schema=schema, temperature=CLASSIFY_TEMPERATURE)
        intent = _read_intent(reply, options)
        if intent is not None:
            if intent.then is not None and not _names(text, intent.then, options):
                intent = intent.model_copy(update={"then": None})
            return intent
    return Intent(kind="unclear")


def _questions(options: Options) -> dict[str, object]:
    """What a decision model is asked about the player's words. Each part of the intent is its
    own question; one with nothing to choose from is left out."""

    def choice(instructions: str, criteria: dict[str, str]) -> dict[str, object]:
        return {"type": "choice", "instructions": instructions, "criteria": criteria}

    moves = {move_id: move.description for move_id, move in options.moves.items()}
    stats = list(dict.fromkeys(stat for move in options.moves.values() for stat in move.stats))
    questions = {
        "kind": choice("What kind of action is the player taking?", DECISION_KINDS),
        "move": choice(
            "If the player does something that triggers a move, which move?",
            {**moves, NONE: "the player triggers no move"},
        ),
    }
    if options.people:
        questions["person"] = choice(
            "Which person here is the player acting on or speaking to?",
            {**options.people, NONE: "no one"},
        )
    if options.places:
        questions["place"] = choice(
            "Which place does the player say they go to?",
            {**options.places, NONE: "the player names no place to go"},
        )
    if options.obstacles:
        questions["obstacle"] = choice(
            "Which obstacle is the player acting on?", {**options.obstacles, NONE: "none"}
        )
    if stats:
        questions["stat"] = choice(
            "Which ability does the player use?", {**{s: s for s in stats}, NONE: "unsure"}
        )
    return questions


def _decided(answers: Answers, options: Options, text: str) -> Intent:
    """The intent from a decision model's answers. A named move wins over the kind: the model
    picks the move more reliably than it tells a move from talk or a look. Going where no way
    leads is `travel` without a target."""
    picked: dict[str, str | None] = {}
    for name, answer in answers.items():
        choice = answer.get("choice") if isinstance(answer, dict) else None
        picked[name] = None if choice == NONE or not isinstance(choice, str) else choice
    move_id, person, place = picked.get("move"), picked.get("person"), picked.get("place")
    kind = "move" if move_id is not None else picked.get("kind")
    match kind:
        case "move" if move_id in options.moves:
            move = options.moves[move_id]
            stat = picked.get("stat")
            stat = stat if stat in move.stats else None
            then = place if place in options.places and _names(text, place, options) else None
            if move.targeted == "obstacle":
                target, targets = picked.get("obstacle"), options.obstacles
            elif move.targeted:
                target, targets = person, options.people
            else:
                return Intent(kind=kind, move_id=move_id, stat=stat, then=then)
            if target in targets:
                return Intent(kind=kind, move_id=move_id, stat=stat, target=target, then=then)
        case "travel":
            return Intent(kind=kind, target=place if place in options.places else None)
        case "talk" if person in options.people:
            return Intent(kind=kind, target=person)
        case "look" | "inventory" | "ooc" | "unclear":
            return Intent(kind=kind)
    return Intent(kind="unclear")


def _names(text: str, place: str, options: Options) -> bool:
    """Whether the player's `text` names `place`: going on somewhere is only ever what the
    player said, never the model's guess."""
    said = set(_words(text))
    return any(word in said for word in _words(f"{place} {options.places[place]}"))


def _words(text: str) -> list[str]:
    """The words of `text` that can tell one place from another: no articles or particles."""
    return [word for word in re.findall(r"[a-z]+", text.lower()) if word not in _COMMON]


def narrate(
    provider: LLMProvider,
    check: FactCheck,
    context: Context,
    facts: Sequence[str],
    said: str = "",
) -> Iterator[Part]:
    """Prose for what the engine decided, streamed and fact-checked."""
    told = "\n".join(f"- {fact}" for fact in facts)
    prompt = f"{context.render()}\n\nWhat just happened:\n{told}"
    if said:
        prompt += f"\n\nThe player said: {said}"
    yield from _checked(provider, check, NARRATE_SYSTEM, prompt, NARRATION_SENTENCES)


def voice_npc(
    provider: LLMProvider, check: FactCheck, context: Context, profile: str, said: str
) -> Iterator[Part]:
    """An NPC's answer to the player character, in character, streamed and fact-checked."""
    prompt = f"{context.render()}\n\nThe player character says: {said}"
    system = VOICE_SYSTEM.format(profile=profile)
    yield from _checked(provider, check, system, prompt, NPC_SENTENCES)


def answer_gm(
    provider: LLMProvider, check: FactCheck, context: Context, options: Options, question: str
) -> Iterator[Part]:
    """The GM's answer to the player, out of character, streamed and fact-checked. Unlike the
    narrator, the GM may talk about the rules."""
    prompt = f"{context.render()}\n\n{_render_options(options)}\n\nThe player asks: {question}"
    yield from _checked(provider, check, GM_SYSTEM, prompt, GM_SENTENCES, rules=True)


def _checked(
    provider: LLMProvider,
    check: FactCheck,
    system: str,
    prompt: str,
    sentences: int,
    rules: bool = False,
) -> Iterator[Part]:
    """Streams the reply, cut off after `sentences`; if it names what the prompt doesn't or
    talks about the rules (unless `rules` may be talked about), retracts it and asks once
    more, telling the model what to leave out. A second failure is retracted for good, and
    the engine's templated text stands alone."""
    messages = [Message("system", system), Message("user", prompt)]
    given = f"{system}\n{prompt}"
    for _ in range(2):
        told: list[str] = []
        stream = provider.stream(messages, temperature=NARRATE_TEMPERATURE)
        try:
            for chunk in _capped(stream, sentences):
                told.append(chunk)
                yield chunk
        except ProviderError:
            if told:
                yield Retract()
            return
        text = "".join(told)
        corrections = []
        if unknown := check.unknown_names(text, given):
            corrections.append(f"Do not mention {', '.join(unknown)}: they are not in this scene.")
        if not rules and rules_talk(text):
            corrections.append("Do not mention numbers, dice, HP, damage or stats.")
        if not corrections:
            return
        yield Retract()
        correction = " ".join(corrections)
        messages = [Message("system", system), Message("user", f"{prompt}\n\n{correction}")]


def _capped(chunks: Iterator[str], sentences: int) -> Iterator[str]:
    """The chunks up to the end of the `sentences`-th sentence; the rest is never read."""
    text = ""
    try:
        for chunk in chunks:
            start = len(text)
            text += chunk
            ends = [match.end() for match in _SENTENCE_END.finditer(text)]
            if len(ends) >= sentences:
                if last := text[start : ends[sentences - 1]]:
                    yield last
                return
            yield chunk
    finally:
        close = getattr(chunks, "close", None)
        if close is not None:
            close()


def _intent_schema(options: Options) -> Schema:
    stats = list(dict.fromkeys(stat for move in options.moves.values() for stat in move.stats))
    return {
        "type": "object",
        "properties": {
            "kind": {"enum": list(get_args(Kind))},
            "move_id": {"enum": [*options.moves, None]},
            "stat": {"enum": [*stats, None]},
            "target": {"enum": [*options.people, *options.places, *options.obstacles, None]},
            "then": {"enum": [*options.places, None]},
        },
        "required": ["kind", "move_id", "stat", "target", "then"],
    }


def _render_options(options: Options) -> str:
    lines = ["Moves:"]
    for move_id, move in options.moves.items():
        line = f"- {move_id}: {move.description}"
        if move.stats:
            line += f" (stat: {', '.join(move.stats)})"
        if move.targeted == "obstacle":
            line += " (aimed at an obstacle)"
        elif move.targeted:
            line += " (aimed at someone)"
        lines.append(line)
    lines += ["People here:", *(f"- {id}: {name}" for id, name in options.people.items())]
    lines += ["Places to go:", *(f"- {id}: {name}" for id, name in options.places.items())]
    if options.obstacles:
        obstacles = options.obstacles.items()
        lines += ["Obstacles here:", *(f"- {id}: {name}" for id, name in obstacles)]
    return "\n".join(lines)


def _read_intent(reply: str, options: Options) -> Intent | None:
    try:
        answer = json.loads(reply)
        kind = answer["kind"]
        move_id, stat, target = answer.get("move_id"), answer.get("stat"), answer.get("target")
        then = answer.get("then")
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    if not all(value is None or isinstance(value, str) for value in (move_id, stat, target, then)):
        return None
    match kind:
        case "move" if move_id in options.moves:
            move = options.moves[move_id]
            stat = stat if stat in move.stats else None
            then = then if then in options.places else None
            aims = {False: None, True: options.people, "obstacle": options.obstacles}
            targets = aims[move.targeted]
            if targets is None:
                return Intent(kind=kind, move_id=move_id, stat=stat, then=then)
            if target in targets:
                return Intent(kind=kind, move_id=move_id, stat=stat, target=target, then=then)
        case "travel" if target is None or target in options.places:
            return Intent(kind=kind, target=target)
        case "talk" if target in options.people:
            return Intent(kind=kind, target=target)
        case "look" | "inventory" | "ooc" | "unclear":
            return Intent(kind=kind)
    return None
