"""Generates a trainers mastersheet page from a calc's backup data.

    python3 tools/gen_mastersheet.py <backup-key> "<title>"
    python3 tools/gen_mastersheet.py rrss "Rising Ruby/Sinking Saphire"

Writes <backup-key>_mastersheet.html next to index.html.

The existing mastersheets were exported from hzla's Pokeweb, which only covers
gen 4/5, so gen 6 calcs have no way to get one. This builds the equivalent page
straight from backups/<key>.js instead: same class names and data attributes, so
the sidebar wiring in *_mastersheet_files/mastersheet.js works untouched.

The page is index.html plus a #content-container holding the sidebar and the
trainer document. Tab toggles between the two, which is what showdown_hooks.js
already does when the url contains "mastersheet".

Encounters are deliberately absent: the gen 6 backups carry no wild data, and a
half-populated encounters tab would be worse than none.
"""
import collections
import html
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# assets the mastersheet needs on top of what index.html already pulls in.
# Reused from an existing mastersheet rather than duplicated.
MASTERSHEET_CSS = [
    "./bb2redux_mastersheet_files/main.css",
    "./bb2redux_mastersheet_files/mastersheet.css",
]
MASTERSHEET_JS = ["./sterlingsilver_mastersheet_files/mastersheet.js"]

TYPES = ["normal", "fire", "water", "electric", "grass", "ice", "fighting",
         "poison", "ground", "flying", "psychic", "bug", "rock", "ghost",
         "dragon", "dark", "steel", "fairy"]


def read_backup(key):
    path = os.path.join(REPO, "backups", "%s.js" % key)
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    return json.loads(raw[raw.index("{"):].rstrip().rstrip(";"))


def read_move_ids():
    """name -> id, from the generated gen 6 constants."""
    path = os.path.join(REPO, "js", "save_constants", "gen6.js")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"g6_moves = \[(.*?)\n\]", src, re.S)
    if not m:
        return {}
    names = json.loads("[" + m.group(1).rstrip().rstrip(",") + "]")
    return {n: i for i, n in enumerate(names)}


def read_splits(title):
    """The gym/level-cap sections the fragsheet already defines for this game."""
    path = os.path.join(REPO, "calc", "data", "splits.js")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r'"%s":\s*\{(.*?)\n\t\}' % re.escape(title), src, re.S)
    if not m:
        return [], []
    body = m.group(1)
    titles = re.search(r'"titles":\s*\[(.*?)\]', body, re.S)
    lvls = re.search(r'"lvls":\s*\[(.*?)\]', body, re.S)
    titles = re.findall(r'"([^"]*)"', titles.group(1)) if titles else []
    lvls = [int(x) for x in re.findall(r"\d+", lvls.group(1))] if lvls else []
    return titles, lvls


def slug(name):
    """Matches the sprite naming the calc uses elsewhere."""
    return (name.lower().replace(" ", "-").replace(".", "").replace("’", "")
            .replace("'", "").replace(":", "-").replace("*", "+"))


def sprite(name):
    rel = "img/pokesprite/%s.png" % slug(name)
    if os.path.exists(os.path.join(REPO, rel)):
        return "./" + rel
    return "./img/pokesprite/0.png"


def esc(value):
    return html.escape(str(value), quote=True)


def group_trainers(data):
    """formatted_sets is keyed species -> "Lvl N Trainer" -> set. Invert it."""
    trainers = collections.defaultdict(list)
    for species, sets in data["formatted_sets"].items():
        for set_name, entry in sets.items():
            m = re.match(r"^Lvl\s+(\d+)\s+(.*)$", set_name.strip())
            if not m:
                continue
            trainers[m.group(2).strip()].append({
                "species": species,
                "level": int(m.group(1)),
                "set_name": set_name,
                "sub_index": entry.get("sub_index", 0),
                "entry": entry,
            })
    for team in trainers.values():
        team.sort(key=lambda p: (p["sub_index"], p["level"]))
    return trainers


def render_mon(mon, data, move_ids):
    entry = mon["entry"]
    species = mon["species"]
    dex_id = data["poks"].get(species, {}).get("id", 0)

    item = entry.get("item") or "-"
    nature = entry.get("nature") or "-"
    ability = entry.get("ability") or "-"

    moves = []
    for move in (entry.get("moves") or [])[:4]:
        move = move or "-"
        moves.append('<div class="trpok-item-info doc-move" data-id="%d">%s</div>'
                     % (move_ids.get(move, 0), esc(move)))
    while len(moves) < 4:
        moves.append('<div class="trpok-item-info doc-move" data-id="0">-</div>')

    return """      <div class="trainer-doc-item">
        <img src="%s" class="doc-sprite" loading="lazy" data-species-id="%d">
        <div class="trpok-item-info doc-species" data-species-id="%d">Lvl %d %s</div>
        <div class="trpok-item-info">%s</div>
        <div class="trpok-item-info">%s</div>
        <div class="trpok-item-info">%s</div>
        <br>
%s
      </div>
""" % (sprite(species), dex_id, dex_id, mon["level"], esc(species),
       esc(item), esc(nature), esc(ability), "\n".join("        " + m for m in moves))


def render_trainer(index, name, team, data, move_ids):
    lead = team[0]["species"] if team else ""
    mons = "".join(render_mon(m, data, move_ids) for m in team)
    return """  <div class="expanded-field filterable ms-trainer" data-index="%d">
    <div class="expanded-field-main">
      <div class="trainer-name"><img src="%s" class="" loading="lazy"> %s</div>
    </div>
    <div class="expanded-card-content expanded-docs">
%s    </div>
  </div>
""" % (index, sprite(lead), esc(name), mons)


def render_document(title, trainers, data, move_ids, splits):
    section_titles, caps = splits
    # must match deriveTrainerOrder in js/showdown_hooks.js exactly: the calc
    # indexes customLeads by that order, and .trainer-name clicks look it up by
    # this data-index. Lowest level first, plain code point order on ties.
    ordered = sorted(trainers.items(), key=lambda kv: (max(p["level"] for p in kv[1]), kv[0]))
    tr_ids = {name: i for i, (name, _) in enumerate(ordered)}

    # bucket trainers by the level cap they fall under, so the page reads in
    # roughly the order you meet them
    buckets = collections.OrderedDict()
    for i, cap in enumerate(caps):
        label = section_titles[i] if i < len(section_titles) else "Cap %d" % cap
        buckets["%s (cap: %d)" % (label, cap)] = []
    buckets["Post Game"] = []

    for name, team in ordered:
        # the ace decides which cap section a trainer belongs to, for the same
        # reason it decides the order
        high = max(p["level"] for p in team)
        placed = False
        for i, cap in enumerate(caps):
            if high <= cap:
                label = section_titles[i] if i < len(section_titles) else "Cap %d" % cap
                buckets["%s (cap: %d)" % (label, cap)].append((name, team))
                placed = True
                break
        if not placed:
            buckets["Post Game"].append((name, team))

    out = ['<div class="pokemon-list spreadsheet" id="mastersheet">', "<h1>%s</h1>" % esc(title)]
    for label, group in buckets.items():
        if not group:
            continue
        out.append("<h1>%s</h1>" % esc(label))
        for name, team in group:
            out.append(render_trainer(tr_ids[name], name, team, data, move_ids))
    out.append("</div>")
    return "\n".join(out)


def render_species_panels(data):
    panels = []
    for name, pok in sorted(data["poks"].items(), key=lambda kv: kv[1].get("id", 0)):
        dex_id = pok.get("id", 0)
        types = pok.get("types") or ["Normal"]
        abilities = pok.get("abilities") or []
        bs = pok.get("bs") or {}

        type_html = "".join(
            '<div class="pokemon-type -%s">%s</div>' % (esc(t.lower()), esc(t))
            for t in types)
        ability_html = "".join(
            '<div class="pokemon-card__ability">%d: %s</div>' % (i + 1, esc(a))
            for i, a in enumerate(abilities[:3])) or '<div class="pokemon-card__ability">-</div>'

        rows = []
        for label, key in [("HP", "hp"), ("Attack", "at"), ("Defense", "df"),
                           ("Sp. Atk", "sa"), ("Sp. Def", "sd"), ("Speed", "sp")]:
            value = bs.get(key, 0)
            rows.append("""        <tr><td><strong>%s</strong></td><td>%d</td>
          <td><div class="pokemon-card__graph-wrapper">
            <div class="pokemon-card__graph -medium" style="width: calc(100%% * (%d / 255));"></div>
          </div></td></tr>""" % (label, value, value))

        panels.append("""<div class="ms-pok" data-species-id="%d" data-species-name="%s">
  <div class="pokemon-card__info">
    <div class="ms-enc-header">%s</div>
    <div class="pokemon-types">%s</div>
    <div class="pokemon-card__abilities">%s</div>
  </div>
  <table class="pokemon-card__table" cellspacing="0"><tbody>
%s
  </tbody></table>
</div>""" % (dex_id, esc(name), esc(name), type_html, ability_html, "\n".join(rows)))

        learnset = pok.get("learnset_info") or []
        if learnset:
            rows = "".join(
                '<div class="expanded-field"><div class="enc-lvl">%s</div>'
                '<div class="enc-name">%s</div></div>' % (esc(lv), esc(mv))
                for lv, mv in learnset)
            panels.append(
                '<div class="expanded-card-content expanded-learnset ms-pok" '
                'data-species-id="%d" data-species-name="%s"><div class="expanded-left">%s</div></div>'
                % (dex_id, esc(name), rows))
    return "\n".join(panels)


def render_move_panels(data, move_ids):
    panels = []
    for name, move in sorted(data["moves"].items(), key=lambda kv: move_ids.get(kv[0], 0)):
        mtype = (move.get("type") or "Normal")
        panels.append("""<div class="expanded-field filterable ms-move" data-move-id="%d">
  <div class="expanded-field-main">
    <div class="move-name">%s</div>
    <div class="move-type"><div class="btn -%s -active" type="button">%s</div></div>
    <div class="move-power">%s</div>
    <div class="move-accuracy">%s</div>
  </div>
</div>""" % (move_ids.get(name, 0), esc(name), esc(mtype.lower()), esc(mtype[:3]),
             esc(move.get("basePower", 0)), esc(move.get("category", "-"))))
    return "\n".join(panels)


def build(key, title):
    data = read_backup(key)
    move_ids = read_move_ids()
    splits = read_splits(title)
    trainers = group_trainers(data)

    with open(os.path.join(REPO, "index.html"), encoding="utf-8") as f:
        shell = f.read()

    head = "".join('    <link type="text/css" rel="stylesheet" href="%s" />\n' % c
                   for c in MASTERSHEET_CSS)
    head += "".join('    <script type="text/javascript" src="%s"></script>\n' % j
                    for j in MASTERSHEET_JS)
    shell = shell.replace("</head>", head + "</head>", 1)

    autofills = {
        "true_pokemon_names": [n for n, _ in sorted(data["poks"].items(),
                                                    key=lambda kv: kv[1].get("id", 0))],
        "move_names": [n for n, _ in sorted(data["moves"].items(),
                                            key=lambda kv: move_ids.get(kv[0], 0))],
    }

    content = """
<div id="content-container">
  <script>autofills = %s;</script>
  <div class="pokemon-filter master-sidebar" style="top: 0px">
    <div class="filter-title">Lookup</div>
    <input class="" placeholder="Species or move name">
%s
%s
  </div>
%s
</div>
""" % (json.dumps(autofills, ensure_ascii=False),
       render_move_panels(data, move_ids),
       render_species_panels(data),
       render_document(title, trainers, data, move_ids, splits))

    shell = shell.replace("</body>", content + "</body>", 1)

    dest = os.path.join(REPO, "%s_mastersheet.html" % key)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(shell)

    print("trainers: %d" % len(trainers))
    print("species panels: %d" % len(data["poks"]))
    print("move panels: %d" % len(data["moves"]))
    print("sections: %s" % ", ".join(t for t in splits[0]) if splits[0] else "(no splits found)")
    print("wrote %s (%.1f MB)" % (dest, os.path.getsize(dest) / 1024 / 1024))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2])
