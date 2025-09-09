// Extra moves for Monster Hunter Emerald
// These are merged into the data.moves map at runtime when type_mod=mh_em
console.log('mhe moves')
window.mheMoves = {
  "Acidic Clash": {
    "basePower": 80,
    "type": "Poison",
    "category": "Physical",
    "secondaries": [{"chance": 100, "boosts": {"def": -1}}]
  },
  "Hyper Tackle": {
    "basePower": 130,
    "type": "Water",
    "category": "Physical",
    "self": { "boosts": { "def": 1 } }
  },
  "Ice Shard": {
    "basePower": 40,
    "type": "Ice",
    "category": "Physical",
    "priority": 1
  },
  "Icicle Crash": {
    "basePower": 85,
    "type": "Ice",
    "category": "Physical",
    "secondaries": [{"chance": 33, "volatileStatus": "flinch"}]
  },
  "Para Fang": {
    "basePower": 20,
    "type": "Electric",
    "category": "Physical",
    "accuracy": 80,
    "makesContact": true,
    "secondaries": [{"chance": 100, "status": "par"}]
  },
  "Psycho Cut": {
    "basePower": 70,
    "type": "Psychic",
    "category": "Physical",
    "highCritRatio": true
  },
  "Shade Slash": {
    "basePower": 40,
    "type": "Ghost",
    "category": "Physical",
    "priority": 1,
    "secondaries": [{"chance": 100, "boosts": {"accuracy": -1}}]
  },
  "Shockspray": {
    "basePower": 90,
    "type": "Water",
    "category": "Special",
    "accuracy": 90,
    "secondaries": [{"chance": 30, "status": "par"}]
  },
  "Sleep Bite": {
    "basePower": 0,
    "type": "Normal",
    "category": "Status",
    "accuracy": 80,
    "secondaries": [{"chance": 100, "status": "slp"}]
  },
  "Sleeping Gas": {
    "basePower": 0,
    "type": "Dark",
    "category": "Status",
    "accuracy": 75,
    "target": "allAdjacent",
    "secondaries": [{"chance": 50, "status": "slp"}]
  },
  "Steel Strike": {
    "basePower": 70,
    "type": "Steel",
    "category": "Physical",
    "secondaries": [{"chance": 50, "boosts": {"def": -1}}]
  },
  "Stygian Powder": {
    "basePower": 55,
    "type": "Dragon",
    "category": "Special",
    "accuracy": 90,
    "secondaries": [{"chance": 100, "boosts": {"spa": -1}}]
  },
  "Wood Hammer": {
    "basePower": 120,
    "type": "Grass",
    "category": "Physical",
    "recoil": [1,3]
  },
  "X-Scissor": {
    "basePower": 80,
    "type": "Bug",
    "category": "Physical"
  },
  "Aqua Fist": {
    "basePower": 70,
    "type": "Water",
    "category": "Physical",
    "secondaries": [{"chance": 30, "boosts": {"spe": -1}}]
  },
  "Aqua Tail": {
    "basePower": 90,
    "type": "Water",
    "category": "Physical"
  },
  "Blade Shot": {
    "basePower": 25,
    "type": "Fighting",
    "category": "Physical",
    "multihit": [2,5]
  },
  "Blood Drain": {
    "basePower": 80,
    "type": "Psychic",
    "category": "Physical",
    "drain": [1,2]
  },
  "Chain Slam": {
    "basePower": 65,
    "type": "Steel",
    "category": "Physical",
    "multihit": 2
  },
  "Demolition Dash": {
    "basePower": 120,
    "type": "Fighting",
    "category": "Physical",
    "secondaries": [{"chance": 100, "volatileStatus": "confusion"}]
  },
  "Discharge": {
    "basePower": 80,
    "type": "Electric",
    "category": "Special",
    "secondaries": [{"chance": 30, "status": "par"}],
    "target": "allAdjacent"
  },
  "Diving Claw": {
    "basePower": 95,
    "type": "Flying",
    "category": "Physical",
    "makesContact": true,
    "secondaries": [{"chance": 30, "status": "psn"}]
  },
  "Dragon Hammer": {
    "basePower": 90,
    "type": "Dragon",
    "category": "Physical"
  },
  "Dragon Pulse": {
    "basePower": 85,
    "type": "Dragon",
    "category": "Special"
  },
  "Drain Punch": {
    "basePower": 75,
    "type": "Fighting",
    "category": "Physical",
    "drain": [1,2],
    "makesContact": true
  },
  "Electroweb": {
    "basePower": 55,
    "type": "Electric",
    "category": "Special",
    "secondaries": [{"chance": 100, "boosts": {"spe": -1}}]
  },
  "Escaton": {
    "basePower": 200,
    "type": "Dragon",
    "category": "Special",
    "priority": -1,
    "breaksProtect": true
    // NOTE: If you want HP-scaling like Eruption, we can add a small engine hook.
  },
  "Fire Lash": {
    "basePower": 80,
    "type": "Fire",
    "category": "Physical",
    "secondaries": [{"chance": 50, "boosts": {"def": -1}}]
  },
  "Flak Fire": {
    "basePower": 40,
    "type": "Fire",
    "category": "Special",
    "priority": 1,
    "secondaries": [{"chance": 30, "status": "brn"}]
  },
  "Flint Chip": {
    "basePower": 50,
    "type": "Rock",
    "category": "Physical",
    "secondaries": [{"chance": 30, "status": "brn"}]
  },
  "Frenzy": {
    "basePower": 0,
    "type": "Poison",
    "category": "Status",
    "breaksProtect": true,
    "secondaries": [{"chance": 100, "status": "tox"}]
  },
  "Gluttony": {
    "basePower": 120,
    "type": "Dragon",
    "category": "Physical",
    "drain": [1,2]
  },
  "Horn Leech": {
    "basePower": 75,
    "type": "Grass",
    "category": "Physical",
    "drain": [1,2]
  },
  "Aeroblast": {
    "category": "Special"
  }
};
