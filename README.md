# The Compliance Bouncer

An inspection game about hardware-rooted trust. Students play a compliance officer at a data center. Each AI job
arrives as a report sealed by the chip that ran it, and the student stamps it Allow or Block before the queue backs up.

The lesson every level builds toward: **a valid signature proves where numbers came from and that they weren't
changed. It doesn't prove that unsigned claims are true, or that the meter saw all the work.**

## Levels

| Level | The question | Students learn | Attacks |
| --- | --- | --- | --- |
| 1 | Can I trust where this came from? | Endorsement, integrity | Edited after signing; unregistered chip |
| 2 | Have I seen this before? Who is paying? | Freshness; charging the registered owner | Replayed reports; one run split into small jobs |
| 3 | Is the claim true? | Unsigned claims; limits of measurement | Disguised workload type; work the FLOP meter missed |
| 4 | How sure do I need to be? | Noise and tolerance | Borderline jobs, plus every earlier attack |
| Final | Can I build one, and break one? | All of the above | Students build an honest record, forgeries, and one that slips through |

Each level is a timed shift. Time-outs wave waiting reports through unchecked, so speed and accuracy share one score.
After each shift comes an untimed debrief and three questions.

## Repo layout

| Path | What it is |
| --- | --- |
| `content/` | Everything the player reads: onboarding, Rulebook, tools, feedback, shifts, final challenge. See `content/README.md` |
| `levels.json` | Hand-written records per level. Attacks are marked with `"attack"` |
| `game_config.json` | FLOP and energy caps, and the FLOPs-per-kJ band for each workload type |
| `answer_keys.json` | Correct verdict, reason code and explanation for every record |
| `game_data.json` | Generated: config, chip registry and signed records. The game loads this |
| `instructor.py` | Reference policy. The GUI's game logic must give the same verdicts |
| `rot/` | Simulated hardware root of trust: chips, keys, signing, registry. See `rot/README.md` |
| `preview.py` | Prints the game as a player meets it, and checks every verdict against the answer keys |
| `check_content.py` | Checks `content/` for gaps before handoff |

## Setup

```bash
pip install -r rot/requirements.txt
```

## Preview and check

```bash
python preview.py 1          # a level as the player sees it (onboarding, 1-4, final, or all)
python check_content.py      # missing hints, unknown placeholders, locked reasons and other gaps
```

## Changing levels (instructors)

1. Edit `levels.json`, and give every record an entry in `answer_keys.json` (block entries need a `reason` code).
2. Add a hint for any new record in `content/shifts.json`.
3. Rebuild and check:

```bash
python -m rot.sign_levels    # signs every record and rebuilds game_data.json
python check_content.py
python preview.py all        # fails if any verdict disagrees with answer_keys.json
```

Never commit `ROT_SEED` or ship the level chips' private keys: anyone with them can forge any chip's seal.
