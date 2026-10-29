"""The fact check: flags AI text that names an NPC, place or item the prompt never gave it.

It knows every name the scenario and the pack use; a name in the text that the prompt does
not also contain is one the model brought in on its own. Names the scenario has never heard
of (an invented "Smaug") are beyond it.
"""

import re

from gminator.packs.models import Pack
from gminator.scenario.models import Scenario

_ARTICLE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


class FactCheck:
    def __init__(self, scenario: Scenario, rules: Pack) -> None:
        names = [
            *(npc.name for npc in scenario.npcs.values()),
            *(location.name for location in scenario.locations.values()),
            *(item.name for item in rules.items.values()),
        ]
        self._patterns = {name: _pattern(name) for name in dict.fromkeys(names)}

    def unknown_names(self, text: str, prompt: str) -> list[str]:
        """The names in `text` that `prompt` does not contain, in the order they are known."""
        return [
            name
            for name, pattern in self._patterns.items()
            if pattern.search(text) and not pattern.search(prompt)
        ]


def _pattern(name: str) -> re.Pattern[str]:
    core = _ARTICLE.sub("", name.strip())
    words = r"\s+".join(re.escape(word) for word in core.split())
    return re.compile(rf"\b{words}\b", re.IGNORECASE)
