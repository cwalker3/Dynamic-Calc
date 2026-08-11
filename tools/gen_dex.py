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
import html
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


def build_payload(data_dir):
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
            "notes": entry.get("notes") or [],
            "changes": entry.get("changes") or [],
            "location": attrs.get("Location", ""),
            "sprite": "./img/pokesprite/%s.png" % slug(entry["name"]),
        })

    # where each species can be caught, and what each area holds
    area_list = []
    for area in areas:
        rows = []
        for wild in (area.get("wild") or []):
            sp = wild.get("species")
            sp = sp if isinstance(sp, list) else [sp]
            for s in sp:
                if s and s.get("name"):
                    rows.append({"name": s["name"], "method": wild.get("method", ""),
                                 "level": wild.get("level", ""), "rare": bool(s.get("rare"))})
        if rows:
            area_list.append({"name": area["name"], "wild": rows})

    move_list = []
    for key, m in moves.items():
        move_list.append({"id": key, "name": m.get("n", ""), "type": m.get("t", ""),
                          "cat": m.get("c", ""), "pow": m.get("pow", ""),
                          "acc": m.get("acc", ""), "pp": m.get("pp", ""),
                          "desc": m.get("d", "")})
    move_list.sort(key=lambda m: m["name"])

    return {"species": species, "areas": area_list, "moves": move_list,
            "moveById": {m["id"]: m for m in move_list}, "types": TYPE_COLOURS}


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
        <a class="dex-sub" data-list="moves" href="#">Moves</a>
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
 .dex-tab.active, .dex-sub.active { color:#fff; background:#4a3a5a; border-color:#8a6aaa }
 #dex-body { flex:1 1 auto; display:flex; gap:10px; padding:10px; min-height:0 }
 #dex-left { flex:0 0 260px; display:flex; flex-direction:column; min-height:0;
             background:#232323; border:1px solid #333; border-radius:6px; padding:8px }
 .dex-subtabs { display:flex; gap:4px; margin-bottom:6px }
 #dex-search { width:100%; box-sizing:border-box; margin-bottom:6px; padding:5px 8px;
               background:#1b1b1b; color:#ddd; border:1px solid #444; border-radius:4px }
 #dex-list { flex:1 1 auto; overflow-y:auto; min-height:0 }
 .dex-row { padding:5px 8px; border-bottom:1px solid #2c2c2c; cursor:pointer; font-size:13px }
 .dex-row:hover { background:#2e2e2e }
 .dex-row.sel { background:#3a2f4a }
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
 .dex-mv .nm { flex:1 1 auto }
 .dex-mv .num { width:38px; text-align:right; color:#ccc }
 .dex-h { color:#fff; font-weight:bold; margin:10px 0 4px; border-bottom:1px solid #333; padding-bottom:3px }
 @media (max-width: 900px) { #dex-body { flex-direction:column } #dex-left { flex:0 0 auto; max-height:200px } }
</style>
<script>
(function () {
    var D = window.DEX_DATA, cur = null, list = 'mons';
    var byName = {}; D.species.forEach(function (s) { byName[s.name] = s });

    function el(id) { return document.getElementById(id) }
    function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] }) }
    function typeTag(t) {
        var c = D.types[String(t).toLowerCase()] || '#666';
        return '<span class="dex-type" style="background:' + c + '">' + esc(t) + '</span>';
    }

    function calcUrl() {
        var q = location.search.replace(/([?&])view=[^&]*&?/, '$1').replace(/[?&]$/, '');
        return location.pathname.replace(/[^\/]*$/, 'index.html') + q;
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
                if (!q || a.name.toLowerCase().indexOf(q) >= 0)
                    out.push({ key: a.name, label: a.name, area: true });
            });
        } else {
            D.moves.forEach(function (m) {
                if (!q || m.name.toLowerCase().indexOf(q) >= 0)
                    out.push({ key: m.id, label: m.name, move: true });
            });
        }
        return out;
    }

    function renderList() {
        el('dex-list').innerHTML = rows().slice(0, 1200).map(function (r) {
            return '<div class="dex-row" data-key="' + esc(r.key) + '">' + esc(r.label) + '</div>';
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
                return '<div style="font-size:13px;padding:2px 0">' + esc(a.name)
                     + ' <span style="color:#888">' + esc(w.map(function (x) {
                           return x.method + ' Lv' + x.level + (x.rare ? ' *' : ''); }).join(', ')) + '</span></div>';
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

        Array.prototype.forEach.call(document.querySelectorAll('.dex-row'), function (r) {
            r.classList.toggle('sel', r.getAttribute('data-key') === sp.name);
        });
    }

    function showArea(name) {
        var a = D.areas.filter(function (x) { return x.name === name })[0];
        if (!a) return;
        var byMethod = {};
        a.wild.forEach(function (w) { (byMethod[w.method] = byMethod[w.method] || []).push(w) });
        el('dex-mid').innerHTML = '<div style="font-size:18px;color:#fff">' + esc(a.name) + '</div>'
          + Object.keys(byMethod).map(function (m) {
              return '<div class="dex-h">' + esc(m) + '</div>' + byMethod[m].map(function (w) {
                  return '<div class="dex-mv" data-mon="' + esc(w.name) + '">'
                       + '<span class="nm">' + esc(w.name) + (w.rare ? ' *' : '') + '</span>'
                       + '<span class="num">Lv' + esc(w.level) + '</span></div>';
              }).join('');
          }).join('');
        el('dex-right').innerHTML = '<div style="color:#888">Pick a Pokémon to see its moves.</div>';
    }

    function showMove(id) {
        var m = D.moveById[id];
        if (!m) return;
        var learners = D.species.filter(function (s) {
            return s.learnset.some(function (x) { return x.name === m.name })
                || s.tms.some(function (t) { return t.name === m.name });
        });
        el('dex-mid').innerHTML = '<div style="font-size:18px;color:#fff">' + esc(m.name) + '</div>'
          + '<div style="margin-top:6px">' + (m.type ? typeTag(m.type) : '') + esc(m.cat) + '</div>'
          + '<div class="dex-h">Power ' + esc(m.pow || '-') + ' &nbsp; Accuracy ' + esc(m.acc || '-')
          + ' &nbsp; PP ' + esc(m.pp || '-') + '</div>'
          + '<div style="font-size:13px;color:#bbb">' + esc(m.desc || '') + '</div>';
        el('dex-right').innerHTML = '<div class="dex-h">Learned by (' + learners.length + ')</div>'
          + learners.map(function (s) {
              return '<div class="dex-mv" data-mon="' + esc(s.name) + '"><span class="nm">' + esc(s.name) + '</span></div>';
          }).join('');
    }

    el('dex-close').setAttribute('href', calcUrl());
    el('dex-search').addEventListener('input', renderList);

    Array.prototype.forEach.call(document.querySelectorAll('.dex-sub'), function (t) {
        t.addEventListener('click', function (e) {
            e.preventDefault();
            Array.prototype.forEach.call(document.querySelectorAll('.dex-sub'), function (x) {
                x.classList.remove('active');
            });
            t.classList.add('active');
            list = t.getAttribute('data-list');
            el('dex-search').value = '';
            renderList();
        });
    });

    document.addEventListener('click', function (e) {
        var row = e.target.closest && e.target.closest('.dex-row');
        if (row) {
            var key = row.getAttribute('data-key');
            if (list === 'mons') select(byName[key]);
            else if (list === 'areas') showArea(key);
            else showMove(key);
            return;
        }
        var mon = e.target.closest && e.target.closest('[data-mon]');
        if (mon && byName[mon.getAttribute('data-mon')]) { select(byName[mon.getAttribute('data-mon')]); return }
        var mv = e.target.closest && e.target.closest('[data-move]');
        if (mv && mv.getAttribute('data-move')) showMove(mv.getAttribute('data-move'));
    });

    el('dex-title').textContent = window.DEX_TITLE || 'Dex';
    renderList();
    select(D.species[0]);
})()
</script>
"""


def build(key, title, data_dir):
    payload = build_payload(data_dir)

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

    print("species: %d" % len(payload["species"]))
    print("areas:   %d" % len(payload["areas"]))
    print("moves:   %d" % len(payload["moves"]))
    print("wrote %s (%.1f MB)" % (dest, os.path.getsize(dest) / 1024 / 1024))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2], sys.argv[3])
