"""
check_content.py

Checks the files in content/ against the level data before they go to the GUI. Run it after any content edit:

    python check_content.py

It exits with an error and lists every problem it finds. It checks that:
- every record in each level has a hint, and every hint belongs to a real record
- each level's guided record exists and is honest (the walkthrough must not give away an answer)
- each level unlocks every reason its records need, and every reason has a stamp, an in-shift note and a debrief message
- each level has three questions, multiple-choice answers are valid options, and referenced records exist
- every tool a level or walkthrough uses is defined, and every {placeholder} is one the game knows how to fill
- each shift's pass limits are below its number of violations and honest records
- the final challenge's starting state is solvable in the worst case
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLACEHOLDERS = {"owner", "chip", "counter", "last_counter", "total_flops", "total_energy", "flop_limit", "energy_limit",
                "energy_margin_limit", "ratio", "type", "band", "passed", "correct", "chosen", "reason_message",
                "shift_time", "min_flops"}


def load(name):
    with open(ROOT / name, encoding="utf-8") as f:
        return json.load(f)


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


problems = []
game, keys, config = load("game_data.json"), load("answer_keys.json"), load("game_config.json")
c = {n: load(f"content/{n}.json") for n in ["onboarding", "rulebook", "tools", "feedback", "shifts", "final"]}
tools = {t["id"] for t in c["tools"]["tools"]}
reasons = c["feedback"]["reasons"]
all_ids = {r["record_id"] for recs in game["levels"].values() for r in recs}

for name, obj in c.items():
    for s in strings(obj):
        for p in re.findall(r"\{(\w+)\}", s):
            if p not in PLACEHOLDERS:
                problems.append(f"{name}: unknown placeholder {{{p}}} in \"{s[:60]}...\"")

for code, r in reasons.items():
    for field in ["label", "stamp", "in_shift", "debrief", "unlock_level"]:
        if field not in r:
            problems.append(f"feedback: reason {code} has no {field}")

for lvl, recs in game["levels"].items():
    shift = c["shifts"]["shifts"].get(lvl)
    if shift is None:
        problems.append(f"shifts: level {lvl} is missing")
        continue
    ids = [r["record_id"] for r in recs]
    lkeys = keys[lvl]
    for rid in ids:
        if not shift["records"].get(rid, {}).get("hint"):
            problems.append(f"shifts {lvl}: {rid} has no hint")
    for rid in shift["records"]:
        if rid not in ids:
            problems.append(f"shifts {lvl}: hint for {rid}, which is not in this level")
    guided = shift.get("guided_record")
    if guided not in ids:
        problems.append(f"shifts {lvl}: guided record {guided} is not in this level")
    elif lkeys[guided]["verdict"] != "allow":
        problems.append(f"shifts {lvl}: guided record {guided} is a violation; the walkthrough would give it away")
    for t in shift["tools_unlocked"] + [s["tool"] for s in shift["guided_steps"]]:
        if t not in tools:
            problems.append(f"shifts {lvl}: unknown tool {t}")
    for t in [s["tool"] for s in shift["guided_steps"]]:
        if t not in shift["tools_unlocked"]:
            problems.append(f"shifts {lvl}: walkthrough uses {t} before it is unlocked")
    for rid, k in lkeys.items():
        if k["verdict"] == "block":
            if k.get("reason") not in reasons:
                problems.append(f"answer_keys {lvl}: {rid} has unknown reason {k.get('reason')}")
            elif k["reason"] not in shift["reasons_unlocked"]:
                problems.append(f"shifts {lvl}: {rid} needs reason {k['reason']}, which is not unlocked yet")
    for r in shift["reasons_unlocked"]:
        if r not in reasons:
            problems.append(f"shifts {lvl}: unknown reason {r}")
        elif reasons[r]["unlock_level"] > int(lvl):
            problems.append(f"shifts {lvl}: reason {r} unlocks at level {reasons[r]['unlock_level']}")
    blocks = sum(k["verdict"] == "block" for k in lkeys.values())
    honest = len(lkeys) - blocks
    if not 0 <= shift["max_slipped"] < blocks:
        problems.append(f"shifts {lvl}: max_slipped {shift['max_slipped']} must be below {blocks} violations")
    if not 0 <= shift["max_complaints"] < honest:
        problems.append(f"shifts {lvl}: max_complaints {shift['max_complaints']} must be below {honest} honest records")
    qs = shift["questions"]
    if len(qs) != 3:
        problems.append(f"shifts {lvl}: {len(qs)} questions, expected 3")
    for q in qs:
        for rid in q.get("refs", []):
            if rid not in all_ids:
                problems.append(f"shifts {lvl}: question {q['id']} refers to unknown record {rid}")
        if q["type"] == "mc" and q["answer"] not in q["options"]:
            problems.append(f"shifts {lvl}: question {q['id']} answer {q['answer']} is not an option")
        if q["type"] == "short" and not (q.get("model_answer") and q.get("key_points")):
            problems.append(f"shifts {lvl}: question {q['id']} needs a model answer and key points")
    print(f"level {lvl}: {len(ids)} records ({blocks} violations, {honest} honest), "
          f"{shift['shift_seconds']}s, pass with <= {shift['max_slipped']} slipped / <= {shift['max_complaints']} complaints")

for r in c["rulebook"]["rules"]:
    if not 1 <= r["level"] <= 4:
        problems.append(f"rulebook: rule {r['id']} has level {r['level']}")

# final challenge, part A: the worst starting state must still allow a training job of min_flops
s = c["final"]["part_a"]["starting_state"]
lo, hi = config["reference_ranges"]["training"]["flops_per_kj"]
room_flops = config["flop_limit"] - s["used_flops"][1]
room_energy = config["energy_limit_kj"] * 0.95 - s["used_energy_kj"][1]
min_energy = s["min_flops"] / (hi * 1.1)
if room_flops < s["min_flops"] or room_energy < min_energy:
    problems.append(f"final: worst-case starting state is unsolvable (FLOP room {room_flops:.3g}, "
                    f"energy room {room_energy:.3f} kJ, needs at least {min_energy:.3f} kJ)")
else:
    print(f"final: worst case leaves {room_flops / 1e12:.2f}e12 FLOPs and {room_energy:.2f} kJ "
          f"(a {s['min_flops'] / 1e12:.1f}e12 job needs >= {min_energy:.2f} kJ)")

if problems:
    print("\nPROBLEMS:\n  " + "\n  ".join(problems))
    sys.exit(1)
print("\nAll content checks passed.")
