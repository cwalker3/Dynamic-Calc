"""Builds a dex overlay page for a calc, from a Nuzlocke Documentation Site.

    python3 tools/gen_dex.py <backup-key> "<title>" <hack-data-dir>
    python3 tools/gen_dex.py rrss "Rising Ruby/Sinking Saphire" ".../docs/data/hacks/rrss"

Writes <backup-key>_mastersheet.html, the name MASTERSHEETS in showdown_hooks.js
already points at.

Three panes, like the Decomps dex: a list of mons/areas/moves on the left, the
selected species in the middle, its learnset on the right. The data comes from
the documentation site rather than backups/<key>.js, because only the doc site
carries move accuracy and PP, stat changes and evolutions.

The page is index.html plus a launcher and a fixed overlay. It deliberately
does not touch body padding or anything else in the calculator's own layout:
the calculator's header is absolutely positioned, so shifting the flow leaves
the two overlapping.
"""
import collections
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_trainer_order as order          # noqa: E402  (shares the name matching)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# how the calc writes the game's gender symbols, which sit in the private use
# area and render as tofu in a browser
GENDER_DISPLAY = {"\ue08e": "♂", "\ue08f": "♀"}

TYPE_COLOURS = {
    "normal": "#9099a1", "fire": "#ff9d55", "water": "#4d90d5", "electric": "#f4d23c",
    "grass": "#63bc5a", "ice": "#73cec0", "fighting": "#ce4069", "poison": "#ab6ac8",
    "ground": "#d97845", "flying": "#8fa8dd", "psychic": "#fa7179", "bug": "#90c12c",
    "rock": "#c7b78b", "ghost": "#5269ac", "dragon": "#0b6dc3", "dark": "#5a5465",
    "steel": "#5a8ea1", "fairy": "#ec8fe6",
}


def esc(v):
    return html.escape(str(v), quote=True)


def slug(name):
    return (name.lower().replace(" ", "-").replace(".", "").replace("’", "")
            .replace("'", "").replace(":", "-").replace("*", "+"))


def load(path, name):
    with open(os.path.join(path, name), encoding="utf-8") as f:
        return json.load(f)


def move_id(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def fix_text(value):
    """Undo the double encoding in 160 of the move descriptions, where an
    apostrophe reads as a-hat-euro-tm. The text was encoded as UTF-8 and then
    read back as cp1252, so encoding it back to cp1252 and decoding as UTF-8
    puts it right. Text that is already correct does not survive the round trip
    and comes back untouched, so this can be applied to anything.
    """
    if not isinstance(value, str):
        return value
    try:
        return value.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def display_name(name):
    for glyph, symbol in GENDER_DISPLAY.items():
        name = name.replace(glyph, symbol)
    return re.sub(r"\s+", " ", name).strip()


# Which of the two runs a trainer belongs to, which rival they are, and which
# starter choice puts them in front of you. The rom holds every combination at
# once; a given save only ever meets one of each.
STARTER_LINES = {
    "treecko": ("Treecko", "Grovyle", "Sceptile"),
    "torchic": ("Torchic", "Combusken", "Blaziken"),
    "mudkip": ("Mudkip", "Marshtomp", "Swampert"),
}

# The rival takes the starter that beats yours: choose Mudkip and May turns up
# with Treecko. Keyed by what the rival holds, since that is what the team data
# shows, and read off as the choice that puts them in front of you.
RIVAL_TO_PLAYER = {"treecko": "mudkip", "torchic": "treecko", "mudkip": "torchic"}


def run_tags(name, team):
    """Which side, which rival, and the starter choice that summons them.

    Keyed "side" rather than "team", which a trainer already uses for the six
    Pokemon they field.
    """
    tags = {}
    lower = name.lower()

    if "aqua" in lower:
        tags["side"] = "aqua"
    elif "magma" in lower:
        tags["side"] = "magma"

    # Brendan and May are the same battles twice over: you play one, you fight
    # the other, and no save ever sees both.
    if "brendan" in lower:
        tags["rival"] = "brendan"
    elif re.search(r"\bmay\d*\s*$", lower):
        tags["rival"] = "may"

    if "rival" in tags:
        for member in team:
            species = member["species"].split("-")[0]
            for line, members in STARTER_LINES.items():
                if species in members:
                    tags["starter"] = RIVAL_TO_PLAYER[line]
                    return tags
    return tags


def is_gym(name):
    """The eight gyms, so the trainer list can pick them out of the routes.

    Matched on the name because that is all there is: nothing in the data says
    which areas are the ones you have to beat.
    """
    return name.strip().lower().endswith(" gym")


def add_rates(rows):
    """How often each wild encounter comes up, where that is knowable.

    From the hack's own AreaChanges.txt: "Every area with grass/walking/sand etc
    has at least 10 wild Pokemon, each having a 10% chance of appearing on any
    encounter. Some areas have 11 Pokemon instead, in which case two will only
    appear with a 5% rate. These 5% Pokemon are shown with an asterisk next to
    their name." That asterisk is the rare flag on each row.

    Applied only where a method's rates add up to exactly 100, which is 59 of
    the 70 land groups. Surfing, fishing, hordes and DexNav follow slot rules
    this data does not carry, and the odd land group is missing an asterisk. A
    plausible looking percentage that is wrong is worse than no percentage.
    """
    groups = collections.defaultdict(list)
    for row in rows:
        groups[row["method"]].append(row)

    for group in groups.values():
        rates = [5 if row["rare"] else 10 for row in group]
        if sum(rates) != 100:
            continue
        for row, rate in zip(group, rates):
            row["rate"] = rate


def build_payload(data_dir, key):
    poke = load(data_dir, "pokemon.json")
    moves = load(data_dir, "moves.json")["moveInfo"]
    areas = load(data_dir, "areas.json")["areas"]
    tm_moves = poke.get("tmMoves") or {}

    species = []
    for entry in poke["entries"]:
        attrs = {a.get("label"): a.get("value") for a in (entry.get("attrs") or [])}
        types = [t.strip() for t in (attrs.get("Type") or "").split("/") if t.strip()]

        tms = []
        for group in ("tms", "tmsNew", "tmsExtra"):
            for tm in (entry.get(group) or "").split():
                name = tm_moves.get(tm)
                if name:
                    tms.append({"tm": tm, "name": name, "new": group != "tms"})

        species.append({
            "name": entry["name"],
            "dex": entry.get("dex", ""),
            "types": types,
            "abilities": [a for a in (entry.get("a1"), entry.get("a2"), entry.get("ah")) if a],
            "stats": entry.get("stats") or {},
            "statChg": entry.get("statChg") or {},
            "evo": entry.get("evo") or {},
            "learnset": entry.get("moves") or [],
            "tms": tms,
            "notes": [fix_text(n) for n in (entry.get("notes") or [])],
            "changes": [fix_text(c) for c in (entry.get("changes") or [])],
            "location": attrs.get("Location", ""),
            "sprite": "./img/pokesprite/%s.png" % slug(entry["name"]),
        })

    trainers, by_area, matched = order.build_trainers(key, areas)

    # Rematches are the same trainer again at a higher level, and there are 224
    # of them: five Calvins on Route 102 buried the four trainers you actually
    # meet there. Dropped here rather than in build_trainers, so that the Next
    # button, which still has to walk every set the calc holds, is unaffected.
    trainers = {name: t for name, t in trainers.items() if not t["rematch"]}
    for area in by_area:
        area["trainers"] = [n for n in area["trainers"] if n in trainers]

    for name, entry in trainers.items():
        entry.update(run_tags(name, entry["team"]))
        entry["name"] = display_name(entry["name"])
    rosters = {a["index"]: a for a in by_area if "index" in a}

    # what each area holds, wild and trained, in the order you walk them
    area_list = []
    for index, area in enumerate(areas):
        rows = []
        for wild in (area.get("wild") or []):
            sp = wild.get("species")
            sp = sp if isinstance(sp, list) else [sp]
            for s in sp:
                if s and s.get("name"):
                    rows.append({"name": s["name"], "method": wild.get("method", ""),
                                 "level": wild.get("level", ""), "rare": bool(s.get("rare"))})
        add_rates(rows)

        roster = rosters.get(index) or {}
        if rows or roster.get("trainers"):
            area_list.append({"name": area["name"], "wild": rows,
                              "trainers": roster.get("trainers") or [],
                              "gym": is_gym(area["name"])})

    for area in by_area:                       # the unplaced tail has no wild rows
        if area.get("unplaced"):
            area_list.append({"name": area["name"], "wild": [],
                              "trainers": area["trainers"], "unplaced": True})

    # the hack's own attack changes document, which is where the before and
    # after live; moveInfo only carries a flag saying that a move was touched
    changed = {move_id(e.get("name")): e.get("rows") or []
               for e in (load(data_dir, "moves.json").get("attacks") or {}).get("entries", [])}

    move_list = []
    for key, m in moves.items():
        entry = {"id": key, "name": m.get("n", ""), "type": m.get("t", ""),
                 "cat": m.get("c", ""), "pow": m.get("pow", ""),
                 "acc": m.get("acc", ""), "pp": m.get("pp", ""),
                 "desc": fix_text(m.get("d", "")), "fx": fix_text(m.get("fx", ""))}
        rows = changed.get(move_id(m.get("n")))
        if m.get("chg") or rows:
            entry["chg"] = True
            entry["changes"] = rows or []
        move_list.append(entry)
    move_list.sort(key=lambda m: m["name"])

    return {"species": species, "areas": area_list, "moves": move_list,
            "moveById": {m["id"]: m for m in move_list}, "types": TYPE_COLOURS,
            "trainers": trainers,
            "_matched": sum(1 for t in trainers.values()
                            if t["area"] != "No listed location")}


CHROME = r"""
<div id="dex-open" title="Open the dex">Dex</div>
<div id="dex-overlay">
  <div id="dex-bar">
    <span id="dex-title"></span>
    <a class="dex-tab" id="dex-close" href="#">Calculator</a>
    <a class="dex-tab active" href="#">Dex</a>
  </div>
  <div id="dex-body">
    <div id="dex-left">
      <div class="dex-subtabs">
        <a class="dex-sub active" data-list="mons" href="#">Mons</a>
        <a class="dex-sub" data-list="areas" href="#">Areas</a>
        <a class="dex-sub" data-list="trainers" href="#">Trainers</a>
        <a class="dex-sub" data-list="moves" href="#">Moves</a>
      </div>
      <div id="dex-run">
        <select id="dex-version">
          <option value="">Both versions</option>
          <option value="magma">Rising Ruby &middot; Magma</option>
          <option value="aqua">Sinking Sapphire &middot; Aqua</option>
        </select>
        <select id="dex-player">
          <option value="">Either player</option>
          <option value="may">Playing the boy &middot; rival May</option>
          <option value="brendan">Playing the girl &middot; rival Brendan</option>
        </select>
        <select id="dex-starter">
          <option value="">Any starter</option>
          <option value="treecko">You chose Treecko</option>
          <option value="torchic">You chose Torchic</option>
          <option value="mudkip">You chose Mudkip</option>
        </select>
      </div>
      <input id="dex-search" placeholder="Search">
      <div id="dex-list"></div>
    </div>
    <div id="dex-mid"></div>
    <div id="dex-right"></div>
  </div>
</div>
<style>
 #dex-open { display:none }
 #dex-overlay { display:flex; position:fixed; inset:0; z-index:10000; background:#1b1b1b; color:#ddd;
                font-family:inherit; flex-direction:column }
 #dex-bar { flex:0 0 auto; display:flex; align-items:center; gap:6px; padding:8px 12px;
            background:#111; border-bottom:1px solid #333 }
 #dex-title { font-weight:bold; font-size:15px; margin-right:12px; color:#fff }
 .dex-tab, .dex-sub { color:#bbb; background:#2b2b2b; border:1px solid #444; border-radius:4px;
                      padding:4px 12px; text-decoration:none; font-size:13px }
 .dex-sub { padding:4px 7px; font-size:12px }
 .dex-tab.active, .dex-sub.active { color:#fff; background:#4a3a5a; border-color:#8a6aaa }
 #dex-body { flex:1 1 auto; display:flex; gap:10px; padding:10px; min-height:0 }
 #dex-left { flex:0 0 260px; display:flex; flex-direction:column; min-height:0;
             background:#232323; border:1px solid #333; border-radius:6px; padding:8px }
 .dex-subtabs { display:flex; gap:4px; margin-bottom:6px }
 #dex-search { width:100%; box-sizing:border-box; margin-bottom:6px; padding:5px 8px;
               background:#1b1b1b; color:#ddd; border:1px solid #444; border-radius:4px }
 #dex-run { display:none; margin-bottom:6px }
 #dex-run select { width:100%; box-sizing:border-box; margin-bottom:4px; padding:4px 6px;
                   background:#1b1b1b; color:#bbb; border:1px solid #444; border-radius:4px;
                   font-size:11px }
 #dex-list { flex:1 1 auto; overflow-y:auto; min-height:0 }
 .dex-row { padding:5px 8px; border-bottom:1px solid #2c2c2c; cursor:pointer; font-size:13px }
 .dex-row:hover { background:#2e2e2e }
 .dex-row.sel { background:#3a2f4a }
 .dex-row.group { display:flex; align-items:center; gap:6px; color:#cfc3dd }
 .dex-row.group .caret { color:#9a8aaa; font-size:12px; width:11px; line-height:1 }
 .dex-row.group.gym { color:#e6c264; font-weight:bold }
 .dex-row.group.gym .caret { color:#b08a2e }
 .dex-row.group.gym .dex-count { color:#9a7f3c }
 .dex-row.child { padding-left:24px }
 .dex-count { margin-left:auto; color:#777; font-size:11px }
 #dex-mid { flex:1 1 40%; overflow-y:auto; min-height:0; background:#232323;
            border:1px solid #333; border-radius:6px; padding:12px }
 #dex-right { flex:1 1 40%; overflow-y:auto; min-height:0; background:#232323;
              border:1px solid #333; border-radius:6px; padding:12px }
 .dex-type { display:inline-block; color:#fff; border-radius:3px; padding:1px 8px;
             font-size:11px; text-transform:uppercase; margin-right:4px }
 .dex-statrow { display:flex; align-items:center; gap:8px; margin:2px 0; font-size:13px }
 .dex-statrow b { width:64px; display:inline-block; font-weight:normal; color:#aaa }
 .dex-statnum { width:34px; text-align:right }
 .dex-bar { height:9px; border-radius:2px; background:#6a9955 }
 .dex-up { color:#6ec06e } .dex-down { color:#d16a6a }
 .dex-mv { display:flex; align-items:center; gap:8px; padding:4px 6px; border-bottom:1px solid #2c2c2c;
           font-size:13px; cursor:pointer }
 .dex-mv:hover { background:#2e2e2e }
 .dex-mv .lv { width:38px; color:#888; font-size:11px }
 .dex-icon { width:28px; height:28px; flex:0 0 28px; image-rendering:pixelated; margin:-4px 0 }
 .dex-tick { color:#6ec06e; font-size:11px; margin-left:5px }
 .dex-tick.dead { color:#c98b8b }
 .dex-chg { color:#e0b25a; border:1px solid #6b552a; background:#2e2718; border-radius:3px;
            font-size:10px; padding:0 5px; margin-left:6px; text-transform:uppercase }
 .dex-was { color:#a08585; text-decoration:line-through }
 .dex-now { color:#7fc47f }
 .dex-row.done, .dex-mv.done, .done { color:#7d8b7d }
 .dex-mv .nm { flex:1 1 auto }
 .dex-mv .num { min-width:38px; text-align:right; color:#ccc; white-space:nowrap }
 .dex-h { color:#fff; font-weight:bold; margin:10px 0 4px; border-bottom:1px solid #333; padding-bottom:3px }
 .dex-head { padding:6px 8px 3px; color:#9a86b5; font-size:11px; text-transform:uppercase;
             letter-spacing:.5px; cursor:default; position:sticky; top:0; background:#232323 }
 .dex-head.sub { position:static; color:#777; padding-left:16px; text-transform:none; letter-spacing:0 }
 .dex-mon { border:1px solid #333; border-radius:5px; padding:6px 8px; margin-bottom:6px; background:#1f1f1f }
 .dex-mon-top { display:flex; align-items:center; gap:8px }
 .dex-mon-top img { width:40px; height:40px; image-rendering:pixelated }
 .dex-mon-top .nm { font-size:14px; color:#fff }
 .dex-mon-top .meta { color:#999; font-size:11px }
 .dex-mon-mv { display:flex; flex-wrap:wrap; gap:4px; margin-top:5px }
 .dex-mon-mv span.mv { border:1px solid #3a3a3a; border-radius:3px; padding:1px 6px; font-size:11px; background:#262626 }
 #dex-open-calc { display:inline-block; margin-top:8px; padding:5px 12px; border-radius:4px;
                  background:#4a3a5a; border:1px solid #8a6aaa; color:#fff; font-size:13px;
                  text-decoration:none; cursor:pointer }
 @media (max-width: 900px) { #dex-body { flex-direction:column } #dex-left { flex:0 0 auto; max-height:200px } }
</style>
<script>
(function () {
    var D = window.DEX_DATA, cur = null, list = 'mons', curKey = null, curKind = 'mons';
    var expanded = {};              // which areas are open on the trainer list

    // Which run you are actually playing. The rom holds both versions, both
    // rivals and all three starter branches at once, and a save only ever meets
    // one of each, so the rest is noise on a route list.
    var run = { side: '', rival: '', starter: '' };

    function inRun(t) {
        if (run.side && t.side && t.side !== run.side) return false;
        if (run.rival && t.rival && t.rival !== run.rival) return false;
        if (run.starter && t.starter && t.starter !== run.starter) return false;
        return true;
    }
    var byName = {}; D.species.forEach(function (s) { byName[s.name] = s });

    function el(id) { return document.getElementById(id) }
    function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] }) }
    // What the calculator's save reader says you already have. The game names a
    // route once where this data splits it in two, so "Route 104" marks off both
    // halves of Route 104; a prefix has to end on a word so that Route 10 does
    // not claim Route 103.
    var caught = { species: {}, areas: {}, dead: {}, deadAreas: {} };

    function matches(name, list) {
        var n = String(name).toLowerCase().trim();
        return Object.keys(list).some(function (a) {
            a = a.toLowerCase().trim();
            return n === a || n.indexOf(a + ' ') === 0 || n.indexOf(a + ' (') === 0;
        });
    }

    // A route is spent whether the Pokemon lived or died, so both mark it off;
    // the dagger says which, and a later catch on the same route wins.
    function areaState(name) {
        if (matches(name, caught.areas)) return 'caught';
        if (matches(name, caught.deadAreas)) return 'dead';
        return '';
    }

    function tick(state) {
        if (!state) return '';
        return state === 'dead'
            ? '<span class="dex-tick dead" title="lost here">&#10013;</span>'
            : '<span class="dex-tick" title="caught">&#10003;</span>';
    }

    function monState(name) {
        return caught.species[name] ? 'caught' : caught.dead[name] ? 'dead' : '';
    }

    function icon(name) {
        var sp = byName[name];
        if (!sp) return '';
        return '<img class="dex-icon" src="' + esc(sp.sprite) + '" alt="" '
             + 'onerror="this.style.visibility=\'hidden\'">';
    }

    function typeTag(t) {
        var c = D.types[String(t).toLowerCase()] || '#666';
        return '<span class="dex-type" style="background:' + c + '">' + esc(t) + '</span>';
    }

    // The calculator opens this in an iframe over the top of itself, so that
    // going back to it is not a page load and nothing you had typed is lost.
    // When that is where we are, talk to it rather than navigating.
    var embedded = window.parent !== window;

    function tellParent(msg) {
        try { window.parent.postMessage(msg, '*') } catch (e) { }
    }

    function calcUrl() {
        // Resolve through URL rather than splicing the path. The path can arrive
        // with a doubled slash, and "//index.html" is protocol relative, so the
        // browser reads index.html as the hostname and fails to connect.
        var q = location.search.replace(/([?&])view=[^&]*&?/, '$1').replace(/[?&]$/, '');
        return new URL('index.html' + q, location.href).toString();
    }

    // Where you were last time. The trip to the calculator and back is a full
    // page load, so without this every visit starts at the top of the mon list.
    // Wrapped because localStorage throws outright on a file:// origin, and an
    // exception here would take the rest of the dex down with it.
    var STORE = 'dexState:' + (window.DEX_TITLE || '');

    function remember() {
        try {
            localStorage.setItem(STORE, JSON.stringify({
                list: list, kind: curKind, sel: curKey, run: run,
                q: el('dex-search').value, scroll: el('dex-list').scrollTop
            }));
        } catch (e) { }
    }

    function recall() {
        try { return JSON.parse(localStorage.getItem(STORE) || 'null') } catch (e) { return null }
    }

    function rows() {
        var q = el('dex-search').value.trim().toLowerCase(), out = [];
        if (list === 'mons') {
            D.species.forEach(function (s) {
                if (!q || s.name.toLowerCase().indexOf(q) >= 0 ||
                    s.types.join(' ').toLowerCase().indexOf(q) >= 0)
                    out.push({ key: s.name, label: '#' + s.dex + ' ' + s.name });
            });
        } else if (list === 'areas') {
            D.areas.forEach(function (a) {
                if (!a.wild.length) return;         // this tab is the encounter list
                if (!q || a.name.toLowerCase().indexOf(q) >= 0)
                    out.push({ key: a.name, label: a.name, area: true, done: areaState(a.name) });
            });
        } else if (list === 'trainers') {
            // Areas in the order you play them, closed until you ask. Listing
            // every trainer at once is 725 rows to scroll past. A search opens
            // whatever survives it, so typing either an area or a trainer name
            // gets you straight there.
            D.areas.forEach(function (a) {
                if (!a.trainers.length) return;
                var areaHit = !q || a.name.toLowerCase().indexOf(q) >= 0;
                var hit = a.trainers.filter(function (t) {
                    if (!inRun(D.trainers[t])) return false;
                    return areaHit || D.trainers[t].name.toLowerCase().indexOf(q) >= 0;
                });
                if (!hit.length) return;

                var open = q ? true : !!expanded[a.name];
                out.push({ key: a.name, label: a.name, group: true, open: open,
                           count: hit.length, gym: a.gym });
                if (open) hit.forEach(function (t) {
                    out.push({ key: t, label: D.trainers[t].name, child: true });
                });
            });
        } else {
            D.moves.forEach(function (m) {
                if (!q || m.name.toLowerCase().indexOf(q) >= 0)
                    out.push({ key: m.id, label: m.name, move: true, chg: m.chg });
            });
        }
        return out;
    }

    function renderList() {
        el('dex-list').innerHTML = rows().slice(0, 1600).map(function (r) {
            if (r.head) return '<div class="dex-head' + (r.sub ? ' sub' : '') + '">'
                             + esc(r.label) + '</div>';
            if (r.chg) return '<div class="dex-row" data-key="' + esc(r.key) + '">' + esc(r.label)
                            + '<span class="dex-chg" title="changed by this hack">changed</span></div>';
            if (r.group) return '<div class="dex-row group' + (r.gym ? ' gym' : '') + '" '
                             + 'data-group="' + esc(r.key) + '">'
                             + '<span class="caret">' + (r.open ? '&#9662;' : '&#9656;') + '</span>'
                             + esc(r.label) + '<span class="dex-count">' + r.count + '</span></div>';
            if (r.child) return '<div class="dex-row child" data-key="' + esc(r.key) + '">'
                             + esc(r.label) + '</div>';
            return '<div class="dex-row' + (r.done ? ' done' : '') + '" data-key="' + esc(r.key) + '">'
                 + esc(r.label) + tick(r.done) + '</div>';
        }).join('');
    }

    function statBar(label, value, chg) {
        var pct = Math.max(2, Math.min(100, value / 255 * 100));
        var mark = chg ? ' <span class="' + (chg > 0 ? 'dex-up">+' : 'dex-down">') + chg + '</span>' : '';
        return '<div class="dex-statrow"><b>' + label + '</b>'
             + '<span class="dex-statnum">' + value + '</span>' + mark
             + '<span class="dex-bar" style="width:' + pct + '%"></span></div>';
    }

    function select(sp) {
        cur = sp;
        var s = sp.stats, c = sp.statChg || {};
        var where = D.areas.filter(function (a) {
            return a.wild.some(function (w) { return w.name === sp.name });
        });

        el('dex-mid').innerHTML =
            '<div style="display:flex;align-items:center;gap:10px">'
          + '<img src="' + esc(sp.sprite) + '" style="width:56px;height:56px;image-rendering:pixelated">'
          + '<div><div style="font-size:18px;color:#fff">' + esc(sp.name)
          + ' <span style="color:#888;font-size:13px">#' + esc(sp.dex) + '</span></div>'
          + '<div style="margin-top:4px">' + sp.types.map(typeTag).join('') + '</div></div></div>'
          + '<div class="dex-h">Abilities</div>' + esc(sp.abilities.join(' | ') || '-')
          + '<div class="dex-h">Base stats</div>'
          + statBar('HP', s.hp, c.hp) + statBar('Attack', s.atk, c.atk) + statBar('Defense', s.def, c.def)
          + statBar('Sp. Atk', s.spa, c.spa) + statBar('Sp. Def', s.spd, c.spd) + statBar('Speed', s.spe, c.spe)
          + '<div class="dex-statrow"><b>Total</b><span class="dex-statnum">' + esc(s.total) + '</span></div>'
          + '<div class="dex-h">Evolution</div>'
          + (sp.evo && sp.evo.into ? esc(sp.evo.into) + ' <span style="color:#888">(' + esc(sp.evo.level) + ')</span>'
                                   : 'Does not evolve')
          + '<div class="dex-h">Found in</div>'
          + (where.length ? where.map(function (a) {
                var w = a.wild.filter(function (x) { return x.name === sp.name });
                var st = areaState(a.name);
                return '<div style="font-size:13px;padding:2px 0"' + (st ? ' class="done"' : '') + '>'
                     + esc(a.name) + tick(st)
                     + ' <span style="color:#888">' + esc(w.map(function (x) {
                           return x.method + (x.rate ? ' ' + x.rate + '%' : '')
                                + ' Lv' + x.level + (x.rare ? ' *' : ''); }).join(', ')) + '</span></div>';
            }).join('') : '<span style="color:#888">Not found in the wild</span>')
          + (sp.notes && sp.notes.length ? '<div class="dex-h">Notes</div>'
                + sp.notes.map(function (n) { return '<div style="font-size:12px;color:#bbb">' + esc(n) + '</div>' }).join('') : '');

        function moveRow(lv, name) {
            var m = D.moveById[name.toLowerCase().replace(/[^a-z0-9]/g, '')] || {};
            return '<div class="dex-mv" data-move="' + esc(m.id || '') + '">'
                 + '<span class="lv">' + esc(lv) + '</span>'
                 + (m.type ? typeTag(m.type) : '')
                 + '<span class="nm">' + esc(name) + '</span>'
                 + '<span class="num">' + esc(m.pow || '-') + '</span>'
                 + '<span class="num">' + esc(m.acc || '-') + '</span>'
                 + '<span class="num">' + esc(m.pp || '-') + '</span></div>';
        }

        el('dex-right').innerHTML =
            '<div class="dex-h">Level-up <span style="float:right;color:#888;font-size:11px">Pow / Acc / PP</span></div>'
          + sp.learnset.map(function (m) { return moveRow('L' + m.level, m.name) }).join('')
          + (sp.tms.length ? '<div class="dex-h">TM / HM</div>'
                + sp.tms.map(function (t) { return moveRow(t.tm, t.name) }).join('') : '');

        markSel(sp.name, 'mons');
    }

    function markSel(key, kind) {
        curKey = key;
        curKind = kind;
        Array.prototype.forEach.call(document.querySelectorAll('.dex-row'), function (r) {
            r.classList.toggle('sel', r.getAttribute('data-key') === key);
        });
        remember();
    }

    function showArea(name) {
        var a = D.areas.filter(function (x) { return x.name === name })[0];
        if (!a) return;
        var byMethod = {};
        a.wild.forEach(function (w) { (byMethod[w.method] = byMethod[w.method] || []).push(w) });
        var state = areaState(a.name);
        el('dex-mid').innerHTML = '<div style="font-size:18px;color:#fff">' + esc(a.name)
            + (state ? ' <span class="dex-tick' + (state === 'dead' ? ' dead' : '') + '">'
                     + (state === 'dead' ? '&#10013; lost here' : '&#10003; caught here') + '</span>' : '')
            + '</div>'
          + Object.keys(byMethod).map(function (m) {
              var rated = byMethod[m].some(function (w) { return w.rate });
              return '<div class="dex-h">' + esc(m)
                   + '<span style="float:right;color:#888;font-size:11px">'
                   + (rated ? 'Rate / Level' : 'Level') + '</span></div>'
                   + byMethod[m].map(function (w) {
                  var st = monState(w.name);
                  return '<div class="dex-mv' + (st ? ' done' : '') + '" '
                       + 'data-mon="' + esc(w.name) + '">'
                       + icon(w.name)
                       + '<span class="nm">' + esc(w.name) + tick(st) + '</span>'
                       + (rated ? '<span class="num">' + (w.rate ? w.rate + '%' : '-') + '</span>' : '')
                       + '<span class="num">Lv' + esc(w.level) + '</span></div>';
              }).join('');
          }).join('');
        el('dex-right').innerHTML = '<div style="color:#888">Pick a Pokémon to see its moves.</div>';
        markSel(a.name, 'areas');
    }

    function moveChip(name) {
        var m = D.moveById[name.toLowerCase().replace(/[^a-z0-9]/g, '')] || {};
        var c = m.type ? (D.types[String(m.type).toLowerCase()] || '#3a3a3a') : '#3a3a3a';
        return '<span class="mv" style="border-color:' + c + '" title="'
             + esc(m.type || '') + ' ' + esc(m.cat || '') + ' - ' + esc(m.pow || '-') + ' pow, '
             + esc(m.acc || '-') + ' acc">' + esc(name) + '</span>';
    }

    function showTrainer(key) {
        var t = D.trainers[key];
        if (!t) return;
        // opened from anywhere - a deep link, a restored spot, the area view -
        // the list has to open too, or the selected trainer sits inside a
        // collapsed area with nothing to show for it
        if (!expanded[t.area]) {
            expanded[t.area] = true;
            renderList();
        }

        el('dex-mid').innerHTML =
            '<div style="font-size:18px;color:#fff">' + esc(t.name)
          + (t.rematch ? ' <span style="color:#9a86b5;font-size:12px">rematch</span>' : '') + '</div>'
          + '<div style="color:#888;font-size:12px;margin-top:2px">'
          + esc(t.area) + ' &middot; ' + t.team.length + ' Pokémon</div>'
          + '<a id="dex-open-calc" href="#" data-set="' + esc(t.team[0].value) + '">Open in calculator</a>'
          + '<div class="dex-h">Team</div>'
          + t.team.map(function (m) {
                var sp = byName[m.species] || {};
                return '<div class="dex-mon">'
                     + '<div class="dex-mon-top">'
                     + '<img src="' + esc(sp.sprite || '') + '" onerror="this.style.visibility=\'hidden\'">'
                     + '<div><div class="nm" data-mon="' + esc(m.species) + '" style="cursor:pointer">'
                     + esc(m.species) + ' <span style="color:#888;font-size:12px">Lv' + esc(m.level) + '</span></div>'
                     + '<div class="meta">' + esc(m.ability || '-') + ' &middot; ' + esc(m.nature || '-')
                     + (m.item ? ' &middot; ' + esc(m.item) : '') + '</div></div></div>'
                     + '<div class="dex-mon-mv">' + m.moves.map(moveChip).join('') + '</div></div>';
            }).join('');

        // every move the trainer can throw at you, strongest first: the thing
        // you actually want before deciding what to send in
        var seen = {}, all = [];
        t.team.forEach(function (m) {
            m.moves.forEach(function (name) {
                if (seen[name]) return;
                seen[name] = 1;
                all.push(D.moveById[name.toLowerCase().replace(/[^a-z0-9]/g, '')] || { name: name });
            });
        });
        all.sort(function (a, b) { return (parseInt(b.pow, 10) || 0) - (parseInt(a.pow, 10) || 0) });

        el('dex-right').innerHTML =
            '<div class="dex-h">Moves used <span style="float:right;color:#888;font-size:11px">Pow / Acc / PP</span></div>'
          + all.map(function (m) {
                return '<div class="dex-mv" data-move="' + esc(m.id || '') + '">'
                     + (m.type ? typeTag(m.type) : '')
                     + '<span class="nm">' + esc(m.name) + '</span>'
                     + '<span class="num">' + esc(m.pow || '-') + '</span>'
                     + '<span class="num">' + esc(m.acc || '-') + '</span>'
                     + '<span class="num">' + esc(m.pp || '-') + '</span></div>';
            }).join('');

        markSel(key, 'trainers');
    }

    function openInCalc(setValue) {
        remember();
        if (embedded) return tellParent({ dex: 'set', set: setValue });

        // Standalone, this is a page load, and a set name in localStorage is
        // the one thing that survives the trip between two separate pages.
        try { localStorage.setItem('msTrainer', setValue) } catch (e) { }
        location.href = calcUrl();
    }

    function showMove(id) {
        var m = D.moveById[id];
        if (!m) return;
        var learners = D.species.filter(function (s) {
            return s.learnset.some(function (x) { return x.name === m.name })
                || s.tms.some(function (t) { return t.name === m.name });
        });
        el('dex-mid').innerHTML = '<div style="font-size:18px;color:#fff">' + esc(m.name)
          + (m.chg ? '<span class="dex-chg">changed</span>' : '') + '</div>'
          + '<div style="margin-top:6px">' + (m.type ? typeTag(m.type) : '') + esc(m.cat) + '</div>'
          + '<div class="dex-h">Power ' + esc(m.pow || '-') + ' &nbsp; Accuracy ' + esc(m.acc || '-')
          + ' &nbsp; PP ' + esc(m.pp || '-') + '</div>'
          + (m.fx ? '<div style="font-size:13px;color:#bbb">' + esc(m.fx) + '</div>' : '')
          + '<div style="font-size:13px;color:#bbb">' + esc(m.desc || '') + '</div>'
          + ((m.changes && m.changes.length)
                ? '<div class="dex-h">What changed</div>'
                  + m.changes.map(function (c) {
                        return '<div class="dex-mv"><span class="nm">' + esc(c.label) + '</span>'
                             + '<span class="num dex-was">' + esc(c.from) + '</span>'
                             + '<span class="num">&rarr;</span>'
                             + '<span class="num dex-now">' + esc(c.to) + '</span></div>';
                    }).join('')
                : (m.chg ? '<div class="dex-h">What changed</div>'
                         + '<div style="font-size:12px;color:#888">Marked as changed, without a listed before and after.</div>'
                   : ''));
        el('dex-right').innerHTML = '<div class="dex-h">Learned by (' + learners.length + ')</div>'
          + learners.map(function (s) {
              return '<div class="dex-mv" data-mon="' + esc(s.name) + '">' + icon(s.name)
                   + '<span class="nm">' + esc(s.name) + '</span></div>';
          }).join('');

        markSel(id, 'moves');
    }

    el('dex-close').setAttribute('href', calcUrl());
    el('dex-close').addEventListener('click', function (e) {
        if (!embedded) return;              // standalone, the href does the work
        e.preventDefault();
        remember();
        tellParent({ dex: 'close' });
    });
    el('dex-search').addEventListener('input', function () { renderList(); remember() });

    var scrollTimer = null;
    el('dex-list').addEventListener('scroll', function () {
        clearTimeout(scrollTimer);
        scrollTimer = setTimeout(remember, 200);
    });

    var PLACEHOLDERS = {
        mons: 'Search a Pokémon or type', areas: 'Search an area',
        trainers: 'Search an area or trainer', moves: 'Search a move'
    };

    function setList(name, keepSearch) {
        list = name;
        Array.prototype.forEach.call(document.querySelectorAll('.dex-sub'), function (x) {
            x.classList.toggle('active', x.getAttribute('data-list') === name);
        });
        if (!keepSearch) el('dex-search').value = '';
        el('dex-search').placeholder = PLACEHOLDERS[name] || 'Search';
        el('dex-run').style.display = name === 'trainers' ? 'block' : 'none';
        renderList();
        remember();
    }

    Array.prototype.forEach.call(document.querySelectorAll('.dex-sub'), function (t) {
        t.addEventListener('click', function (e) {
            e.preventDefault();
            setList(t.getAttribute('data-list'));
        });
    });

    var RUN_FIELDS = { 'dex-version': 'side', 'dex-player': 'rival', 'dex-starter': 'starter' };

    Object.keys(RUN_FIELDS).forEach(function (id) {
        el(id).addEventListener('change', function () {
            run[RUN_FIELDS[id]] = el(id).value;
            renderList();
            remember();
        });
    });

    document.addEventListener('click', function (e) {
        var open = e.target.closest && e.target.closest('#dex-open-calc');
        if (open) { e.preventDefault(); openInCalc(open.getAttribute('data-set')); return }

        var group = e.target.closest && e.target.closest('.dex-row[data-group]');
        if (group) {
            var area = group.getAttribute('data-group');
            expanded[area] = !expanded[area];
            renderList();
            return;
        }

        var row = e.target.closest && e.target.closest('.dex-row');
        if (row) {
            var key = row.getAttribute('data-key');
            if (list === 'mons') select(byName[key]);
            else if (list === 'areas') showArea(key);
            else if (list === 'trainers') showTrainer(key);
            else showMove(key);
            return;
        }
        var tr = e.target.closest && e.target.closest('[data-trainer]');
        if (tr) { showTrainer(tr.getAttribute('data-trainer')); return }
        var mon = e.target.closest && e.target.closest('[data-mon]');
        if (mon && byName[mon.getAttribute('data-mon')]) { select(byName[mon.getAttribute('data-mon')]); return }
        var mv = e.target.closest && e.target.closest('[data-move]');
        if (mv && mv.getAttribute('data-move')) showMove(mv.getAttribute('data-move'));
    });

    if (embedded) {
        window.addEventListener('message', function (e) {
            if (e.source !== window.parent) return;
            if (!e.data || e.data.dex !== 'caught') return;

            caught = { species: {}, areas: {}, dead: {}, deadAreas: {} };
            (e.data.species || []).forEach(function (n) { caught.species[n] = true });
            (e.data.areas || []).forEach(function (n) { caught.areas[n] = true });
            (e.data.dead || []).forEach(function (n) { caught.dead[n] = true });
            (e.data.deadAreas || []).forEach(function (n) { caught.deadAreas[n] = true });

            renderList();                       // the marks live in both panes
            if (curKind && curKey) openEntry(curKind, curKey);
        });
        tellParent({ dex: 'ready' });
    }

    el('dex-title').textContent = window.DEX_TITLE || 'Dex';

    var LISTS = ['mons', 'areas', 'trainers', 'moves'];

    function openEntry(kind, key) {
        if (kind === 'trainers' && D.trainers[key]) showTrainer(key);
        else if (kind === 'areas' && key) showArea(key);
        else if (kind === 'moves' && D.moveById[key]) showMove(key);
        else if (byName[key]) select(byName[key]);
        else return false;
        return true;
    }

    // An explicit ?list=trainers&sel=Youngster Calvin wins, so a view can still
    // be linked to. Otherwise pick up where this browser left off, which is what
    // makes the trip to the calculator and back free.
    // the run is yours whatever you are looking at, so it survives a deep link
    var remembered = recall();
    if (remembered && remembered.run) {
        run = remembered.run;
        Object.keys(RUN_FIELDS).forEach(function (id) { el(id).value = run[RUN_FIELDS[id]] || '' });
    }

    var want = /[?&]list=([^&]*)/.exec(location.search);
    var sel = /[?&]sel=([^&]*)/.exec(location.search);
    var saved = (want || sel) ? null : recall();

    if (want && LISTS.indexOf(decodeURIComponent(want[1])) >= 0) {
        setList(decodeURIComponent(want[1]));
    } else if (saved && LISTS.indexOf(saved.list) >= 0) {
        el('dex-search').value = saved.q || '';
        setList(saved.list, true);
        el('dex-search').placeholder = PLACEHOLDERS[saved.list] || 'Search';
    } else {
        renderList();
    }

    // before the selection below, which saves state as it lands: restoring the
    // scroll afterwards would first store a 0 and lose the position for anyone
    // who leaves again without scrolling
    if (saved && saved.scroll) el('dex-list').scrollTop = saved.scroll;

    if (!(sel && openEntry(list, decodeURIComponent(sel[1])))
        && !(saved && openEntry(saved.kind, saved.sel))) {
        select(D.species[0]);
    }
})()
</script>
"""


def build(key, title, data_dir):
    payload = build_payload(data_dir, key)

    # A standalone page, not index.html with the dex bolted on. Sharing the
    # shell meant the calculator booted on both pages and the dex's own data
    # loaded alongside it, and the calculator came back half initialised.
    # Nothing here can touch the calculator, because none of it is loaded.
    shell = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>%s</title>
<script src="./js/vendor/jquery-1.9.1.min.js"></script>
<style>html,body{margin:0;padding:0;background:#1b1b1b;color:#ddd;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}</style>
</head><body>
<script>window.DEX_TITLE = %s; window.DEX_DATA = %s;</script>
%s
</body></html>
""" % (esc(title + " Dex"), json.dumps(title + " Dex"),
       json.dumps(payload, ensure_ascii=False), CHROME)

    dest = os.path.join(REPO, "%s_mastersheet.html" % key)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(shell)

    print("species:  %d" % len(payload["species"]))
    print("areas:    %d" % len(payload["areas"]))
    print("moves:    %d" % len(payload["moves"]))
    print("trainers: %d (%d placed in an area, %d not listed)"
          % (len(payload["trainers"]), payload["_matched"],
             len(payload["trainers"]) - payload["_matched"]))
    print("wrote %s (%.1f MB)" % (dest, os.path.getsize(dest) / 1024 / 1024))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2], sys.argv[3])
