// Gen 6 (X/Y, Omega Ruby/Alpha Sapphire) save reading and editing.
//
// Operates on the raw `main` file inside a 3DS save directory. For Citra that is
//   <citra user dir>/sdmc/Nintendo 3DS/<id0>/<id1>/title/00040000/<title id>/data/00000001/main
// Layout and crypto are ported from PKHeX: PokeCrypto.Decrypt67/Encrypt67,
// BlockInfo6 (CRC16-CCITT over each block), SAV6XY/SAV6AO block tables.

G6_SIZE_STORED = 0xE8
G6_SIZE_PARTY = 0x104
G6_SIZE_BLOCK = 56
G6_BOX_SLOTS = 930 // 31 boxes * 30
G6_BEEF = 0x42454546

G6_LAYOUTS = {
    "ORAS": {
        size: 0x76000,
        blockInfo: 0x75E00,
        party: { id: 18, offset: 0x14200, length: 0x61C },
        box: { id: 56, offset: 0x33000, length: 0x34AD0 }
    },
    "XY": {
        size: 0x65600,
        blockInfo: 0x65400,
        party: { id: 18, offset: 0x14200, length: 0x61C },
        box: { id: 53, offset: 0x22600, length: 0x34AD0 }
    }
}

// destination block <- source block, indexed by (pv >> 13) & 31
G6_BLOCK_POSITION = [
    0, 1, 2, 3, 0, 1, 3, 2, 0, 2, 1, 3, 0, 3, 1, 2,
    0, 2, 3, 1, 0, 3, 2, 1, 1, 0, 2, 3, 1, 0, 3, 2,
    2, 0, 1, 3, 3, 0, 1, 2, 2, 0, 3, 1, 3, 0, 2, 1,
    1, 2, 0, 3, 1, 3, 0, 2, 2, 1, 0, 3, 3, 1, 0, 2,
    2, 3, 0, 1, 3, 2, 0, 1, 1, 2, 3, 0, 1, 3, 2, 0,
    2, 1, 3, 0, 3, 1, 2, 0, 2, 3, 1, 0, 3, 2, 1, 0,

    // duplicates of 0-7 so the shift value never needs a modulus
    0, 1, 2, 3, 0, 1, 3, 2, 0, 2, 1, 3, 0, 3, 1, 2,
    0, 2, 3, 1, 0, 3, 2, 1, 1, 0, 2, 3, 1, 0, 3, 2
]

G6_BLOCK_POSITION_INVERT = [
    0, 1, 2, 4, 3, 5, 6, 7,
    12, 18, 13, 19, 8, 10, 14, 20,
    16, 22, 9, 11, 15, 21, 17, 23,
    0, 1, 2, 4, 3, 5, 6, 7
]

// 3DS private use characters that show up in nicknames
G6_CHARS = {
    0xE08D: "…", 0xE08E: "♂", 0xE08F: "♀", 0xE090: "♠", 0xE091: "♣",
    0xE092: "♥", 0xE093: "♦", 0xE094: "★", 0xE095: "◎", 0xE096: "○",
    0xE097: "□", 0xE098: "△", 0xE099: "◇", 0xE09A: "♪", 0xE09B: "☀",
    0xE09C: "☁", 0xE09D: "☂", 0xE09E: "☃", 0xE09F: "☺", 0xE0A0: "☹"
}

g6Save = false          // true once a gen 6 save is loaded, routes the shared editor entry points
g6Layout = null         // entry of G6_LAYOUTS matched by file size
g6Base = 0              // start of the save inside the uploaded file
g6PartyMons = {}        // display name -> index into g6Party
g6Party = []            // { offset, dec, species, growth }
g6BoxMons = {}          // display name -> { offset, dec, species, growth }
g6File = null           // retained File, re-read by the sync button
g6FileHandle = null     // FileSystemFileHandle when the browser supports it

// ----------------------------------------------------------------- binary ---

function g6ReadU16(data, offset) {
    return data[offset] | (data[offset + 1] << 8)
}

function g6ReadU32(data, offset) {
    return (data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16) | (data[offset + 3] << 24)) >>> 0
}

function g6WriteU16(data, offset, value) {
    data[offset] = value & 0xFF
    data[offset + 1] = (value >>> 8) & 0xFF
}

function g6WriteU32(data, offset, value) {
    data[offset] = value & 0xFF
    data[offset + 1] = (value >>> 8) & 0xFF
    data[offset + 2] = (value >>> 16) & 0xFF
    data[offset + 3] = (value >>> 24) & 0xFF
}

// 32 bit LCG xor stream, applied to every 16 bit word in [start, end)
function g6CryptRegion(data, start, end, seed) {
    let x = seed >>> 0
    for (let i = start; i < end; i += 2) {
        x = (Math.imul(0x41C64E6D, x) + 0x6073) >>> 0
        const word = g6ReadU16(data, i) ^ ((x >>> 16) & 0xFFFF)
        g6WriteU16(data, i, word)
    }
}

// reorders the four 56 byte blocks that follow the 8 byte header
function g6ShuffleBlocks(data, sv) {
    const out = new Uint8Array(data)
    for (let block = 0; block < 4; block++) {
        const source = G6_BLOCK_POSITION[(sv * 4) + block]
        out.set(data.subarray(8 + (G6_SIZE_BLOCK * source), 8 + (G6_SIZE_BLOCK * (source + 1))),
            8 + (G6_SIZE_BLOCK * block))
    }
    return out
}

function g6Decrypt(bytes) {
    const data = new Uint8Array(bytes)
    const pv = g6ReadU32(data, 0)
    const sv = (pv >>> 13) & 31

    g6CryptRegion(data, 8, G6_SIZE_STORED, pv)
    if (data.length > G6_SIZE_STORED) {
        g6CryptRegion(data, G6_SIZE_STORED, data.length, pv)
    }
    return g6ShuffleBlocks(data, sv)
}

function g6Encrypt(dec) {
    const pv = g6ReadU32(dec, 0)
    const sv = G6_BLOCK_POSITION_INVERT[(pv >>> 13) & 31]

    const data = g6ShuffleBlocks(dec, sv)
    g6CryptRegion(data, 8, G6_SIZE_STORED, pv)
    if (data.length > G6_SIZE_STORED) {
        g6CryptRegion(data, G6_SIZE_STORED, data.length, pv)
    }
    return data
}

// sum of the 16 bit words covering the four data blocks
function g6PKMChecksum(dec) {
    let checksum = 0
    for (let i = 8; i < G6_SIZE_STORED; i += 2) {
        checksum = (checksum + g6ReadU16(dec, i)) & 0xFFFF
    }
    return checksum
}

function g6CRC16(data, start, length) {
    let top = 0xFF
    let bot = 0xFF
    for (let i = start; i < start + length; i++) {
        let x = (data[i] ^ top) & 0xFF
        x ^= (x >> 4)
        top = (bot ^ (x >> 3) ^ (x << 4)) & 0xFF
        bot = (x ^ (x << 5)) & 0xFF
    }
    return ((top << 8) | bot) & 0xFFFF
}

function g6SetBlockChecksum(block) {
    const checksum = g6CRC16(view, g6Base + block.offset, block.length)
    g6WriteU16(view, g6Base + g6Layout.blockInfo + 0x14 + (block.id * 8) + 6, checksum)
}

// the save footer is a u64 timestamp pair followed by the "BEEF" magic
function g6DetectLayout(data) {
    for (const name in G6_LAYOUTS) {
        const layout = G6_LAYOUTS[name]
        const base = data.length - layout.size
        if (base < 0) continue
        if (g6ReadU32(data, base + layout.blockInfo + 0x10) == G6_BEEF) {
            return { name: name, layout: layout, base: base }
        }
    }
    return null
}

// ------------------------------------------------------------------ names ---

// Rom hacks and the calculator disagree on a few names, so fall back until
// something resolves in the dex rather than emitting a set nothing can look up.
function g6ResolveSpecies(name) {
    if (typeof pokedex == "undefined" || pokedex[name]) return name

    const aliases = (typeof g6_species_aliases != "undefined" && g6_species_aliases[name]) || []
    for (let i = 0; i < aliases.length; i++) {
        if (pokedex[aliases[i]]) return aliases[i]
    }

    // drop a form suffix the calculator does not carry, e.g. Vivillon-Sandstorm
    const base = name.split("-")[0]
    if (pokedex[base]) return base

    return name
}

function g6SpeciesName(dec, species) {
    let name = g6_species[species]
    const form = dec[0x1D] >> 3
    const forms = g6_forms[species]

    if (form > 0 && forms && forms[form]) {
        name = forms[form]
    }
    return g6ResolveSpecies(name)
}

function g6Nickname(dec) {
    let nickname = ""
    for (let i = 0; i < 12; i++) {
        const code = g6ReadU16(dec, 0x40 + (i * 2))
        if (code == 0) break
        nickname += G6_CHARS[code] || String.fromCharCode(code)
    }
    return nickname
}

function g6MetLocation(id) {
    const bank = id >= 60000 ? 60000 : id >= 40000 ? 40000 : id >= 30000 ? 30000 : 0
    const table = g6_locations[String(bank)] || []
    return table[id - bank] || "Unknown"
}

function g6ExpTable(species) {
    return expTables[g6_growths[species] || 0]
}

// ---------------------------------------------------------------- reading ---

function g6ParsePKM(bytes, offset, isParty) {
    const dec = g6Decrypt(bytes)
    const species = g6ReadU16(dec, 0x08)

    if (species == 0 || !g6_species[species]) return ""

    const iv32 = g6ReadU32(dec, 0x74)
    if ((iv32 >>> 30) & 1) return "" // egg

    const name = g6SpeciesName(dec, species)
    const nickname = g6Nickname(dec)
    const item = g6_items[g6ReadU16(dec, 0x0A)]
    const ability = g6_abilities[dec[0x14]] || ""
    const nature = natures[dec[0x1C]]

    const exp = g6ReadU32(dec, 0x10)
    // party records carry a level directly, but fall back to exp if it is blank
    const level = (isParty && dec[0xEC]) ? dec[0xEC] : get_level(g6ExpTable(species), exp)

    const evs = [dec[0x1E], dec[0x1F], dec[0x20], dec[0x22], dec[0x23], dec[0x21]]
    const ivs = [
        iv32 & 0x1F,
        (iv32 >>> 5) & 0x1F,
        (iv32 >>> 10) & 0x1F,
        (iv32 >>> 20) & 0x1F,
        (iv32 >>> 25) & 0x1F,
        (iv32 >>> 15) & 0x1F
    ]

    const entry = { offset: offset, dec: dec, species: species, growth: g6_growths[species] || 0 }
    if (isParty) {
        g6PartyMons[name] = g6Party.length
        g6Party.push(entry)
    } else if (!g6BoxMons[name]) {
        g6BoxMons[name] = entry
    }

    let text = nickname && nickname.toLowerCase() != name.toLowerCase()
        ? `${nickname} (${name})`
        : `${name}`

    if (item) text += ` @ ${item}`

    text += "\n"
    text += `Level: ${level}\n`
    text += `${nature} Nature\n`
    if (ability) text += `Ability: ${ability}\n`
    text += `EVs: ${evs[0]} HP / ${evs[1]} Atk / ${evs[2]} Def / ${evs[3]} SpA / ${evs[4]} SpD / ${evs[5]} Spe\n`
    text += `IVs: ${ivs[0]} HP / ${ivs[1]} Atk / ${ivs[2]} Def / ${ivs[3]} SpA / ${ivs[4]} SpD / ${ivs[5]} Spe\n`

    for (let i = 0; i < 4; i++) {
        text += `- ${g6_moves[g6ReadU16(dec, 0x5A + (i * 2))] || "(No Move)"}\n`
    }

    text += `Met: ${g6MetLocation(g6ReadU16(dec, 0xDA))}\n\n`
    return text
}

function g6ReadSave(buffer, fileName) {
    const data = new Uint8Array(buffer)
    const detected = g6DetectLayout(data)

    if (!detected) {
        alert("That does not look like a gen 6 save. Upload the `main` file from your 3DS/Citra save folder.")
        return false
    }

    view = data
    g6Layout = detected.layout
    g6Base = detected.base
    g6Save = true
    saveUploaded = true
    saveFileName = fileName
    savExt = ""

    g6PartyMons = {}
    g6Party = []
    g6BoxMons = {}

    const partyOffset = g6Base + g6Layout.party.offset
    partyCount = view[partyOffset + (6 * G6_SIZE_PARTY)]

    let showdownImport = ""

    for (let i = 0; i < Math.min(partyCount, 6); i++) {
        const offset = partyOffset + (i * G6_SIZE_PARTY)
        showdownImport += g6ParsePKM(view.subarray(offset, offset + G6_SIZE_PARTY), offset, true)
    }

    const boxOffset = g6Base + g6Layout.box.offset
    for (let i = 0; i < G6_BOX_SLOTS; i++) {
        const offset = boxOffset + (i * G6_SIZE_STORED)
        showdownImport += g6ParsePKM(view.subarray(offset, offset + G6_SIZE_STORED), offset, false)
    }

    $('.import-team-text').val(showdownImport)

    changelog = "<h4>Changelog:</h4>"
    changelog += `<p>${fileName} loaded (${detected.name}, ${g6Party.length} in party)</p>`
    if ($('#changelog').length == 0) {
        $('#clearSets').after("<p id='changelog'></p>")
    }
    $('#changelog').html(changelog).show()

    g6AddSyncBtn()
    return true
}

// ---------------------------------------------------------------- editing ---

function g6SetExp(entry, level, edge) {
    const table = expTables[entry.growth]
    const current = g6ReadU32(entry.dec, 0x10)

    // leave partial progress alone when the level on screen has not moved
    if (!edge && get_level(table, current) == level) return current

    // edging leaves the mon one point short of the next level
    const exp = edge ? table[level] - 1 : table[level - 1]
    g6WriteU32(entry.dec, 0x10, exp)
    return exp
}

function g6UpdateProps(entry) {
    const dec = entry.dec

    const item = $('#itemL1').val()
    const itemIndex = item ? g6_items.indexOf(item) : 0
    if (itemIndex > -1) g6WriteU16(dec, 0x0A, itemIndex)

    const abilityIndex = g6_abilities.indexOf($('#abilityL1').val())
    if (abilityIndex > 0) dec[0x14] = abilityIndex

    const natureIndex = natures.indexOf($('#natureL1').val())
    if (natureIndex > -1) dec[0x1C] = natureIndex

    dec[0x1E] = parseInt($('#p1').find('.hp .evs').val()) || 0
    dec[0x1F] = parseInt($('#p1').find('.at .evs').val()) || 0
    dec[0x20] = parseInt($('#p1').find('.df .evs').val()) || 0
    dec[0x21] = parseInt($('#p1').find('.sp .evs').val()) || 0
    dec[0x22] = parseInt($('#p1').find('.sa .evs').val()) || 0
    dec[0x23] = parseInt($('#p1').find('.spd .evs').val()) || 0

    dec[0xCA] = 255 // max friendship

    // the calculator shows rom hack move names, so map them back before writing
    const reverseMoveChanges = {}
    if (typeof moveChanges[TITLE] != "undefined") {
        for (const original in moveChanges[TITLE]) {
            reverseMoveChanges[moveChanges[TITLE][original]] = original
        }
    }

    for (let i = 0; i < 4; i++) {
        let moveName = $(`.move${i + 1} .select2-container`).first().text().trim()
        if (reverseMoveChanges[moveName]) moveName = reverseMoveChanges[moveName]

        const moveIndex = g6_moves.indexOf(moveName)
        if (moveIndex > -1) g6WriteU16(dec, 0x5A + (i * 2), moveIndex)
    }
}

// party stats live outside the four encrypted blocks but inside the same record
function g6UpdateBattleStats(entry, speciesName, level, batch) {
    const dec = entry.dec
    const set = customSets[speciesName] && customSets[speciesName]["My Box"]
    const pokeinfo = pokedex[speciesName]

    if (!set || !pokeinfo) {
        console.log(`no imported set for ${speciesName}, leaving party stats alone`)
        return
    }

    if (typeof set.ivs === 'undefined') set.ivs = { hp: 31, at: 31, df: 31, sa: 31, sd: 31, sp: 31 }
    if (typeof set.evs === 'undefined') set.evs = { hp: 0, at: 0, df: 0, sa: 0, sd: 0, sp: 0 }

    const mods = [natMods[set.nature].plus, natMods[set.nature].minus]
    const hp = getStat(mods, 'hp', pokeinfo.bs.hp, set.ivs.hp, set.evs.hp, level)
    const at = getStat(mods, 'atk', pokeinfo.bs.at, set.ivs.at, set.evs.at, level)
    const df = getStat(mods, 'def', pokeinfo.bs.df, set.ivs.df, set.evs.df, level)
    const sa = getStat(mods, 'spa', pokeinfo.bs.sa, set.ivs.sa, set.evs.sa, level)
    const sd = getStat(mods, 'spd', pokeinfo.bs.sd, set.ivs.sd, set.evs.sd, level)
    const sp = getStat(mods, 'spe', pokeinfo.bs.sp, set.ivs.sp, set.evs.sp, level)

    if ([hp, at, df, sa, sd, sp].includes(0)) {
        alert("Something went wrong building party stats, please refresh and try again.")
        return
    }

    dec[0xEC] = level
    g6WriteU16(dec, 0xF0, hp)
    g6WriteU16(dec, 0xF2, hp)
    g6WriteU16(dec, 0xF4, at)
    g6WriteU16(dec, 0xF6, df)
    g6WriteU16(dec, 0xF8, sp)
    g6WriteU16(dec, 0xFA, sa)
    g6WriteU16(dec, 0xFC, sd)

    // only touch live battle state when editing a single mon by hand
    if (batch) return

    const currentHp = parseInt($('#currentHpL1').val())
    if (!isNaN(currentHp)) g6WriteU16(dec, 0xF0, currentHp)
    g6WriteU32(dec, 0xE8, g6StatusValue($('#statusL1').val()))
}

function g6StatusValue(status) {
    if (status == "Asleep") return 1
    if (status == "Poisoned") return 1 << 3
    if (status == "Burned") return 1 << 4
    if (status == "Frozen") return 1 << 5
    if (status == "Paralyzed") return 1 << 6
    if (status == "Badly Poisoned") return 1 << 7
    return 0
}

function g6WriteEntry(entry) {
    const checksum = g6PKMChecksum(entry.dec)
    g6WriteU16(entry.dec, 0x06, checksum)
    view.set(g6Encrypt(entry.dec), entry.offset)
}

function g6UpdatePartyPKMN(edge, speciesNameOverride) {
    const speciesName = speciesNameOverride || $('.set-selector')[0].value.split("(")[0].trim()
    const partyIndex = g6PartyMons[speciesName]

    if (typeof partyIndex === 'undefined') {
        return g6UpdateBoxPKMN(edge, speciesNameOverride)
    }

    const entry = g6Party[partyIndex]
    const batch = speciesNameOverride != false && speciesNameOverride != undefined
    const level = batch ? desiredLevel - 1 : parseInt($('#levelL1').val())

    if (!level) {
        alert("Could not read a level to write, please refresh and try again.")
        return
    }

    if (!batch) g6UpdateProps(entry)
    g6SetExp(entry, level, edge)
    g6UpdateBattleStats(entry, speciesName, level, batch)
    g6WriteEntry(entry)

    changelog += `<p>Party ${speciesName} updated</p>`
    $('#changelog').html(changelog)

    g6SetBlockChecksum(g6Layout.party)
    addSaveBtn()
}

function g6UpdateBoxPKMN(edge, speciesNameOverride) {
    const speciesName = speciesNameOverride || $('.set-selector')[0].value.split("(")[0].trim()
    const entry = g6BoxMons[speciesName]

    if (!entry) {
        alert(`${speciesName} was not found in the loaded save.`)
        return
    }

    const level = speciesNameOverride ? desiredLevel - 1 : parseInt($('#levelL1').val())
    if (!speciesNameOverride) g6UpdateProps(entry)
    g6SetExp(entry, level, edge)
    g6WriteEntry(entry)

    changelog += `<p>${speciesName} updated</p>`
    $('#changelog').html(changelog)

    g6SetBlockChecksum(g6Layout.box)
    addSaveBtn()
}

function g6EdgeSelected() {
    const selected = getSelectedPoks()

    if (selected.length == 0) {
        alert("Nothing selected")
        return
    }

    desiredLevel = parseInt(prompt("Edge selection to level: "))
    if (!desiredLevel) return

    for (let i = 0; i < selected.length; i++) {
        const boxEntry = g6BoxMons[selected[i]]

        if (typeof g6PartyMons[selected[i]] !== 'undefined') {
            g6UpdatePartyPKMN(true, selected[i])
            continue
        }

        if (!boxEntry) {
            console.log(`${selected[i]} not found in save`)
            continue
        }

        g6SetExp(boxEntry, desiredLevel - 1, true)
        g6WriteEntry(boxEntry)
        changelog += `<p>${selected[i]} edged to level ${desiredLevel - 1}</p>`
    }

    g6SetBlockChecksum(g6Layout.party)
    g6SetBlockChecksum(g6Layout.box)
    addSaveBtn()

    $('#changelog').html(changelog)
}

function g6Bedtime() {
    for (let i = 0; i < g6Party.length; i++) {
        g6WriteU32(g6Party[i].dec, 0xE8, 1)
        g6WriteEntry(g6Party[i])
    }

    changelog += `<p>Party set to 1 turn sleep</p>`
    $('#changelog').html(changelog)

    g6SetBlockChecksum(g6Layout.party)
    addSaveBtn()
}

function g6DownloadSave() {
    const blob = new Blob([view], { type: 'application/octet-stream' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = saveFileName || "main"

    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
}

// ----------------------------------------------------------------- loading ---

function g6LoadFile(file) {
    if (!file) return

    const reader = new FileReader()
    reader.onload = function (e) {
        try {
            g6ReadSave(e.target.result, file.name)
        } catch (error) {
            console.error(error)
            alert("Failed to read that save file. It may be corrupted or from a different game.")
        }
    }
    reader.readAsArrayBuffer(file)
}

// Re-reads whatever was opened last so the box refreshes after saving in game.
// A picked file handle can always be re-read, a plain upload only sometimes can.
async function g6SyncSave() {
    try {
        const file = g6FileHandle ? await g6FileHandle.getFile() : g6File
        if (!file) {
            alert("Load a save first.")
            return
        }

        const buffer = await file.arrayBuffer()
        if (!g6ReadSave(buffer, file.name)) return

        $('#import').click()
        $('#sync-sav').text("Synced!")
        setTimeout(function () { $('#sync-sav').text("Sync Save") }, 1000)
    } catch (error) {
        console.error(error)
        alert("Could not re-read the save file. Pick it again with Read 3DS Save.")
    }
}

function g6AddSyncBtn() {
    if ($('#sync-sav').length > 0) return
    $('#read-save').after(`<button id="sync-sav" class="bs-btn bs-btn-default" onClick='g6SyncSave()'>Sync Save</button>`)
}

// Called once the gen 6 constants have loaded. Prefers the file picker so that
// syncing keeps working after the game writes to the file again.
function g6Init() {
    $('#save-upload-3ds').on('change', function (event) {
        g6File = event.target.files[0]
        g6FileHandle = null
        g6LoadFile(g6File)
    })

    if (!window.showOpenFilePicker) {
        // without a handle the input has to be cleared or picking the same file
        // a second time never fires a change event
        $('#read-save').on('click', function () {
            if ($('#save-upload-3ds').length) $('#save-upload-3ds')[0].value = null
        })
        return
    }

    $('#read-save').on('click', async function (event) {
        event.preventDefault()
        try {
            const handles = await window.showOpenFilePicker({
                id: 'dynamic-calc-3ds-save',
                types: [{ description: '3DS save', accept: { 'application/octet-stream': ['.sav', '.bin', '.dsv', ''] } }]
            })
            g6FileHandle = handles[0]
            g6File = await g6FileHandle.getFile()
            g6LoadFile(g6File)
        } catch (error) {
            if (error && error.name != 'AbortError') console.error(error)
        }
    })
}
