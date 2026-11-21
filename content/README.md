# Game content

Everything the player reads lives in this folder, so wording can change without touching game code. The GUI loads
these files alongside `game_data.json` (the signed records) and `answer_keys.json` (verdicts and reason codes).

| File | What it holds |
| --- | --- |
| `onboarding.json` | The opening screens: the officer's job, the anatomy of a record, the three trust checks, the shift rules |
| `rulebook.json` | Glossary terms and rules. Each has a `level`: show it from that level on |
| `tools.json` | Each inspection tool: name, what it shows, what it cannot tell you (use as the tooltip), unlock level, walkthrough text |
| `feedback.json` | Per reason code: the option label, the stamp text, the two-second in-shift note and the debrief message. Plus messages for complaints, false blocks, wrong reasons and waved-through records |
| `shifts.json` | Per level: briefing, shift time and pass limits, unlocked tools and reasons, the guided first record and its walkthrough steps, a hint per record, and the three debrief questions with answers |
| `final.json` | The Forge & Certify challenge: workbench chips, prompts, starting-state ranges and rubrics |

## Placeholders

Text in curly braces is filled by the game from the record being shown, for example
`"Charged to {owner}, this brings the period total to {total_flops} FLOPs"`. The allowed names are listed in
`check_content.py`. `python preview.py` shows how each one is filled.

| Placeholder | Value |
| --- | --- |
| `{owner}`, `{chip}` | The chip's registered owner, and the chip ID |
| `{counter}`, `{last_counter}` | This report's counter, and the last counter accepted from this chip |
| `{total_flops}`, `{total_energy}` | The owner's period totals after this report |
| `{flop_limit}`, `{energy_limit}`, `{energy_margin_limit}` | From `game_config.json`; the margin limit is the energy cap minus 5% |
| `{ratio}`, `{type}`, `{band}` | This report's FLOPs per kJ, its declared type, and that type's band with 10% tolerance |
| `{passed}` | The checks this report passed |
| `{correct}`, `{chosen}` | Reason labels, for the wrong-reason message |
| `{reason_message}` | The debrief message for the record's reason |
| `{shift_time}`, `{min_flops}` | Shift length (m:ss), and the final challenge's minimum job size |

## After editing

```bash
python check_content.py   # catches missing hints, unknown placeholders, locked reasons and other gaps
python preview.py 1       # read a level as the player sees it (onboarding, 1-4, final, or all)
```
