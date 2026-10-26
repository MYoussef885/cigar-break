# Demo: the auto break in 30 seconds

The GIF at the top of the README. It shows the most striking part of Cigar: the session notices it is slipping, the agent writes its own handoff, the context clears by itself, and the agent carries on. Terminal only (auto mode is verified there, D-026).

## Setup (2 minutes, not recorded)

1. A scratch repo with a little real work to do:
   ```
   mkdir -p ~/cigar-demo && cd ~/cigar-demo && git init -q
   printf 'def add(a, b):\n    return a - b\n' > calc.py
   ```
2. A terminal at about 110 × 32 characters with a large, readable font (iTerm2 or Ghostty make the 🚬 notifications look best).
3. Start Claude Code with low test thresholds so the break comes within a minute:
   ```
   CIGAR_KNEE_TOKENS=20000 CIGAR_MIN_TOKENS=5000 claude
   ```
4. Type `/cigar:mode auto` before recording (it prints one line; you can also leave it in the recording as the opt-in moment).

## The 30 seconds

| Time | On screen | You do |
|---|---|---|
| 0–4 s | The prompt, with `/cigar:mode auto` already confirmed | Type: *Fix the bug in calc.py, add test_calc.py with plain asserts and run it, then add mul and div with tests.* |
| 4–15 s | Claude reads, edits and runs tests. Then the line **🚬 Cigar: this session shows fatigue (… tokens, … signals in the last 20 calls)** | Nothing. Let it work. |
| 15–20 s | Claude calls `take_break` on its own; *Handoff saved to .cigar/handoffs/….md* | Nothing. |
| 20–24 s | The turn ends, the screen clears by itself, then **🚬 Cigar auto mode cleared the context and restored the handoff from .cigar/handoffs/….md** | Nothing. This is the moment. |
| 24–30 s | | Type: *what's next?* Claude answers with the goal and the next step from the handoff. Stop recording once the first line of the answer appears. |

If Claude doesn't call `take_break` by itself after the nudge, auto mode never clears (by design); type `/cigar:break` and it continues from step 15 s. Keep that take for a "you can always force it" cut.

## Recording

- macOS: Cmd-Shift-5, "Record Selected Portion", around the terminal window. Then convert to a GIF under 8 MB, for example `ffmpeg -i demo.mov -vf "fps=12,scale=1100:-1:flags=lanczos" -loop 0 docs/demo.gif` (or `gifski --fps 12 --width 1100 -o docs/demo.gif demo.mov`).
- Speed up the "Claude works" stretch to 2× if the run is longer than 30 seconds; keep the clear-and-restore part at normal speed.
- Save it as `docs/demo.gif`; the README already points there.

## Afterwards

`/cigar:mode suggest` returns to the default. The demo's data lives in `~/.cigar/` and `~/cigar-demo/.cigar/`; delete the scratch repo when done.
