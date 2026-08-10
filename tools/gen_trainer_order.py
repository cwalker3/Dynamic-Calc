"""Builds an explicit trainer order for a calc, from a Nuzlocke Documentation
Site areas.json.

    python3 tools/gen_trainer_order.py <backup-key> "<title>" <areas.json>

Appends/updates js/data/trainer_order.js, which both showdown_hooks.js
(deriveTrainerOrder) and tools/gen_mastersheet.py read. Emitting one list that
both consume is the point: the mastersheet indexes trainers by position, so if
the two ever disagree the Next button silently loads the wrong trainer.

The calc data carries no field for where you meet a trainer. class_id is the
trainer class and p_id is the lead's species, so order has to come from
somewhere else. areas.json lists areas in game order with their rosters, which
is exactly that missing information.

Not every calc trainer appears there: rematches and unnamed "[~ N]" entries do
not. Those get slotted in by ace level, which rises steadily along game order,
so they land in roughly the right stretch of the game rather than at the end.
"""
import bisect
import collections
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(REPO, "js", "data", "trainer_order.js")


def calc_trainers(key):
    """trainer name -> ace level, from the calc's own set data."""
    with open(os.path.join(REPO, "backups", "%s.js" % key), encoding="utf-8") as f:
        raw = f.read()
    data = json.loads(raw[raw.index("{"):].rstrip().rstrip(";"))

    levels = collections.defaultdict(list)
    for sets in data["formatted_sets"].values():
        for set_name in sets:
            m = re.match(r"^Lvl\s+(\d+)\s+(.*)$", set_name.strip())
            if m:
                levels[m.group(2).strip()].append(int(m.group(1)))
    return {name: max(lv) for name, lv in levels.items()}


# the doc site spells a few things differently to the calc's set data
SPELLINGS = [
    ("PKMN ", "Pokémon "),
    ("Manaic", "Maniac"),
    ("Picknicker", "Picnicker"),
    (" and ", " & "),
]


def normalise(name):
    for wrong, right in SPELLINGS:
        name = name.replace(wrong, right)
    return re.sub(r"\s+", " ", name).strip().lower()


def exact_key(name):
    """The name with any "[Diantha]" style note stripped."""
    return normalise(re.sub(r"\s*\[[^\]]*\]\s*$", "", name))


def alias_keys(name):
    """Disguised trainers are written "Leader Carnation [Roxanne]". The bracket
    names who they actually are, which is how the calc lists them."""
    m = re.match(r"^(.*?)\s*\[([^\]]+)\]\s*$", normalise(name))
    if not m:
        return []

    stripped, alias = m.group(1).strip(), m.group(2).strip()
    keys = [alias]
    parts = stripped.rsplit(" ", 1)
    if len(parts) == 2:
        keys.insert(0, parts[0] + " " + alias)   # keep the trainer class
    return keys


def doc_order(areas_path, trainers):
    """Calc trainer names in game order, for those the doc site lists."""
    with open(areas_path, encoding="utf-8") as f:
        areas = json.load(f)["areas"]

    by_norm = collections.defaultdict(list)
    for name in trainers:
        by_norm[normalise(name)].append(name)

    entries = [trainer.get("name") or ""
               for area in areas
               for roster in (area.get("rosters") or [])
               for trainer in (roster.get("trainers") or [])]

    placed, ordered = set(), []

    def place(key):
        if key not in by_norm:
            return False
        names = [n for n in by_norm[key] if n not in placed]
        if not names:
            return False
        placed.update(names)
        ordered.append((key, sorted(names)))
        return True

    # Exact names first, across the whole game, before any alias is considered.
    # The rematch facility fields disguised gym leaders ("Leader Antonin
    # [Norman]"), and letting that alias land first would drag Norman's gym
    # battle to wherever the facility appears.
    for name in entries:
        place(exact_key(name))

    # second pass fills the gaps, keeping doc order among what is left
    resolved = {}
    for i, name in enumerate(entries):
        for key in alias_keys(name):
            if key in by_norm and key not in resolved and place(key):
                resolved[key] = i
                break

    # first occurrence wins: gym leaders show up again in the rematch facility
    # late in the file, and taking the last position would sort them to the end
    order_of = {}
    for i, name in enumerate(entries):
        for key in [exact_key(name)] + alias_keys(name):
            order_of.setdefault(key, i)

    ordered.sort(key=lambda kv: order_of.get(kv[0], len(entries)))

    return [name for _, names in ordered for name in names]


def build(key, title, areas_path):
    trainers = calc_trainers(key)
    ordered = doc_order(areas_path, trainers)
    placed = set(ordered)

    # Slot the rest by where their ace ranks among the placed trainers, rather
    # than by walking a running max of the sequence. A single name collision
    # (the doc site lists an early route Rich Boy Winston, the calc only has his
    # level 75 rematch) would otherwise spike that running max and dump every
    # later trainer into one bucket. Ranking shifts by one position instead.
    placed_aces = sorted(trainers[name] for name in ordered)

    leftovers = collections.defaultdict(list)
    for name, ace in sorted(trainers.items(), key=lambda kv: (kv[1], kv[0])):
        if name in placed:
            continue
        leftovers[bisect.bisect_right(placed_aces, ace)].append(name)

    final = []
    for i, name in enumerate(ordered):
        final.extend(leftovers.get(i, []))
        final.append(name)
    final.extend(leftovers.get(len(ordered), []))

    orders = {}
    if os.path.exists(DEST):
        with open(DEST, encoding="utf-8") as f:
            existing = f.read()
        m = re.search(r"trainerOrders = (\{.*\})", existing, re.S)
        if m:
            orders = json.loads(m.group(1))
    orders[title] = final

    with open(DEST, "w", encoding="utf-8") as f:
        f.write("// Trainer order in the sequence you meet them.\n")
        f.write("// Generated by tools/gen_trainer_order.py - do not hand edit.\n")
        f.write("// Read by deriveTrainerOrder in js/showdown_hooks.js and by\n")
        f.write("// tools/gen_mastersheet.py, which must agree on positions.\n\n")
        f.write("trainerOrders = " + json.dumps(orders, ensure_ascii=False, indent=1) + "\n")

    print("calc trainers: %d" % len(trainers))
    print("placed from areas.json: %d" % len(ordered))
    print("slotted by ace level: %d" % (len(final) - len(ordered)))
    assert len(final) == len(trainers), "lost trainers: %d vs %d" % (len(final), len(trainers))
    assert len(set(final)) == len(final), "duplicate trainers in order"
    print("wrote %s (%d trainers for %s)" % (DEST, len(final), title))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2], sys.argv[3])
