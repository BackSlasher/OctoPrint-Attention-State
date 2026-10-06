import importlib.util
import os
import unittest

HERE = os.path.dirname(__file__)
spec = importlib.util.spec_from_file_location(
    "tracker", os.path.join(HERE, "..", "octoprint_attention_state", "tracker.py")
)
tracker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tracker)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class TrackerTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.t = tracker.Tracker(clock=self.clock)

    def test_quiet_printing_is_not_attention(self):
        for line in ("ok", "T:240.03/240.00 B:85.22/85.00", "echo:busy: processing", "X:150.71 Y:160.23 Z:23.20"):
            self.assertFalse(self.t.received(line))
        self.assertFalse(self.t.attention)
        self.assertFalse(self.t.sent("G1"))

    def test_stall_begins_and_the_first_later_move_ends(self):
        # verbatim from a Prusa CORE One INDX serial log
        self.assertTrue(self.t.received("E-motor stall detected"))
        self.assertEqual(self.t.reason, tracker.STALL_REASON)
        # the move OctoPrint had already queued goes out 9 ms later: not a recovery
        self.clock.now += 0.009
        self.assertFalse(self.t.sent("G1"))
        self.assertTrue(self.t.attention)
        # temperature polling during the wait changes nothing
        self.clock.now += 600
        self.assertFalse(self.t.sent("M105"))
        self.assertTrue(self.t.attention)
        # user reloaded, OctoPrint resumes streaming
        self.assertTrue(self.t.sent("G1"))
        self.assertFalse(self.t.attention)

    def test_prompt_begins_and_prompt_end_ends(self):
        self.assertTrue(self.t.received("//action:prompt_begin Warning: Heating disabled due to 30 minutes of inactivity."))
        self.assertFalse(self.t.received("//action:prompt_button OK"))
        self.assertFalse(self.t.received("//action:prompt_show"))
        self.assertEqual(self.t.reason, "Printer dialog: Warning: Heating disabled due to 30 minutes of inactivity.")
        self.assertTrue(self.t.received("//action:prompt_end"))
        self.assertFalse(self.t.attention)

    def test_untitled_prompt_gets_a_generic_reason(self):
        self.t.received("//action:prompt_begin")
        self.assertEqual(self.t.reason, "Printer dialog: Printer dialog")

    def test_stall_outranks_the_heater_timeout_that_follows_it(self):
        self.t.received("E-motor stall detected")
        self.clock.now += 1800
        self.assertFalse(self.t.received("//action:prompt_begin Warning: Heating disabled due to 30 minutes of inactivity."))
        self.assertEqual(self.t.reason, tracker.STALL_REASON)
        # the user dismisses the warning first: still waiting on the reload
        self.assertFalse(self.t.received("//action:prompt_end"))
        self.assertTrue(self.t.attention)
        self.assertTrue(self.t.sent("G1"))
        self.assertFalse(self.t.attention)

    def test_prompt_still_open_after_stall_recovery_keeps_attention(self):
        self.t.received("E-motor stall detected")
        self.clock.now += 1800
        self.t.received("//action:prompt_begin Warning: Heating disabled due to 30 minutes of inactivity.")
        self.assertTrue(self.t.sent("G0"))
        self.assertEqual(self.t.reason, "Printer dialog: Warning: Heating disabled due to 30 minutes of inactivity.")

    def test_reset_forgets_everything(self):
        self.t.received("E-motor stall detected")
        self.t.received("//action:prompt_begin x")
        self.t.reset()
        self.assertFalse(self.t.attention)


if __name__ == "__main__":
    unittest.main()
