"""A tiny scenario on the Dungeon World pack, for tests."""

from pathlib import Path

from gminator.packs.models import Pack
from gminator.scenario.loader import load_scenario
from gminator.scenario.models import Scenario
from support import write_files

MANIFEST = """\
id: tiny-cellar
name: Tiny Cellar
version: 0.1.0
license: CC0
attribution: Written for tests
system: dungeon-world
start: inn
intro: You stand in the inn.
"""

LOCATIONS = """\
- id: inn
  name: The inn
  description: Warm and loud.
  exits: [cellar]
- id: cellar
  name: The cellar
  exits: [inn]
"""

NPCS = """\
- id: corwin
  name: Corwin
  location: inn
  max_hp: 8
  damage: d6
  knows: [wererat]
"""

SECRETS = """\
- id: wererat
  text: Corwin is a wererat.
"""

TAGS = """\
- {id: exposed, description: Unmasked before everyone.}
"""

FRONTS = """\
- id: undercellar
  name: The Undercellar
  impending_doom: The inn is overrun.
  dangers:
    - id: swarm
      name: The swarm
      type: horde
      impulse: to consume
      npc: corwin
      portents: [Rats in the pantry., A child is bitten.]
      moves:
        - id: rats_bite
          name: The rats bite
          severity: hard
          requires: {pc_at: cellar}
          effects:
            - take_damage: {amount: target.damage}
            - advance_clock: {clock: swarm}
"""

ENDINGS = """\
- id: overrun
  title: Overrun
  text: The rats win.
  when: {clock_full: swarm}
- id: exposed
  title: Exposed
  text: Corwin is unmasked.
  when: {npc_has_tag: {npc: corwin, tag: exposed}}
"""

UNMASK = """\
id: unmask
name: Unmask Corwin
category: special
trigger: When you reveal Corwin for what he is
requires: {secret_revealed: wererat}
target: true
roll: stat.cha
outcomes:
  strong:
    effects:
      - add_tag: {tag: exposed, target: target}
  partial:
    effects:
      - reveal_secret: wererat
  miss:
    effects:
      - move_to: {location: cellar}
"""

VALID = {
    "scenario.yaml": MANIFEST,
    "locations.yaml": LOCATIONS,
    "npcs.yaml": NPCS,
    "secrets.yaml": SECRETS,
    "tags.yaml": TAGS,
    "fronts.yaml": FRONTS,
    "endings.yaml": ENDINGS,
    "moves/unmask.yaml": UNMASK,
}


def load_tiny_cellar(root: Path, pack: Pack, files: dict[str, str] = VALID) -> Scenario:
    return load_scenario(write_files(root, files), pack)
