---
name: buddy
description: Hatch a coding companion that lives in your terminal.
argument-hint: "pet / feed / play / teach <stat> / off / on / rehatch"
---
Hatch a coding companion that lives in your terminal.

Run `python3 ${CLAUDE_SKILL_DIR}/buddy.py -q` with the appropriate subcommand based on the user's input. The `-q` flag suppresses stdout and writes output to `${CLAUDE_SKILL_DIR}/.buddy_display.txt` instead.

| User says | Command |
|-----------|---------|
| `/buddy` | `python3 ${CLAUDE_SKILL_DIR}/buddy.py -q` |
| `/buddy pet` | `python3 ${CLAUDE_SKILL_DIR}/buddy.py -q pet` |
| `/buddy feed` | `python3 ${CLAUDE_SKILL_DIR}/buddy.py -q feed` |
| `/buddy play` | `python3 ${CLAUDE_SKILL_DIR}/buddy.py -q play` |
| `/buddy teach <stat>` | `python3 ${CLAUDE_SKILL_DIR}/buddy.py -q teach <stat>` |
| `/buddy off` | `python3 ${CLAUDE_SKILL_DIR}/buddy.py -q off` |
| `/buddy on` | `python3 ${CLAUDE_SKILL_DIR}/buddy.py -q on` |
| `/buddy rehatch` | `python3 ${CLAUDE_SKILL_DIR}/buddy.py -q rehatch` |
| `/buddy weather` | `python3 ${CLAUDE_SKILL_DIR}/buddy.py -q weather` |
| `/buddy weather on` | `python3 ${CLAUDE_SKILL_DIR}/buddy.py -q weather on` |
| `/buddy weather off` | `python3 ${CLAUDE_SKILL_DIR}/buddy.py -q weather off` |

Where `<stat>` is one of: curiosity, patience, snark, charm, focus, chaos.

After running the command, read `${CLAUDE_SKILL_DIR}/.buddy_display.txt` and display its contents exactly as-is inside a code block to preserve the ASCII art formatting. Do not add commentary unless the user asks a question about their buddy.

If the buddy exists and is not muted, occasionally (not every time) run `python3 ${CLAUDE_SKILL_DIR}/buddy.py react <context>` at the end of your responses where `<context>` is a few keywords about what just happened (e.g., "fix bug", "merge PR", "error in tests", "refactoring code"). This gives the buddy a chance to react. Show the reaction inline at the end of your response, not in a code block.

## Live viewer

For a full-color, animated buddy card, run the Textual live viewer in a separate terminal pane:

```
python3 ${CLAUDE_SKILL_DIR}/buddy_watch.py
```

The viewer watches `.buddy_state.json` for changes and live-updates with animation frames, colored stat bars, rarity-styled borders, and a scrolling reaction log. Press `q` to quit. Requires `pip3 install textual watchdog`.
