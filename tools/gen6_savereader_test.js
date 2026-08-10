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
const imports = { count: 0 };
const noop = () => stub();
const stub = () => ({
    length: 0, val: noop, html: noop, show: noop, after: noop, text: noop,
    attr: noop, on: noop, click: noop, find: noop, first: noop
});
const $ = (sel) => {
    if (sel === '.import-team-text') {
        return { length: 1, val: (v) => { if (v === undefined) return textarea.value; textarea.value = v; } };
    }
    if (sel === '#import') return Object.assign(stub(), { click: () => { imports.count++; } });
    return stub();
};

const sandbox = {
    console, $, jQuery: $, window: {}, document: { createElement: () => ({}) },
    alert: (m) => console.log('    [alert] ' + m),
    setTimeout, setInterval, clearInterval,
    Blob: function () { }, FileReader: function () { },
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

// party members carry the marker addSets turns into the player party preview
const marked = text.split('\n').filter(l => l.includes(' |Party'));
check('every party member is tagged for the party preview', marked.length === expected.partyParsed,
    `got ${marked.length}: ${JSON.stringify(marked)}`);
check('no box mon is tagged for the party preview',
    marked.every(l => Object.keys(sandbox.g6PartyMons).some(n => l.includes(n))));
check('the marker sits before the item so addSets can recover both',
    marked.every(l => !l.includes('@') || l.indexOf(' |Party') < l.indexOf('@')));

// gen 5+ stores a status enum, not the gen 1-4 bitfield
check('Asleep writes the gen 5+ sleep enum value', sandbox.g6StatusValue('Asleep') === 2);
check('Paralyzed writes the gen 5+ paralysis enum value', sandbox.g6StatusValue('Paralyzed') === 1);
check('Healthy clears the status', sandbox.g6StatusValue('Healthy') === 0);

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

// ------------------------------------------------------------- auto sync ---
// The picker itself cannot be driven headlessly, but everything the poll loop
// decides can be, using a stand-in for the file handle the browser would give.
(async () => {
    console.log('auto sync');

    const good = fs.readFileSync(path.join(SCRATCH, 'synthetic_oras.main'));
    let served = good;
    let mtime = 1000;
    sandbox.g6SaveFileHandle = {
        getFile: async () => ({
            name: 'main',
            lastModified: mtime,
            arrayBuffer: async () => served.buffer.slice(served.byteOffset, served.byteOffset + served.length)
        })
    };

    sandbox.g6ReadSave(good.buffer.slice(0), 'main');
    sandbox.g6LastModified = mtime;
    sandbox.g6Dirty = false;

    imports.count = 0;
    await sandbox.g6PollSave();
    check('an untouched file does not re-import', imports.count === 0, `${imports.count} imports`);

    mtime = 2000;
    await sandbox.g6PollSave();
    check('a changed file re-imports', imports.count === 1, `${imports.count} imports`);
    check('the new mtime is recorded', sandbox.g6LastModified === 2000);

    imports.count = 0;
    await sandbox.g6PollSave();
    check('the same change does not re-import twice', imports.count === 0, `${imports.count} imports`);

    // a save written mid-game-write fails layout detection and must be retried
    served = Buffer.alloc(good.length);
    mtime = 3000;
    await sandbox.g6PollSave();
    check('a torn read is skipped', imports.count === 0, `${imports.count} imports`);
    check('a torn read leaves the mtime alone so it retries', sandbox.g6LastModified === 2000,
        `got ${sandbox.g6LastModified}`);

    served = good;
    await sandbox.g6PollSave();
    check('the retry after a torn read succeeds', imports.count === 1 && sandbox.g6LastModified === 3000);

    // unwritten edits must not be silently thrown away by a background re-read
    sandbox.g6Dirty = true;
    imports.count = 0;
    mtime = 4000;
    sandbox.g6AutoSyncTimer = sandbox.setInterval(() => { }, 1000);
    await sandbox.g6PollSave();
    check('a change with unsaved edits pauses instead of re-importing', imports.count === 0);
    check('auto sync is stopped when it pauses', sandbox.g6AutoSyncTimer === null);
    sandbox.g6Dirty = false;

    // ---------------------------------------------------------- backups ---
    console.log('auto backup');

    // stand-in for the backup folder the directory picker would hand over
    const written = new Map();
    const removed = [];
    sandbox.g6BackupDirHandle = {
        getFileHandle: async (name) => ({
            createWritable: async () => ({
                write: async (data) => { written.set(name, data.length || data.byteLength); },
                close: async () => { }
            })
        }),
        removeEntry: async (name) => { written.delete(name); removed.push(name); },
        values: async function* () {
            for (const name of written.keys()) yield { kind: 'file', name };
        }
    };

    await sandbox.g6BackupSave();
    check('a backup is written', written.size === 1, [...written.keys()].join());
    const backupName = [...written.keys()][0];
    check('the backup carries the whole save', written.get(backupName) === good.length,
        `${written.get(backupName)} vs ${good.length}`);
    check('the backup name is prefixed so pruning cannot touch anything else',
        backupName.startsWith(sandbox.G6_BACKUP_PREFIX), backupName);
    check('the backup name sorts chronologically',
        /^dyncalc-main-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}$/.test(backupName), backupName);

    // fill past the cap, plus files the calc did not write
    written.clear();
    for (let i = 0; i < sandbox.G6_BACKUP_KEEP + 5; i++) {
        written.set(`${sandbox.G6_BACKUP_PREFIX}2026-01-01T00-00-${String(i).padStart(2, '0')}`, good.length);
    }
    written.set('main', 1);
    written.set('my-own-backup.sav', 1);

    const prunedCount = await sandbox.g6PruneBackups();
    const survivors = [...written.keys()].filter(n => n.startsWith(sandbox.G6_BACKUP_PREFIX));
    check('pruning trims down to the cap', survivors.length === sandbox.G6_BACKUP_KEEP,
        `${survivors.length} left, ${prunedCount} pruned`);
    check('pruning removes the oldest first',
        removed.every(n => n < survivors[0]), `removed ${removed.slice(0, 3).join()}`);
    check('pruning never touches files the calc did not write',
        written.has('main') && written.has('my-own-backup.sav'));

    // a failing backup must not take syncing down with it
    sandbox.g6BackupDirHandle = {
        getFileHandle: async () => { throw new Error('permission lapsed'); },
        values: async function* () { },
        removeEntry: async () => { }
    };
    await sandbox.g6BackupSave();
    check('a failed backup disables itself instead of throwing', sandbox.g6BackupDirHandle === null);

    check('an upload with no handle cannot auto sync',
        (sandbox.g6SaveFileHandle = null, sandbox.g6FileHandle = null, sandbox.g6CanAutoSync() === false));

    console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILURES`);
    process.exit(failures === 0 ? 0 : 1);
})();
