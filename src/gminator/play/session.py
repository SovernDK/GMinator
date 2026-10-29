"""The turn controller for play without AI: slash commands in, templated text out.

Each command that changes the game runs as one turn: the player's action, the GM moves it
calls for, the dying move if the player character dropped to 0 HP, and the ending if one is
reached. A turn is recorded whole or not at all.
"""

from collections.abc import Callable, Sequence
from typing import Literal

from gminator.core.conditions import holds, is_dead
from gminator.core.events import (
    CharacterCreated,
    CharacterMoved,
    ChoiceMade,
    ClockAdvanced,
    Event,
    ForwardChanged,
    GameEnded,
    GmMoveMade,
    GmMoveTriggered,
    HoldChanged,
    HpChanged,
    ItemGained,
    ItemUsed,
    MoveMade,
    QuestionsAsked,
    SecretRevealed,
    TagAdded,
    TagRemoved,
    XpMarked,
)
from gminator.core.game import Game
from gminator.core.moves import Decider, ResolveError, armor, resolve_move
from gminator.core.state import GameState, ReplayError, apply
from gminator.packs.models import Move, Pack
from gminator.play.text import t
from gminator.scenario.gm import make_scenario_gm_move
from gminator.scenario.graph import build_graph
from gminator.scenario.models import Ending, Scenario, ScenarioMove
from gminator.scenario.story import opening_events, reached_ending

Availability = Literal["yes", "never", "not_now"]


class Session:
    def __init__(self, game: Game, pack: Pack, scenario: Scenario, pc_id: str) -> None:
        self.game = game
        self.scenario = scenario
        self.rules = scenario.ruleset(pack)
        self.pc_id = pc_id
        self._gm_moves = dict(pack.gm_moves)
        self._portents: dict[str, list[str]] = {}
        for danger in scenario.dangers():
            self._gm_moves |= {gm_move.id: gm_move for gm_move in danger.moves}
            self._portents[danger.id] = danger.portents
        self._commands: dict[str, Callable[[list[str], Decider], list[str]]] = {
            "help": lambda args, decider: [t("command.help")],
            "look": lambda args, decider: self._look(),
            "go": self._go,
            "moves": lambda args, decider: self._moves(),
            "move": self._move,
            "sheet": lambda args, decider: self._sheet(),
            "clocks": lambda args, decider: self._clocks(),
            "secrets": lambda args, decider: self._secrets(),
        }

    @classmethod
    def begin(
        cls, pack: Pack, scenario: Scenario, seed: int, character: Sequence[Event]
    ) -> "Session":
        """A new game: the player character's creation events, then the scenario's opening."""
        created = character[0]
        assert isinstance(created, CharacterCreated)
        game = Game.new(seed)
        for event in (*character, *opening_events(scenario, created.character_id)):
            game.record(event)
        return cls(game, pack, scenario, created.character_id)

    @property
    def state(self) -> GameState:
        return self.game.state

    @property
    def ending(self) -> Ending | None:
        return next((e for e in self.scenario.endings if e.id == self.state.ending), None)

    def opening(self) -> list[str]:
        intro = self.scenario.manifest.intro
        return [intro, *self._look()] if intro else self._look()

    def handle(self, line: str, decider: Decider) -> list[str]:
        line = line.strip()
        if not line.startswith("/"):
            return [t("command.free_text")]
        command, *args = line[1:].split() or [""]
        handler = self._commands.get(command)
        if handler is None:
            return [t("command.unknown", command=f"/{command}")]
        return handler(args, decider)

    # Commands that change the game

    def _go(self, args: list[str], decider: Decider) -> list[str]:
        if not args:
            return [t("command.go_where")]
        place = args[0]
        if place not in self.scenario.locations[self._pc_location()].exits:
            return [t("command.no_exit", place=place)]
        lines = self._turn(
            lambda game: game.record(CharacterMoved(character_id=self.pc_id, location_id=place)),
            decider,
        )
        return lines if self.state.ending else [*lines, *self._look()]

    def _move(self, args: list[str], decider: Decider) -> list[str]:
        if not args:
            return [t("command.move_which")]
        move_id, *rest = args
        move = self.rules.moves.get(move_id)
        availability = self._availability(move) if move else "never"
        if availability == "never":
            return [t("command.no_move", move=move_id)]
        assert move is not None
        if availability == "not_now":
            return [t("command.not_now", move=move.name)]

        stats = self.rules.manifest.stats
        stat = next((arg for arg in rest if arg in stats), None)
        target = next((arg for arg in rest if arg not in stats), None)
        if target is not None:
            character = self.state.characters.get(target)
            if character is None or target == self.pc_id:
                return [t("command.no_target", target=target)]
            if character.location != self._pc_location():
                return [t("command.not_here", target=character.name)]

        return self._turn(
            lambda game: resolve_move(
                game, self.rules, move_id, self.pc_id, decider, target_id=target, stat=stat
            ),
            decider,
        )

    def _turn(self, act: Callable[[Game], object], decider: Decider) -> list[str]:
        if self.state.ending is not None:
            assert self.ending is not None
            return [t("command.ended", title=self.ending.title)]
        scratch = Game(self.game.events)
        start = len(scratch.events)
        try:
            act(scratch)
            self._aftermath(scratch, start, decider)
        except (ResolveError, ReplayError) as error:
            return [t("command.failed", reason=error)]
        before = self.state
        events = scratch.events[start:]
        for event in events:
            self.game.record(event)
        return self._render(events, before)

    def _aftermath(self, game: Game, start: int, decider: Decider) -> None:
        index = start
        dying_move = self.rules.manifest.dying_move
        dying_move_made = False
        while True:
            while index < len(game.events):
                event = game.events[index]
                if isinstance(event, GmMoveTriggered):
                    make_scenario_gm_move(
                        game, self.rules, self.scenario, self.pc_id, event.severity, decider
                    )
                index += 1
            pc = game.state.characters[self.pc_id]
            if dying_move is None or dying_move_made or pc.hp > 0 or "dead" in pc.tags:
                break
            resolve_move(game, self.rules, dying_move, self.pc_id, decider)
            dying_move_made = True
        ending = reached_ending(self.scenario, game.state, self.pc_id)
        if ending is not None:
            game.record(GameEnded(ending_id=ending.id))

    def available_moves(self) -> list[Move]:
        """The moves the player character can make right now."""
        return [m for m in self.rules.moves.values() if self._availability(m) == "yes"]

    def _availability(self, move: Move) -> Availability:
        if move.id == self.rules.manifest.dying_move:
            return "never"
        if move.category == "class":
            class_id = self.state.characters[self.pc_id].class_id
            cls = self.rules.classes.get(class_id) if class_id else None
            if cls is None or move.id not in cls.moves:
                return "never"
        requires = move.requires if isinstance(move, ScenarioMove) else None
        if requires is not None and not holds(requires, self.state, self.pc_id):
            return "not_now"
        return "yes"

    # Commands that only tell

    def _look(self) -> list[str]:
        location = self.scenario.locations[self._pc_location()]
        graph = build_graph(self.scenario, self.state, self.pc_id)
        lines = [t("look.location", name=location.name)]
        if location.description:
            lines.append(location.description)
        exits = [
            t("look.named", name=e.name, id=e.id) for e in graph.objects(location.id, "connects")
        ]
        lines.append(t("look.exits", exits=", ".join(exits)) if exits else t("look.no_exits"))
        here = []
        for entity in graph.subjects("at", location.id):
            if entity.id == self.pc_id:
                continue
            named = t("look.named", name=entity.name, id=entity.id)
            dead = is_dead(self.state.characters[entity.id])
            here.append(t("look.dead", name=named) if dead else named)
        if here:
            lines.append(t("look.here", characters=", ".join(here)))
        return lines

    def _moves(self) -> list[str]:
        return [
            t("moves.title"),
            *(
                t("moves.move", id=m.id, name=m.name, trigger=m.trigger)
                for m in self.available_moves()
            ),
        ]

    def _sheet(self) -> list[str]:
        pc = self.state.characters[self.pc_id]
        cls = self.rules.classes.get(pc.class_id) if pc.class_id else None
        stats = ", ".join(f"{name} {value:+d}" for name, value in pc.stats.items())
        lines = [
            t("sheet.title", name=pc.name, class_name=cls.name if cls else ""),
            t(
                "sheet.hp",
                hp=pc.hp,
                max_hp=pc.max_hp,
                armor=armor(self.rules, pc),
                xp=pc.xp,
                level=pc.level,
            ),
            t("sheet.stats", stats=stats),
        ]
        if pc.forward:
            lines.append(t("sheet.forward", forward=pc.forward))
        if pc.hold:
            hold = ", ".join(f"{self._move_name(m)} {n}" for m, n in pc.hold.items())
            lines.append(t("sheet.hold", hold=hold))
        if pc.tags:
            lines.append(t("sheet.tags", tags=", ".join(pc.tags)))
        items = [
            t("sheet.uses", name=self._item_name(p.item_id), uses=p.uses)
            if p.uses is not None
            else self._item_name(p.item_id)
            for p in pc.inventory
        ]
        lines.append(t("sheet.inventory", items=", ".join(items) or t("sheet.nothing")))
        return lines

    def _clocks(self) -> list[str]:
        lines = []
        for danger_id, portents in self._portents.items():
            clock = self.state.clocks[danger_id]
            lines.append(
                t("clocks.clock", label=clock.label, filled=clock.filled, segments=clock.segments)
            )
            lines += [t("clocks.portent", portent=p) for p in portents[: clock.filled]]
        return lines or [t("clocks.none")]

    def _secrets(self) -> list[str]:
        texts = [self.scenario.secrets[secret_id].text for secret_id in self.state.revealed]
        return [t("secrets.secret", text=text) for text in texts] or [t("secrets.none")]

    # Templated text for events

    def _render(self, events: Sequence[Event], state: GameState) -> list[str]:
        lines: list[str] = []
        for event in events:
            after = apply(state, event)
            lines += self._describe(event, state, after)
            state = after
        return lines

    def _describe(self, event: Event, before: GameState, after: GameState) -> list[str]:
        def who(character_id: str) -> str:
            return after.characters[character_id].name

        match event:
            case MoveMade(band=None):
                move = self.rules.moves[event.move_id]
                return _texts(
                    t("event.made", who=who(event.character_id), move=move.name), move.text
                )
            case MoveMade(band=band):
                move = self.rules.moves[event.move_id]
                assert move.outcomes is not None
                rolled = t(
                    "event.rolled",
                    who=who(event.character_id),
                    move=move.name,
                    total=event.total,
                    band=t(f"band.{band}"),
                )
                return _texts(rolled, getattr(move.outcomes, band).text)
            case HpChanged(character_id=character_id, amount=amount):
                character = after.characters[character_id]
                values = {"who": character.name, "hp": character.hp, "max_hp": character.max_hp}
                if amount < 0:
                    lines = [t("event.damage", amount=-amount, **values)]
                elif amount == 0:
                    lines = [t("event.no_damage", who=character.name)]
                else:
                    lines = [t("event.healed", amount=amount, **values)]
                if character.hp == 0 < before.characters[character_id].hp:
                    lines.append(t("event.down", who=character.name))
                return lines
            case XpMarked():
                return [t("event.xp", who=who(event.character_id), amount=event.amount)]
            case ClockAdvanced(clock_id=clock_id):
                clock = after.clocks[clock_id]
                portents = self._portents.get(clock_id, [])
                filled = range(before.clocks[clock_id].filled, min(clock.filled, len(portents)))
                return [
                    t(
                        "event.clock",
                        label=clock.label,
                        filled=clock.filled,
                        segments=clock.segments,
                    ),
                    *(t("event.portent", portent=portents[i]) for i in filled),
                ]
            case TagAdded():
                tag = self.rules.tags.get(event.tag)
                description = tag.description if tag else event.tag
                return [t("event.tagged", who=who(event.character_id), description=description)]
            case TagRemoved():
                return [t("event.untagged", who=who(event.character_id), tag=event.tag)]
            case HoldChanged(amount=amount):
                key = "event.hold_gained" if amount > 0 else "event.hold_spent"
                move = self._move_name(event.move_id)
                return [t(key, who=who(event.character_id), amount=abs(amount), move=move)]
            case ForwardChanged():
                return [t("event.forward", who=who(event.character_id), amount=event.amount)]
            case ItemGained():
                item = self._item_name(event.item_id)
                return [t("event.item_gained", who=who(event.character_id), item=item)]
            case ItemUsed():
                item = self._item_name(event.item_id)
                return [t("event.item_used", who=who(event.character_id), item=item)]
            case ChoiceMade():
                return [t("event.chosen", chosen="; ".join(event.chosen))]
            case QuestionsAsked():
                return [
                    t("event.asked", who=who(event.character_id), question=question)
                    for question in event.questions
                ]
            case SecretRevealed(secret_id=secret_id):
                if secret_id in before.revealed:
                    return []
                return [t("event.secret", text=self.scenario.secrets[secret_id].text)]
            case CharacterMoved():
                location = self.scenario.locations[event.location_id].name
                return [t("event.moved", who=who(event.character_id), location=location)]
            case GmMoveMade():
                gm_move = self._gm_moves[event.gm_move_id]
                return [t("event.gm_move", name=gm_move.name, text=gm_move.text)]
            case GameEnded():
                ending = next(e for e in self.scenario.endings if e.id == event.ending_id)
                return [t("event.ending", title=ending.title), ending.text]
        return []

    def _pc_location(self) -> str:
        location = self.state.characters[self.pc_id].location
        assert location is not None
        return location

    def _move_name(self, move_id: str) -> str:
        move = self.rules.moves.get(move_id)
        return move.name if move else move_id

    def _item_name(self, item_id: str) -> str:
        item = self.rules.items.get(item_id)
        return item.name if item else item_id


def _texts(*texts: str) -> list[str]:
    return [text for text in texts if text]
