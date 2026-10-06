# coding=utf-8
"""Decides, from the serial traffic alone, whether the printer is waiting for a human.

Pure logic, no OctoPrint imports, so it can be unit-tested anywhere. The plugin feeds
it received lines and sent commands; it answers with the attention reasons currently
pending. Two kinds of wait are recognised:

* a host prompt: the firmware announces a dialog with ``//action:prompt_begin <title>``
  and takes it down with ``//action:prompt_end`` (Marlin's action-command protocol,
  which Prusa Buddy uses for warnings such as "Heating disabled due to 30 minutes of
  inactivity");
* an extruder stall: Prusa Buddy prints ``E-motor stall detected`` and shows its
  "Reloading filament" screen, which is *not* announced as a prompt and has no end
  marker. The firmware stops acknowledging the stuck move, so OctoPrint sends no new
  movement until the user has reloaded; the first movement sent after the stall line
  (ignoring the one or two that were already in flight) is therefore the recovery.
"""

import re
import time

STALL_RE = re.compile(r"E-motor stall detected")
PROMPT_BEGIN_RE = re.compile(r"//action:prompt_begin\s*(.*)")
PROMPT_END_RE = re.compile(r"//action:prompt_end")
MOVEMENT_GCODES = ("G0", "G1", "G2", "G3")

STALL_REASON = "Filament stuck: E-motor stall detected"

# moves OctoPrint had already sent when the stall line arrived still trickle out for a
# moment; a move this soon after the stall is not a recovery
STALL_SETTLE_SECONDS = 2.0


class Tracker:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._stall_at = None  # monotonic time of the last stall line, while unresolved
        self._prompt = None  # title of the open prompt, while one is open

    # ~~ inputs

    def received(self, line):
        """Feed a line received from the printer. Returns True if the state changed."""
        before = self.reason
        if STALL_RE.search(line):
            self._stall_at = self._clock()
        else:
            m = PROMPT_BEGIN_RE.search(line)
            if m:
                self._prompt = m.group(1).strip() or "Printer dialog"
            elif PROMPT_END_RE.search(line):
                self._prompt = None
        return before != self.reason

    def sent(self, gcode):
        """Feed the gcode of a command sent to the printer. Returns True if the state changed."""
        if self._stall_at is None or gcode not in MOVEMENT_GCODES:
            return False
        if self._clock() - self._stall_at < STALL_SETTLE_SECONDS:
            return False
        self._stall_at = None
        return True  # the reason changed: either gone, or down to a prompt that is still open

    def reset(self):
        """Forget everything (print ended, printer disconnected)."""
        self._stall_at = None
        self._prompt = None

    # ~~ output

    @property
    def reason(self):
        """Why the printer needs a human, or None if it does not.

        A stall outranks a prompt: the "heating disabled" warning that follows an
        unattended stall is a consequence, the stall is what the user has to deal with.
        """
        if self._stall_at is not None:
            return STALL_REASON
        if self._prompt is not None:
            return "Printer dialog: " + self._prompt
        return None

    @property
    def attention(self):
        return self.reason is not None
