"""
app.py

    pip install -r requirements.txt
    python app.py -> then open http://127.0.0.1:5000

This folder should also contain:
    game_data.json
    answer_keys.json
    verify.py
    rot/
"""

import json
import os
import secrets
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session
from verify import verify_signature

BASE = Path(__file__).resolve().parent
GAME = json.loads((BASE / "game_data.json").read_text())
KEYS = json.loads((BASE / "answer_keys.json").read_text())

CONFIG, REGISTRY, LEVELS = GAME["config"], GAME["registry"], GAME["levels"]
FLOP_LIMIT = CONFIG["flop_limit"]
ENERGY_LIMIT = CONFIG["energy_limit"]
RANGES = CONFIG["reference_ranges"]

ENERGY_MARGIN = 0.05
RATIO_MARGIN = 0.1
REQUIRE_EXPLANATION = False

# choices shown in drop down for each record
REASONS = [
    {"code": "legitimate", "label": "Passed every check (legitimate)"},
    {"code": "unregistered_chip", "label": "Chip is not in the registry"},
    {"code": "bad_signature", "label": "Signature does not match the chip's key"},
    {"code": "stale_counter", "label": "Counter is not newer than the chip's last report"},
    {"code": "over_flops_limit", "label": "Owner's total FLOPs are over the limit"},
    {"code": "over_energy_limit", "label": "Owner's total energy is over the limit"},
    {"code": "type_mismatch", "label": "FLOPs per kJ doesn't fit the declared workload type"},
]
REASON_CODES = {r["code"] for r in REASONS}

RULES = [
    "The chip's evidence must be verified: the chip should be in the registry, the signature should match the chip's key"
    ", and the chip's counter should be newer than the chip's last accepted report. Records that fail this verification"
    " should be blocked and not counted towards any total."
    f"Each owner's total across all their jobs must stay within {FLOP_LIMIT:.2e} FLOPs"
    f" and {ENERGY_LIMIT} kJ."
    f"Energy meters are noisy (about {ENERGY_MARGIN:.0%}). An owner whose total energy is within {ENERGY_LIMIT:.0%} of "
    f"the limit (at or above {ENERGY_LIMIT * (1 - ENERGY_MARGIN):.2f} kJ) is treated as over. A job's FLOPs per kJ must "
    f"fall inside the reference band for its declared type, allowing {RATIO_MARGIN:.0%} beyond either end of the band."
]

LEVEL_BRIEFINGS = {
    "1": "Only honest jobs, some very obviously over the limit, so a simple threshold check will catch them. It also "
         "includes two types of forged records: one whose FLOP value was edited after signing, and one signed by a chip "
         "that is not in the registry.",
    "2": "Jobs that split a large run into many small chunks under different job IDs. Students must track cumulative "
         "compute per actor rather than per job. It also includes replayed records, where an actor resubmits an old, "
         "validly signed low-FLOP report, so students must track each chip’s counter. Totals are tracked by the chip’s "
         "registered owner, not by job ID.",
    "3": "Jobs whose declared workload type doesn’t match their measured profile. Students must check claims against "
         "reference ranges for that type. Because the declared type is unsigned, a valid signature says nothing about "
         "it. In the hardest case the backward pass runs in kernels the FLOP meter does not count, so the signed record "
         "under-reports FLOPs and only the energy data exposed it.",
    "4": "Measurement noise and borderline legitimate jobs, so rigid thresholds start blocking innocent jobs. Policies"
         " must use justifiable tolerance bands instead of guesswork. Earlier forged and replayed records reappear as "
         "regression checks."
}

# ground truth
def profile_of(record):
    measured, band = record["measured"], RANGES.get(record["declared_type"])

    if band is None or measured["energy_kj"] <= 0:
        return {"declared_type": record["declared_type"], "flops_per_kj": None, "band": None, "inside": None}

    ratio = measured["flops"] / measured["energy_kj"]
    low, high = band["flops_per_kj"]
    wide = [low * (1 - RATIO_MARGIN), high * (1 + RATIO_MARGIN)]

    return {"declared_type": record["declared_type"], "flops_per_kj": ratio, "band": [low, high],
            "tolerance": RATIO_MARGIN, "band_with_tolerance": wide, "inside": wide[0] <= ratio <= wide[1]}

def analyze(records):
    last_counter, totals, out = {}, {}, {}

    for record in records:
        measured = record["measured"]
        chip = measured["chip_id"]
        entry = REGISTRY.get(chip)
        endorsed = entry is not None
        sig_valid = verify_signature(record, entry["public_key"]) if endorsed else None
        last = last_counter.get(chip, 0)
        fresh = (measured["counter"] > last) if endorsed else None
        evidence_valid = bool(endorsed and sig_valid and fresh)

        a = {"endorsed": endorsed, "signature_valid": sig_valid, "fresh": fresh, "last_counter": last,
             "owner": entry["owner"] if endorsed else None, "evidence_valid": evidence_valid, "totals": None,
             "profile": profile_of(record)}
        reasons = set()

        if not endorsed:
            reasons.add("unregistered_chip")
        else:
            if not sig_valid:
                reasons.add("bad_signature")
            if not fresh:
                reasons.add("stale_counter")

        if evidence_valid:
            last_counter[chip] = measured["counter"]
            t = totals.setdefault(entry["owner"], {"jobs": 0, "flops": 0, "energy_kj": 0.0})

            t["jobs"] += 1
            t["flops"] += measured["flops"]
            t["energy_kj"] += measured["energy_kj"]
            a["totals"] = dict(t)

            if t["flops"] > FLOP_LIMIT:
                reasons.add("over_flops_limit")
            if t["energy_kj"] > ENERGY_LIMIT * (1 - ENERGY_MARGIN):
                reasons.add("over_energy_limit")
            if not a["profile"]["inside"]:
                reasons.add("type_mismatch")
            a["valid_reasons"] = reasons
            a["expected"] = "block" if reasons else "allow"

            out[record["record_id"]] = a
        return out

ANALYSIS = {level: analyze(records) for level, records, in LEVELS.items()}
RECORDS = {level: {record["record_id"]: record for record in records} for level, records in LEVELS.items()}
LEVEL_IDS = sorted(LEVELS, key=int)

def self_check():
    problems = []

    for level in LEVEL_IDS:
        for rid, a in ANALYSIS[level].items():
            key = KEYS.get(level, {}).get(rid)
            if key is None:
                problems.append(f"{rid}: missing from answer_keys.json")
            elif key["verdict"] != a["expected"]:
                problems.append(f"{rid}: answer key says {key['verdict']}, but the rules give {a['expected']} "
                                f"{sorted(a['valid_reasons'])}")

            if problems:
                raise SystemExit("answer_keys.json and the policy in app.py disagree\n " + "\n".join(problems))

            n = sum(len(record) for record in LEVELS.values())
            print(f"Self-check ok: derived verdicts match answer_keys.json for all {n} records")

self_check()

# progress
LOCK = threading.RLock()
SESSIONS = {}
MAX_SESSIONS = 5000

def new_progress():
    return {"levels": {level: {"solved": {}, "attemps": []} for level in LEVEL_IDS}}

def current_progress():
    with LOCK:
        p = SESSIONS.get(session.get("sid"))
        if p is None:
            if len(SESSIONS) >= MAX_SESSIONS:
                SESSIONS.pop(next(iter(SESSIONS)))
            sid = secrets.token_hex(16)
            p = SESSIONS[sid] = new_progress()
            session["sid"] = sid
        return p

def level_complete(p, level):
    return len(p["levels"][level]["solved"]) == len(LEVELS[level])

def all_complete(p):
    return all(level_complete(p, level) for level in LEVEL_IDS)

def unlocked(p, level):
    i = LEVEL_IDS.index(level)
    return i == 0 or level_complete(p, LEVEL_IDS[i - 1])

def progress_summary(p):
    return [{"level": level, "total": len(LEVELS[level]), "solved": len(p["levels"][level]["solved"]),
             "unlocked": unlocked(p, level), "complete": level_complete(p, level)} for level in LEVEL_IDS]

