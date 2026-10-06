# coding=utf-8
from __future__ import absolute_import

import threading

import octoprint.plugin
from octoprint.events import Events

from .tracker import Tracker

# OctoPrint states during which a dialog on the printer means the *print* needs a human
ACTIVE_STATES = ("STARTING", "PRINTING", "PAUSING", "PAUSED", "RESUMING", "FINISHING")

# The one state text OctoPrint reports that means "not a normal step of a print" and that
# Home Assistant's OctoPrint integration maps to a value of its own (`error`). The reason
# goes into the state's error string, which OctoPrint's UI shows behind the red (!) next
# to the state and Home Assistant ignores.
ATTENTION_TEXT = "Error"


class AttentionStatePlugin(
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.EventHandlerPlugin,
):
    def __init__(self):
        self._tracker = Tracker()
        self._lock = threading.Lock()
        self._overridden = False

    # ~~ StartupPlugin

    def on_after_startup(self):
        if self._state_monitor() is None:
            self._logger.error(
                "This OctoPrint has no printer._stateMonitor; the plugin can only log, "
                "it cannot change the reported state. Please report your OctoPrint version."
            )
        else:
            self._logger.info("Attention State ready: stall screens and prompts will be reported as state %r", ATTENTION_TEXT)

    # ~~ EventHandlerPlugin

    def on_event(self, event, payload):
        # OctoPrint has just rewritten the state itself (print done, cancelled, failed,
        # disconnected, ...): whatever we were reporting is stale.
        if event in (Events.PRINTER_STATE_CHANGED, Events.DISCONNECTED):
            with self._lock:
                self._tracker.reset()
                self._overridden = False

    # ~~ hooks

    def on_gcode_received(self, comm_instance, line, *args, **kwargs):
        if line and self._print_active():
            with self._lock:
                if self._tracker.received(line):
                    self._logger.info("attention: %s  (line: %s)", self._tracker.reason, line.strip())
                    self._apply()
        return line

    def on_gcode_sent(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
        if gcode and self._tracker.attention:
            with self._lock:
                if self._tracker.sent(gcode):
                    self._logger.info("attention cleared by %s: %s", gcode, self._tracker.reason or "printer is moving again")
                    self._apply()

    # ~~ the override

    def _apply(self):
        """Make the reported state match the tracker. Called with the lock held."""
        monitor = self._state_monitor()
        if monitor is None:
            return
        current = self._printer.get_current_data().get("state") or {}
        flags = current.get("flags") or {}
        reason = self._tracker.reason
        if reason is not None:
            monitor.set_state(dict(text=ATTENTION_TEXT, flags=flags, error=reason))
            self._overridden = True
            self._event("begin", reason)
        elif self._overridden:
            # back to what OctoPrint itself would say right now
            monitor.set_state(
                dict(text=self._printer.get_state_string(), flags=flags, error=self._comm_error())
            )
            self._overridden = False
            self._event("end", None)

    def _state_monitor(self):
        return getattr(self._printer, "_stateMonitor", None)

    def _comm_error(self):
        comm = getattr(self._printer, "_comm", None)
        try:
            return comm.getErrorString() if comm is not None else ""
        except Exception:
            return ""

    def _print_active(self):
        try:
            return self._printer.get_state_id() in ACTIVE_STATES
        except Exception:
            return False

    def _event(self, which, reason):
        try:
            self._event_bus.fire("plugin_attention_state_" + which, dict(reason=reason))
        except Exception:
            self._logger.exception("could not fire event")

    # ~~ software update

    def get_update_information(self):
        return dict(
            attention_state=dict(
                displayName="Attention State",
                displayVersion=self._plugin_version,
                type="github_release",
                user="BackSlasher",
                repo="OctoPrint-Attention-State",
                current=self._plugin_version,
                pip="https://github.com/BackSlasher/OctoPrint-Attention-State/archive/{target_version}.zip",
            )
        )


def register_custom_events(*args, **kwargs):
    return ["begin", "end"]


__plugin_name__ = "Attention State"
__plugin_pythoncompat__ = ">=3.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = AttentionStatePlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.comm.protocol.gcode.received": __plugin_implementation__.on_gcode_received,
        "octoprint.comm.protocol.gcode.sent": __plugin_implementation__.on_gcode_sent,
        "octoprint.events.register_custom_events": register_custom_events,
    }
