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

Not every calc trainer appears there: some unnamed "[~ N]" entries do not.
Those get slotted in by ace level, which rises steadily along game order, so
they land in roughly the right stretch of the game rather than at the end.

build_trainers does the join, and tools/gen_dex.py reads it too so that the dex
and the Next button agree about where a trainer stands.
"""
import bisect
import collections
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(REPO, "js", "data", "trainer_order.js")


# the doc site spells a few things differently to the calc's set data
SPELLINGS = [
    ("PKMN ", "Pokémon "),
    ("Manaic", "Maniac"),
    ("Picknicker", "Picnicker"),
    ("Triathelete", "Triathlete"),
    (" and ", " & "),
]

# The calc's names carry the game's own gender symbols, which sit in the private
# use area and appear nowhere in the doc site's names: "Swimmer <U+E08F> Nicole"
# against "Swimmer Nicole". Dropping them matched another fifty trainers.
GENDER_GLYPHS = "\ue08e\ue08f"


def normalise(name):
    for wrong, right in SPELLINGS:
        name = name.replace(wrong, right)
    for glyph in GENDER_GLYPHS:
        name = name.replace(glyph, " ")
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


def base_name(name):
    """The name without its rematch counter: "Youngster Calvin3" -> the same
    trainer the doc site lists once, on the route where you first meet him."""
    return re.sub(r"\d+$", "", name).strip()


def calc_teams(key):
    """trainer name -> full team, from the calc's own set data.

    The doc site knows where a trainer stands and what species they field; only
    this knows their moves, abilities, items and natures.
    """
    with open(os.path.join(REPO, "backups", "%s.js" % key), encoding="utf-8") as f:
        raw = f.read()
    data = json.loads(raw[raw.index("{"):].rstrip().rstrip(";"))

    teams = collections.defaultdict(list)
    for species, sets in data["formatted_sets"].items():
        for set_name, entry in sets.items():
            m = re.match(r"^Lvl\s+(\d+)\s+(.*)$", set_name.strip())
            if not m:
                continue
            teams[m.group(2).strip()].append({
                "species": species,
                "level": entry.get("level", 0),
                "ability": entry.get("ability", ""),
                "item": entry.get("item", ""),
                "nature": entry.get("nature", ""),
                "moves": [mv for mv in (entry.get("moves") or []) if mv],
                "sub": entry.get("sub_index", 0),
                # what the calculator's opposing dropdown calls this set, which
                # is how a trainer here opens over there
                "value": "%s (%s)" % (species, set_name),
            })

    for team in teams.values():
        team.sort(key=lambda m: m["sub"])
    return teams


def build_trainers(key, areas):
    """Calc trainers grouped by the area you meet them in, in game order.

    Names alone are not enough to join the two sources: the doc site lists
    "Youngster Calvin" four times, once per route, while the calc calls those
    Calvin, Calvin2, Calvin3, Calvin4 with no hint of where any of them stand.
    So candidates are matched on the base name and then chosen by how well the
    species and levels line up, which is what actually distinguishes them.
    """
    teams = calc_teams(key)

    candidates = collections.defaultdict(list)
    for name in teams:
        candidates[normalise(base_name(name))].append(name)

    def keys_for(doc_name):
        stripped = exact_key(doc_name)
        return [stripped] + alias_keys(doc_name) + [normalise(base_name(stripped))]

    def score(name, wanted, ace):
        """Team overlap first, then closeness of level, then of size.

        A trainer's five rematch teams share his name and rarely a species, so
        overlap alone leaves them tied and the pick arbitrary: that is what put
        Rich Boy Winston's fourth rematch where his first battle belongs. Levels
        rise steadily across the tiers, so they order what species cannot.
        """
        got = {(m["species"], m["level"]) for m in teams[name]}
        mine = max(m["level"] for m in teams[name])
        return (len(got & wanted), -abs(mine - ace), -abs(len(teams[name]) - len(wanted)))

    taken, by_area = set(), []
    placement = {}
    for area in areas:
        rows = []
        for roster in (area.get("rosters") or []):
            title = roster.get("title") or "Trainers"
            for entry in (roster.get("trainers") or []):
                doc_name = entry.get("name") or ""
                team = entry.get("team")
                team = team if isinstance(team, list) else [team]
                team = [m for m in team if m]
                wanted = {(m.get("species"), m.get("level")) for m in team}
                ace = max([m.get("level") or 0 for m in team] or [0])

                pool = [n for k in keys_for(doc_name)
                        for n in candidates.get(k, []) if n not in taken]
                if not pool:
                    continue
                best = max(pool, key=lambda n: score(n, wanted, ace))
                taken.add(best)
                rows.append(best)
                placement[best] = {"area": area["name"], "roster": title,
                                   "rematch": roster.get("kind") == "rematch"}
        if rows:
            by_area.append({"name": area["name"], "trainers": rows})

    # Everything the doc site does not place: rematches beyond the appearances
    # it lists, and the unnamed "[~ N]" rom slots. Kept rather than dropped,
    # under a heading that says plainly they have no known location.
    rest = sorted((n for n in teams if n not in taken),
                  key=lambda n: (max(m["level"] for m in teams[n]), n))
    if rest:
        by_area.append({"name": "No listed location", "trainers": rest, "unplaced": True})

    trainers = {}
    for name, team in teams.items():
        where = placement.get(name) or {"area": "No listed location", "roster": ""}
        trainers[name] = {"name": name, "team": team,
                          "area": where["area"], "roster": where["roster"],
                          "rematch": bool(where.get("rematch"))}
    return trainers, by_area, len(taken)


def build(key, title, areas_path):
    with open(areas_path, encoding="utf-8") as f:
        areas = json.load(f)["areas"]

    trainers, by_area, matched = build_trainers(key, areas)
    aces = {name: max(m["level"] for m in t["team"]) for name, t in trainers.items()}
    playable = {name for name, t in trainers.items()
                if any(m["moves"] for m in t["team"])}

    ordered = [name for area in by_area if not area.get("unplaced")
               for name in area["trainers"]]
    placed = set(ordered)

    # Slot the rest by where their ace ranks among the placed trainers, rather
    # than by walking a running max of the sequence. A single name collision
    # would otherwise spike that running max and dump every later trainer into
    # one bucket. Ranking shifts by one position instead.
    placed_aces = sorted(aces[name] for name in ordered)

    leftovers = collections.defaultdict(list)
    for name, ace in sorted(aces.items(), key=lambda kv: (kv[1], kv[0])):
        if name in placed:
            continue
        leftovers[bisect.bisect_right(placed_aces, ace)].append(name)

    final = []
    for i, name in enumerate(ordered):
        final.extend(leftovers.get(i, []))
        final.append(name)
    final.extend(leftovers.get(len(ordered), []))

    # unused rom slots (every set moveless) go last, matching deriveTrainerOrder
    final = [n for n in final if n in playable] + [n for n in final if n not in playable]

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
    print("unused rom slots pushed to the end: %d" % (len(trainers) - len(playable)))
    assert len(final) == len(trainers), "lost trainers: %d vs %d" % (len(final), len(trainers))
    assert len(set(final)) == len(final), "duplicate trainers in order"
    print("wrote %s (%d trainers for %s)" % (DEST, len(final), title))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2], sys.argv[3])
