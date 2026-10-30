"""Eval cases: what to set up, what to ask the model, and what a good answer looks like.

Each task has its own file in the cases folder: classify.yaml, narrate.yaml and voice.yaml.
"""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

from gminator.ai.tasks import Kind
from gminator.packs.loader import Loader, PackError, unique


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Expected(_Model):
    """An intent a classify case accepts. A stat counts only if one is given; a place to go
    on to must match, so a case without one wants none."""

    kind: Kind
    move_id: str | None = None
    stat: str | None = None
    target: str | None = None
    then: str | None = None


class Scene(_Model):
    """Where a case happens: a quick-start character in a new game, then slash commands
    played to get there. Every command must change the game."""

    class_id: str = "fighter"
    seed: int = 0
    commands: list[str] = []


class ClassifyCase(_Model):
    id: str
    scene: Scene = Scene()
    said: str
    expect: list[Expected]
    """The intents that count as right; one is enough."""

    @field_validator("expect", mode="before")
    @classmethod
    def _one_or_more(cls, value: object) -> object:
        return [value] if isinstance(value, dict) else value


class NarrateCase(_Model):
    id: str
    scene: Scene = Scene()
    command: str
    """The slash command whose outcome is narrated."""
    said: str = ""
    """What the player said that led to the command."""
    mentions: list[str] = []
    """Words of which the narration should use at least one."""
    forbidden: list[str] = []
    """Words the narration must not use, such as a secret not yet revealed."""


class VoiceCase(_Model):
    id: str
    scene: Scene = Scene()
    npc: str
    said: str
    mentions: list[str] = []
    forbidden: list[str] = []


@dataclass(frozen=True)
class Cases:
    classify: list[ClassifyCase] = field(default_factory=list)
    narrate: list[NarrateCase] = field(default_factory=list)
    voice: list[VoiceCase] = field(default_factory=list)


def load_cases(root: Path) -> Cases:
    """The cases in `root`, reporting every problem with its file and line."""
    loader = Loader()
    located = {
        "classify": loader.many(root / "classify.yaml", ClassifyCase),
        "narrate": loader.many(root / "narrate.yaml", NarrateCase),
        "voice": loader.many(root / "voice.yaml", VoiceCase),
    }
    for task, cases in located.items():
        unique(cases, f"{task} case", loader.problems)
    if loader.problems:
        raise PackError(loader.problems)
    return Cases(**{task: [c.model for c in cases] for task, cases in located.items()})
