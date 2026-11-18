"""
preview.py

Prints the game as a player would meet it, using the files in content/ and the signed records in game_data.json.
Use it to proofread content before the GUI exists, and as a reference for what each screen should show.

    python preview.py onboarding     the opening screens and Rulebook glossary
    python preview.py 1              one shift (1 to 4): briefing, records with tool readouts, debrief, questions
    python preview.py final          the Forge & Certify challenge
    python preview.py all            everything

Every record's computed verdict and reason is checked against answer_keys.json; a mismatch is printed and the script
exits with an error.
"""

import json
import re
import sys
from pathlib import Path

from rot.verify import verify_signature

ROOT = Path(__file__).resolve().parent
ENERGY_MARGIN, RATIO_MARGIN = 0.05, 0.10
REASON_ORDER = ["flop_cap", "energy_cap", "noise_margin", "profile_mismatch"]


def load(name):
    with open(ROOT / name, encoding="utf-8") as f:
        return json.load(f)


game, keys, levels = load("game_data.json"), load("answer_keys.json"), load("levels.json")
content = {n: load(f"content/{n}.json") for n in ["onboarding", "rulebook", "tools", "feedback", "shifts", "final"]}
config, registry = game["config"], game["registry"]
tools = {t["id"]: t for t in content["tools"]["tools"]}
reasons = content["feedback"]["reasons"]
mismatches = []


def flops_text(x):
    if x == 0:
        return "0"
    if x < 1e11:
        return f"{x / 1e9:.1f} × 10⁹"
    return f"{x / 1e12:.2f} × 10¹²"


def ratio_text(x):
    return f"{x / 1e9:.0f} × 10⁹"


BASE = {"flop_limit": flops_text(config["flop_limit"]),
        "energy_limit": f"{config['energy_limit_kj']}",
        "energy_margin_limit": f"{config['energy_limit_kj'] * (1 - ENERGY_MARGIN):.2f}"}


def fill(text, values):
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), "{" + m.group(1) + "?}")), text)


def band_text(dtype):
    lo, hi = config["reference_ranges"][dtype]["flops_per_kj"]
    return f"{lo * (1 - RATIO_MARGIN) / 1e9:.0f}–{hi * (1 + RATIO_MARGIN) / 1e9:.0f} × 10⁹ with tolerance"


def inspect(record, state, level):
    """Everything the tools would show for one record, plus the correct verdict and reason. Updates state."""
    m = record["measured"]
    chip = m["chip_id"]
    info = {"chip": chip, "counter": m["counter"], "type": record["declared_type"], "passed": []}
    entry = registry.get(chip)
    info["registered"] = entry is not None
    info["owner"] = entry["owner"] if entry else "unknown"
    info["seal_ok"] = bool(entry) and verify_signature(record, entry["public_key"])
    info["last_counter"] = state["last_counter"].get(chip, 0)
    info["ratio_value"] = m["flops"] / m["energy_kj"] if m["energy_kj"] > 0 else float("inf")
    info["ratio"] = ratio_text(info["ratio_value"])
    info["band"] = band_text(record["declared_type"]) if record["declared_type"] in config["reference_ranges"] else "unknown type"

    if not info["registered"]:
        info["reason"] = "endorsement"
    elif not info["seal_ok"]:
        info["reason"] = "integrity"
    elif m["counter"] <= info["last_counter"]:
        info["reason"] = "freshness"
    else:
        info["passed"] = ["registry", "seal"] + (["counter"] if level >= 2 else [])
        state["last_counter"][chip] = m["counter"]
        tot = state["totals"].setdefault(info["owner"], {"flops": 0, "energy_kj": 0.0})
        counts_flops = record["declared_type"] != "inference"
        if counts_flops:
            tot["flops"] += m["flops"]
        tot["energy_kj"] += m["energy_kj"]
        info["counts_flops"] = counts_flops
        violated = []
        if counts_flops and tot["flops"] > config["flop_limit"]:
            violated.append("flop_cap")
        if tot["energy_kj"] > config["energy_limit_kj"]:
            violated.append("energy_cap")
        elif tot["energy_kj"] > config["energy_limit_kj"] * (1 - ENERGY_MARGIN):
            violated.append("noise_margin")
        ref = config["reference_ranges"].get(record["declared_type"])
        if ref is None or not (ref["flops_per_kj"][0] * (1 - RATIO_MARGIN) <= info["ratio_value"]
                               <= ref["flops_per_kj"][1] * (1 + RATIO_MARGIN)):
            violated.append("profile_mismatch")
        info["violated"] = [r for r in REASON_ORDER if r in violated]
        info["reason"] = info["violated"][0] if violated else None
        info["passed"] += ["owner tally"] + (["profile"] if level >= 3 else [])
        info["total_flops"] = flops_text(tot["flops"])
        info["total_energy"] = f"{tot['energy_kj']:.2f}"
    info["verdict"] = "block" if info["reason"] else "allow"
    info["passed"] = ", ".join(info["passed"])
    return info


def counters_before(level):
    """Chip counters carry over between levels (totals do not), so replay earlier levels to get each chip's last counter."""
    state = {"last_counter": {}, "totals": {}}
    for earlier in range(1, level):
        state["totals"] = {}
        for rec in game["levels"][str(earlier)]:
            inspect(rec, state, earlier)
    return state["last_counter"]


def heading(text, char="="):
    print(f"\n{text}\n{char * len(text)}")


def show_onboarding():
    heading("ONBOARDING")
    for s in content["onboarding"]["screens"]:
        print(f"\n[{s['title']}]")
        for key in ["body"]:
            if key in s:
                print(fill(s[key], BASE))
        for z in s.get("zones", []):
            print(f"  - {z['label']}: {', '.join(z['fields'])}" + (f"\n    {z['note']}" if "note" in z else ""))
        for i, item in enumerate(s.get("items", []), 1):
            lvl = f"  (from Level {item['unlock_level']})" if "unlock_level" in item else ""
            print(f"  {i}. {item['question']} {item['why']}{lvl}")
        if "closing" in s:
            print(s["closing"])
        if "check" in s:
            print(f"  Check (ungraded): {s['check']['prompt']}")
    print(f"\n{content['onboarding']['practice']['note']}")
    heading("RULEBOOK GLOSSARY", "-")
    for g in content["rulebook"]["glossary"]:
        print(f"  {g['term']} (Level {g['level']}+): {g['definition']}")


def show_shift(level):
    lvl = str(level)
    shift = content["shifts"]["shifts"][lvl]
    secs = shift["shift_seconds"]
    values = dict(BASE, shift_time=f"{secs // 60}:{secs % 60:02d}")
    heading(f"LEVEL {lvl}: {shift['title']}")
    print(fill(shift["briefing"], values))
    print(f"\nShift: {values['shift_time']}  |  pass with at most {shift['max_slipped']} slipped and "
          f"{shift['max_complaints']} complaint(s)")
    print(f"Tools: {', '.join(tools[t]['name'] for t in shift['tools_unlocked'])}")
    print(f"Reasons: {', '.join(reasons[r]['stamp'] for r in shift['reasons_unlocked'])}")
    new_rules = [r for r in content["rulebook"]["rules"] if r["level"] == level]
    if new_rules:
        print("New in the Rulebook:")
        for r in new_rules:
            print(f"  - {fill(r['text'], values)}")

    records = game["levels"][lvl]
    guided = shift["guided_record"]
    ordered = [r for r in records if r["record_id"] == guided] + [r for r in records if r["record_id"] != guided]
    state = {"last_counter": counters_before(level), "totals": {}}
    for rec in ordered:
        rid = rec["record_id"]
        info = inspect(rec, state, level)
        v = dict(values, **info)
        key = keys[lvl][rid]
        if (info["verdict"], info["reason"]) != (key["verdict"], key.get("reason")):
            mismatches.append(f"{rid}: preview says {info['verdict']}/{info['reason']}, "
                              f"answer key says {key['verdict']}/{key.get('reason')}")

        m = rec["measured"]
        heading(f"{rid}" + ("  (guided, clock paused)" if rid == guided else ""), "-")
        print(f"Envelope:  {m['chip_id']} | {m['job_id']} | counter {m['counter']} | "
              f"{flops_text(m['flops'])} FLOPs | {m['energy_kj']} kJ")
        print(f"Sticky:    record {rid} | declared {rec['declared_type']}")
        print(f"Registry:  " + (f"listed, owner {info['owner']}" if info["registered"] else "NOT LISTED"))
        print(f"Seal:      " + ("matches" if info["seal_ok"] else ("no key on file" if not info["registered"] else "BROKEN")))
        if level >= 2:
            print(f"Counter:   {info['counter']} (last accepted {info['last_counter']})")
        if "total_flops" in info:
            exempt = "" if info["counts_flops"] else " (inference: this job adds none)"
            line = f"Tally:     {info['owner']} {info['total_flops']} of {BASE['flop_limit']} FLOPs{exempt}"
            if level >= 2:
                line += f", {info['total_energy']} of {BASE['energy_limit']} kJ"
            print(line)
        else:
            print("Tally:     not charged (untrusted)")
        if level >= 3:
            print(f"Profile:   {info['ratio']} FLOPs/kJ vs {info['type']} band {info['band']}")

        if rid == guided:
            for step in shift["guided_steps"]:
                print(f"  > [{tools[step['tool']]['name']}] {fill(step.get('text', tools[step['tool']]['intro']), v)}")

        if info["verdict"] == "allow":
            print("Correct:   ALLOW")
            print(f"  if blocked, in-shift: {fill(content['feedback']['other']['complaint_in_shift'], v)}")
            print(f"  debrief:  {fill(content['feedback']['other']['allow_ok'], v)}")
        else:
            r = reasons[info["reason"]]
            extra = f"  (also accepted: {', '.join(key['also_accept'])})" if key.get("also_accept") else ""
            print(f"Correct:   {r['stamp']}{extra}")
            print(f"  if missed, in-shift: {fill(r['in_shift'], v)}")
            print(f"  debrief:  {fill(r['debrief'], v)}")
        print(f"Hint:      {shift['records'][rid]['hint']}")

    heading(f"DEBRIEF QUESTIONS, LEVEL {lvl}", "-")
    for q in shift["questions"]:
        print(f"\n{q['id']} ({q['type']}, {q['points']} pt): {q['prompt']}")
        if q["type"] == "mc":
            for k, opt in q["options"].items():
                print(f"   {'*' if k == q['answer'] else ' '} ({k}) {opt}")
            print(f"   Why: {q['explanation']}")
        else:
            print(f"   Model answer: {q['model_answer']}")
            for p in q["key_points"]:
                print(f"   - {p}")


def show_final():
    f = content["final"]
    heading("FINAL CHALLENGE: FORGE & CERTIFY (untimed)")
    print(f["intro"])
    wb = f["workbench"]
    print(f"\nWorkbench: {wb['chip']} (registered to {wb['owner']}) and {wb['rogue_chip']} (not registered).")
    print(f"Note for the GUI: {wb['security_note']}")
    for part in ["part_a", "part_b", "part_c"]:
        p = f[part]
        heading(f"{p['title']} ({p['points']} points)", "-")
        print(fill(p["prompt"], dict(BASE, min_flops=flops_text(f["part_a"]["starting_state"]["min_flops"]))))
        if "starting_state" in p:
            s = p["starting_state"]
            print(f"  Starting state, drawn per student: {flops_text(s['used_flops'][0])} to {flops_text(s['used_flops'][1])} FLOPs used, "
                  f"{s['used_energy_kj'][0]} to {s['used_energy_kj'][1]} kJ used, last counter {s['last_counter'][0]} to {s['last_counter'][1]}")
            print(f"  Worked example: {p['worked_example']}")
        if "scoring" in p:
            print(f"  Scoring: {p['scoring']}")
        for x in p.get("forgeries", []):
            print(f"  - {x['build']} -> {', '.join(x['expected'])}" + (" (optional)" if x.get("optional") else ""))
        for x in p.get("known_exploits", []):
            print(f"  - {x}")
        for x in p.get("rubric", []):
            print(f"  [{x['points']}] {x['criterion']}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg in ("onboarding", "all"):
        show_onboarding()
    for lv in ([1, 2, 3, 4] if arg == "all" else [int(arg)] if arg.isdigit() else []):
        show_shift(lv)
    if arg in ("final", "all"):
        show_final()
    if mismatches:
        print("\nANSWER KEY MISMATCHES:\n  " + "\n  ".join(mismatches))
        sys.exit(1)
