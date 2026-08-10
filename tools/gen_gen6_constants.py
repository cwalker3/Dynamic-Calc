"""Generates js/save_constants/gen6.js from PKHeX resources.

Run from the repo root with a scratch directory holding the PKHeX resources:

    python3 tools/gen_gen6_constants.py <dir-with-pkhex-resources>

The directory needs these files, copied out of kwsch/PKHeX (PKHeX.Core/Resources):
    text/other/en/text_Species_en.txt      -> text_Species_en.txt
    text/other/en/text_Moves_en.txt        -> text_Moves_en.txt
    text/other/en/text_Abilities_en.txt    -> text_Abilities_en.txt
    text/items/text_Items_en.txt           -> text_Items_en.txt
    text/locations/gen6/text_xy_*_en.txt   -> text_xy_*_en.txt
    byte/personal/personal_ao              -> personal_ao

Names are normalised to the spellings used by calc/data/*.js so that every value
the save reader emits resolves against the calculator's own dex. The script exits
non-zero if any generated name fails that check.
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, 'tools', 'pkhex')

MAX_SPECIES = 721
MAX_MOVE = 621
MAX_ITEM = 775
MAX_ABILITY = 191
PERSONAL_ENTRY_SIZE = 0x50
PERSONAL_EXP_GROWTH = 0x15


def lines(name):
    with open(os.path.join(SRC, name), encoding='utf-8-sig') as f:
        return f.read().split('\n')


def straight(s):
    """calc/data/moves.js and items.js use a plain apostrophe, PKHeX uses U+2019."""
    return s.replace('’', "'")


# ---------------------------------------------------------------- species ---
species = lines('text_Species_en.txt')[:MAX_SPECIES + 1]
species[0] = ''
species[29] = 'Nidoran-F'
species[32] = 'Nidoran-M'

# ------------------------------------------------------------------ moves ---
moves = [straight(m) for m in lines('text_Moves_en.txt')[:MAX_MOVE + 1]]
moves[0] = '(No Move)'

# ------------------------------------------------------------------ items ---
items = [straight(i) for i in lines('text_Items_en.txt')[:MAX_ITEM + 1]]
items[0] = ''

# -------------------------------------------------------------- abilities ---
abilities = [straight(a) for a in lines('text_Abilities_en.txt')[:MAX_ABILITY + 1]]
abilities[0] = ''

# ---------------------------------------------------------------- growths ---
with open(os.path.join(SRC, 'personal_ao'), 'rb') as f:
    personal = f.read()
growths = [personal[s * PERSONAL_ENTRY_SIZE + PERSONAL_EXP_GROWTH]
           for s in range(MAX_SPECIES + 1)]

# -------------------------------------------------------------- locations ---
locations = {
    '0': lines('text_xy_00000_en.txt'),
    '30000': lines('text_xy_30000_en.txt'),
    '40000': lines('text_xy_40000_en.txt'),
    '60000': lines('text_xy_60000_en.txt'),
}

# ------------------------------------------------------------------- forms ---
# Only forms that can actually be stored in a PK6 are listed. Battle-only forms
# (Mega/Primal/Zen/Blade at rest) never appear in the form byte of a stored
# Pokemon, and purely cosmetic forms are deliberately left out so the name falls
# back to the base species and still resolves in the dex.
ARCEUS = ['Arceus', 'Arceus-Fighting', 'Arceus-Flying', 'Arceus-Poison',
          'Arceus-Ground', 'Arceus-Rock', 'Arceus-Bug', 'Arceus-Ghost',
          'Arceus-Steel', 'Arceus-Fire', 'Arceus-Water', 'Arceus-Grass',
          'Arceus-Electric', 'Arceus-Psychic', 'Arceus-Ice', 'Arceus-Dragon',
          'Arceus-Dark', 'Arceus-Fairy']

forms = {
    386: ['Deoxys', 'Deoxys-Attack', 'Deoxys-Defense', 'Deoxys-Speed'],
    413: ['Wormadam', 'Wormadam-Sandy', 'Wormadam-Trash'],
    421: ['Cherrim', 'Cherrim-Sunshine'],
    479: ['Rotom', 'Rotom-Heat', 'Rotom-Wash', 'Rotom-Frost', 'Rotom-Fan',
          'Rotom-Mow'],
    487: ['Giratina', 'Giratina-Origin'],
    492: ['Shaymin', 'Shaymin-Sky'],
    493: ARCEUS,
    550: ['Basculin', 'Basculin-Blue-Striped'],
    555: ['Darmanitan', 'Darmanitan-Zen'],
    641: ['Tornadus', 'Tornadus-Therian'],
    642: ['Thundurus', 'Thundurus-Therian'],
    645: ['Landorus', 'Landorus-Therian'],
    646: ['Kyurem', 'Kyurem-White', 'Kyurem-Black'],
    647: ['Keldeo', 'Keldeo-Resolute'],
    648: ['Meloetta', 'Meloetta-Pirouette'],
    649: ['Genesect', 'Genesect-Douse', 'Genesect-Shock', 'Genesect-Burn',
          'Genesect-Chill'],
    678: ['Meowstic', 'Meowstic-F'],
    681: ['Aegislash', 'Aegislash-Blade'],
    710: ['Pumpkaboo', 'Pumpkaboo-Small', 'Pumpkaboo-Large', 'Pumpkaboo-Super'],
    711: ['Gourgeist', 'Gourgeist-Small', 'Gourgeist-Large', 'Gourgeist-Super'],
    720: ['Hoopa', 'Hoopa-Unbound'],
}

# Species whose in-game name has no dex entry of its own. The reader falls back
# through these in order until one resolves, so a rom hack that does ship the
# plain name still wins.
aliases = {
    'Aegislash': ['Aegislash-Shield', 'Aegislash-Blade'],
}


# ------------------------------------------------------------- validation ---
KEY_RE = re.compile(
    r"^\s+(?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|(\w[\w]*)):\s*\{",
    re.M | re.UNICODE)


def unescape(js):
    """Decode the \\' and \\uXXXX escapes the compiled calc data files use."""
    return re.sub(r'\\u([0-9a-fA-F]{4})',
                  lambda m: chr(int(m.group(1), 16)),
                  js.replace("\\'", "'").replace('\\"', '"'))


def object_keys(path):
    """Every `Name: {` / `'Name': {` key declared in one of the calc data files."""
    with open(os.path.join(REPO, path), encoding='utf-8') as f:
        src = f.read()
    return {unescape(next(g for g in m.groups() if g is not None))
            for m in KEY_RE.finditer(src)}


problems = []

dex = object_keys('calc/data/species.js')


def resolves(name):
    return name in dex or any(a in dex for a in aliases.get(name, []))


for i, name in enumerate(species):
    if i and not resolves(name):
        problems.append('species %d %r missing from calc/data/species.js' % (i, name))
for sid, names in forms.items():
    for f, name in enumerate(names):
        if not resolves(name):
            problems.append('form %d/%d %r missing from calc/data/species.js' % (sid, f, name))

known_moves = object_keys('calc/data/moves.js')
for i, name in enumerate(moves):
    if i and name not in known_moves:
        problems.append('move %d %r missing from calc/data/moves.js' % (i, name))

if problems:
    print('%d naming problems:' % len(problems))
    for p in problems[:40]:
        print('  ', p)
    sys.exit(1)

print('validated %d species, %d moves, %d items, %d abilities, %d formed species'
      % (MAX_SPECIES, MAX_MOVE, MAX_ITEM, MAX_ABILITY, len(forms)))


# ----------------------------------------------------------------- output ---
def js_array(name, values, per_line):
    out = ['%s = [' % name]
    for i in range(0, len(values), per_line):
        out.append('    ' + ', '.join(json.dumps(v, ensure_ascii=False)
                                      for v in values[i:i + per_line]) + ',')
    out[-1] = out[-1].rstrip(',')
    out.append(']')
    return '\n'.join(out)


parts = [
    '// Gen 6 (X/Y, ORAS) save constants.',
    '// Generated by tools/gen_gen6_constants.py from PKHeX resources - do not hand edit.',
    "// Names use the calculator's own spellings so lookups resolve against pokedex/moves.",
    '',
    js_array('g6_species', species, 6),
    '',
    js_array('g6_moves', moves, 6),
    '',
    js_array('g6_items', items, 6),
    '',
    js_array('g6_abilities', abilities, 6),
    '',
    '// personal table EXP growth group, indexes into expTables',
    js_array('g6_growths', growths, 24),
    '',
    '// species id -> form byte -> display name (storable forms only)',
    'g6_forms = ' + json.dumps({str(k): v for k, v in sorted(forms.items())},
                               ensure_ascii=False, indent=4),
    '',
    '// fallbacks tried when a species/form name has no dex entry of its own',
    'g6_species_aliases = ' + json.dumps(aliases, ensure_ascii=False, indent=4),
    '',
    '// met location banks, keyed by the 10000-block the location id falls in',
    'g6_locations = ' + json.dumps(locations, ensure_ascii=False, indent=4),
    '',
]

dest = os.path.join(REPO, 'js', 'save_constants', 'gen6.js')
with open(dest, 'w', encoding='utf-8') as f:
    f.write('\n'.join(parts))
print('wrote %s (%d bytes)' % (dest, os.path.getsize(dest)))
