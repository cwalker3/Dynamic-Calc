// Tests js/savereader_gen6.js against real PK6 records inside a synthetic ORAS save.
//
//   python3 tools/gen6_fixture.py <scratch-dir>     # build the fixtures first
//   node tools/gen6_savereader_test.js <scratch-dir>
//
// See tools/gen6_fixture.py for what the scratch dir needs. Everything the
// browser normally supplies (jQuery, the DOM, the dex) is stubbed out here, so
// this only covers the binary layer: crypto, save layout, parsing and writing.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO = path.dirname(__dirname);
const SCRATCH = process.argv[2] || path.join(__dirname, 'gen6fixtures');

for (const required of ['pk6', 'synthetic_oras.main', 'synthetic_expected.json', 'crypto_vectors.json']) {
    if (!fs.existsSync(path.join(SCRATCH, required))) {
        console.error(`missing ${required} in ${SCRATCH} - run tools/gen6_fixture.py first`);
        process.exit(2);
    }
}

let failures = 0;
function check(name, cond, extra) {
    if (cond) console.log(`  ok   ${name}`);
    else { failures++; console.log(`  FAIL ${name}${extra ? ' :: ' + extra : ''}`); }
}

// ------------------------------------------------------------- dom stubs ---
const textarea = { value: '' };
const noop = () => stub();
const stub = () => ({
    length: 0, val: noop, html: noop, show: noop, after: noop, text: noop,
    attr: noop, on: noop, click: noop, find: noop, first: noop
});
const $ = (sel) => sel === '.import-team-text'
    ? { length: 1, val: (v) => { if (v === undefined) return textarea.value; textarea.value = v; } }
    : stub();

const sandbox = {
    console, $, jQuery: $, window: {}, document: { createElement: () => ({}) },
    alert: (m) => console.log('    [alert] ' + m),
    setTimeout, Blob: function () { }, FileReader: function () { },
    URL: { createObjectURL: () => '', revokeObjectURL: () => { } },
    TITLE: 'Rising Ruby/Sinking Saphire', moveChanges: {}, customSets: {}, natMods: {}
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

const load = (file) => vm.runInContext(
    fs.readFileSync(path.join(REPO, file), 'utf8'), sandbox, { filename: file });

load('js/enums.js');
load('js/save_constants/gen6.js');
load('js/savereader_gen6.js');

// every name resolves, so g6ResolveSpecies leaves the table values alone
sandbox.pokedex = new Proxy({}, { get: () => ({ bs: {} }), has: () => true });

// ------------------------------------------------------- crypto contract ---
console.log('crypto');
const pk6files = fs.readdirSync(path.join(SCRATCH, 'pk6')).filter(f => f.endsWith('.pk6'));
let cryptoOk = true, checksumOk = true;
for (const file of pk6files) {
    const dec = new Uint8Array(fs.readFileSync(path.join(SCRATCH, 'pk6', file)));
    if (sandbox.g6PKMChecksum(dec) !== (dec[6] | (dec[7] << 8))) {
        checksumOk = false;
        console.log('    checksum mismatch ' + file);
    }
    if (Buffer.compare(Buffer.from(sandbox.g6Decrypt(sandbox.g6Encrypt(dec))), Buffer.from(dec)) !== 0) {
        cryptoOk = false;
        console.log('    roundtrip mismatch ' + file);
    }
}
check(`checksum matches the stored value for all ${pk6files.length} real pk6 records`, checksumOk);
check('encrypt -> decrypt is identity for all real pk6 records', cryptoOk);

const vectors = JSON.parse(fs.readFileSync(path.join(SCRATCH, 'crypto_vectors.json'), 'utf8'));
const vecOk = vectors.every(v => Buffer.compare(
    Buffer.from(sandbox.g6Decrypt(new Uint8Array(Buffer.from(v.encrypted, 'base64')))),
    Buffer.from(v.decrypted, 'base64')) === 0);
check(`decrypt matches the reference implementation on ${vectors.length} random vectors`, vecOk);

// ----------------------------------------------------------- save layout ---
console.log('save parsing');
const bytes = new Uint8Array(fs.readFileSync(path.join(SCRATCH, 'synthetic_oras.main')));
const expected = JSON.parse(fs.readFileSync(path.join(SCRATCH, 'synthetic_expected.json'), 'utf8'));

const detected = sandbox.g6DetectLayout(bytes);
check('detects the ORAS layout from the BEEF footer', detected && detected.name === 'ORAS');
check('g6ReadSave succeeds', sandbox.g6ReadSave(bytes.buffer.slice(0), 'main') === true);

const text = textarea.value;
check('party count read from the save', sandbox.partyCount === expected.partyCountByte,
    `got ${sandbox.partyCount}`);
for (const species of expected.species) check(`contains ${species}`, text.includes(species));
for (const egg of expected.eggSpecies) check(`skips the ${egg} egg record`, !text.includes(egg));
check('box mons indexed for editing', Object.keys(sandbox.g6BoxMons).length === expected.boxCount,
    `got ${Object.keys(sandbox.g6BoxMons).length}`);
check('party mons indexed for editing', Object.keys(sandbox.g6PartyMons).length === expected.partyParsed,
    `got ${Object.keys(sandbox.g6PartyMons).length}`);

// --------------------------------------------------------------- editing ---
console.log('editing');
const live = sandbox.view; // g6ReadSave keeps its own copy, edits land there
const entry = sandbox.g6BoxMons[Object.keys(sandbox.g6BoxMons)[0]];
const beforeExp = sandbox.g6ReadU32(entry.dec, 0x10);
const table = sandbox.expTables[entry.growth];

sandbox.g6SetExp(entry, 49, true);
check('edging writes one exp short of the target level',
    sandbox.g6ReadU32(entry.dec, 0x10) === table[49] - 1);
check('edged exp actually changed', sandbox.g6ReadU32(entry.dec, 0x10) !== beforeExp);

sandbox.g6WriteEntry(entry);
const reread = sandbox.g6Decrypt(live.subarray(entry.offset, entry.offset + 0xE8));
check('written record decrypts back to what was edited',
    Buffer.compare(Buffer.from(reread), Buffer.from(entry.dec)) === 0);
check('written record carries a valid checksum',
    sandbox.g6PKMChecksum(reread) === (reread[6] | (reread[7] << 8)));

const chkOffset = sandbox.g6Base + sandbox.g6Layout.blockInfo + 0x14 + (sandbox.g6Layout.box.id * 8) + 6;
const stale = live[chkOffset] | (live[chkOffset + 1] << 8);
sandbox.g6SetBlockChecksum(sandbox.g6Layout.box);
const recomputed = sandbox.g6CRC16(live, sandbox.g6Base + sandbox.g6Layout.box.offset, sandbox.g6Layout.box.length);
const stored = live[chkOffset] | (live[chkOffset + 1] << 8);
check('box block checksum refreshed after the edit', recomputed === stored && stale !== stored,
    `stale ${stale} -> ${stored}, recomputed ${recomputed}`);

check('edited save re-reads cleanly', sandbox.g6ReadSave(live.buffer.slice(0), 'main') === true);
check('edited level visible after reload', textarea.value.includes('Level: 49'));

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILURES`);
process.exit(failures === 0 ? 0 : 1);
