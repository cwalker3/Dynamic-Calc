"""Builds the fixtures used by tools/gen6_savereader_test.js.

    python3 tools/gen6_fixture.py <scratch-dir>

<scratch-dir> needs a `pk6/` folder of real .pk6 records (the ones in
kwsch/PKHeX under Tests/PKHeX.Core.Tests/Legality work well) and the
text_Species_en.txt resource used by tools/gen_gen6_constants.py.

It writes three files next to them:
    synthetic_oras.main     an ORAS save with those records in the party and boxes
    synthetic_expected.json what the reader is expected to pull out of it
    crypto_vectors.json     decrypt vectors from the reference implementation below

The crypto here is transcribed straight from PKHeX's PokeCrypto (Decrypt67 /
Encrypt67) and BlockInfo6, deliberately independent of the JavaScript, so the
test compares two separate ports rather than one port against itself.
"""
import base64
import glob
import json
import os
import random
import struct
import sys

SIZE_6STORED = 0xE8
SIZE_6PARTY = 0x104
SIZE_6BLOCK = 56

SAVE_SIZE = 0x76000
BLOCK_INFO = 0x75E00
PARTY = 0x14200
PARTY_BLOCK = 18
PARTY_LEN = 0x61C
BOX = 0x33000
BOX_BLOCK = 56
BOX_LEN = 0x34AD0
BEEF = 0x42454546

BLOCK_POSITION = [
    0, 1, 2, 3,  0, 1, 3, 2,  0, 2, 1, 3,  0, 3, 1, 2,
    0, 2, 3, 1,  0, 3, 2, 1,  1, 0, 2, 3,  1, 0, 3, 2,
    2, 0, 1, 3,  3, 0, 1, 2,  2, 0, 3, 1,  3, 0, 2, 1,
    1, 2, 0, 3,  1, 3, 0, 2,  2, 1, 0, 3,  3, 1, 0, 2,
    2, 3, 0, 1,  3, 2, 0, 1,  1, 2, 3, 0,  1, 3, 2, 0,
    2, 1, 3, 0,  3, 1, 2, 0,  2, 3, 1, 0,  3, 2, 1, 0,
    0, 1, 2, 3,  0, 1, 3, 2,  0, 2, 1, 3,  0, 3, 1, 2,
    0, 2, 3, 1,  0, 3, 2, 1,  1, 0, 2, 3,  1, 0, 3, 2,
]

BLOCK_POSITION_INVERT = [
    0, 1, 2, 4, 3, 5, 6, 7,
    12, 18, 13, 19, 8, 10, 14, 20,
    16, 22, 9, 11, 15, 21, 17, 23,
    0, 1, 2, 4, 3, 5, 6, 7,
]


def crypt_array(data, start, end, seed):
    for i in range(start, end, 2):
        seed = (0x41C64E6D * seed + 0x00006073) & 0xFFFFFFFF
        word = struct.unpack_from('<H', data, i)[0] ^ ((seed >> 16) & 0xFFFF)
        struct.pack_into('<H', data, i, word)


def shuffle(data, sv):
    out = bytearray(data)
    for block in range(4):
        src = 8 + (SIZE_6BLOCK * BLOCK_POSITION[(sv * 4) + block])
        dst = 8 + (SIZE_6BLOCK * block)
        out[dst:dst + SIZE_6BLOCK] = data[src:src + SIZE_6BLOCK]
    return out


def decrypt(ekm):
    data = bytearray(ekm)
    pv = struct.unpack_from('<I', data, 0)[0]
    crypt_array(data, 8, SIZE_6STORED, pv)
    if len(data) > SIZE_6STORED:
        crypt_array(data, SIZE_6STORED, len(data), pv)
    return shuffle(data, (pv >> 13) & 31)


def encrypt(pkm):
    data = bytearray(pkm)
    pv = struct.unpack_from('<I', data, 0)[0]
    data = shuffle(data, BLOCK_POSITION_INVERT[(pv >> 13) & 31])
    crypt_array(data, 8, SIZE_6STORED, pv)
    if len(data) > SIZE_6STORED:
        crypt_array(data, SIZE_6STORED, len(data), pv)
    return data


def checksum(dec):
    total = 0
    for i in range(8, SIZE_6STORED, 2):
        total = (total + struct.unpack_from('<H', dec, i)[0]) & 0xFFFF
    return total


def crc16_ccitt(data, start, length):
    top = bot = 0xFF
    for i in range(start, start + length):
        x = data[i] ^ top
        x ^= (x >> 4)
        top = (bot ^ (x >> 3) ^ (x << 4)) & 0xFF
        bot = (x ^ (x << 5)) & 0xFF
    return ((top << 8) | bot) & 0xFFFF


def main(scratch):
    species_names = open(os.path.join(scratch, 'text_Species_en.txt'),
                         encoding='utf-8-sig').read().split('\n')

    records = []
    for path in sorted(glob.glob(os.path.join(scratch, 'pk6', '*.pk6'))):
        data = bytearray(open(path, 'rb').read())
        sid = struct.unpack_from('<H', data, 8)[0]
        iv32 = struct.unpack_from('<I', data, 0x74)[0]
        records.append({
            'data': data,
            'species': sid,
            'form': data[0x1D] >> 3,
            'name': species_names[sid],
            'egg': bool((iv32 >> 30) & 1),
        })

    if not records:
        sys.exit(f'no .pk6 records found in {os.path.join(scratch, "pk6")}')

    # the party takes a few full size records plus an egg, so egg skipping gets
    # covered; a level goes into the party stats since PKHeX blanks them on export
    pool = [r for r in records if len(r['data']) == SIZE_6PARTY]
    party = [r for r in pool if not r['egg']][:4] + [r for r in pool if r['egg']][:1]
    box = [r for r in records if len(r['data']) == SIZE_6STORED]

    save = bytearray(SAVE_SIZE)
    struct.pack_into('<I', save, BLOCK_INFO + 0x10, BEEF)

    for i, rec in enumerate(party):
        data = bytearray(rec['data'])
        data[0xEC] = 40  # Stat_Level
        struct.pack_into('<H', data, 6, checksum(data))
        rec['data'] = data
        save[PARTY + (i * SIZE_6PARTY):PARTY + ((i + 1) * SIZE_6PARTY)] = encrypt(data)
    save[PARTY + (6 * SIZE_6PARTY)] = len(party)

    for i, rec in enumerate(box):
        save[BOX + (i * SIZE_6STORED):BOX + ((i + 1) * SIZE_6STORED)] = encrypt(rec['data'])

    struct.pack_into('<H', save, BLOCK_INFO + 0x14 + (PARTY_BLOCK * 8) + 6,
                     crc16_ccitt(save, PARTY, PARTY_LEN))
    struct.pack_into('<H', save, BLOCK_INFO + 0x14 + (BOX_BLOCK * 8) + 6,
                     crc16_ccitt(save, BOX, BOX_LEN))

    open(os.path.join(scratch, 'synthetic_oras.main'), 'wb').write(save)

    def display(rec):
        # the only alt form in the sample set
        if rec['species'] == 645 and rec['form'] == 1:
            return 'Landorus-Therian'
        return rec['name']

    expected = {
        'partyCountByte': len(party),
        'partyParsed': len([r for r in party if not r['egg']]),
        'boxCount': len({display(r) for r in box if not r['egg']}),
        'species': sorted({display(r) for r in party + box if not r['egg']}),
        'eggSpecies': sorted({r['name'] for r in records if r['egg']}),
    }
    json.dump(expected, open(os.path.join(scratch, 'synthetic_expected.json'), 'w'), indent=2)

    random.seed(6)
    vectors = []
    for _ in range(64):
        size = random.choice([SIZE_6STORED, SIZE_6PARTY])
        enc = bytearray(random.getrandbits(8) for _ in range(size))
        vectors.append({
            'encrypted': base64.b64encode(bytes(enc)).decode(),
            'decrypted': base64.b64encode(bytes(decrypt(enc))).decode(),
        })
    json.dump(vectors, open(os.path.join(scratch, 'crypto_vectors.json'), 'w'))

    print('party:', [r['name'] for r in party])
    print('box:', [r['name'] for r in box])
    print('wrote fixtures to', scratch)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'gen6fixtures'))
