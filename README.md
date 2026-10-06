# OctoPrint-Attention-State

Makes OctoPrint say when the printer is standing at its LCD waiting for you.

Prusa Buddy printers (CORE One, MK4, XL, MINI) handle a stuck extruder, a heater
timeout or any other "press OK" moment on their own screen. Over the serial link they
only print a line about it; OctoPrint keeps reporting **Printing**, the file position
simply stops moving, and anything watching OctoPrint's API, Home Assistant's OctoPrint
integration for example, cannot tell a print that needs you from one that is fine.

This plugin watches the serial traffic and, while the printer is waiting for a human,
reports OctoPrint's state as **Error** with the reason:

* `Filament stuck: E-motor stall detected` – the firmware's extruder stall screen
  ("Reloading filament – manually remove the filament from the extruder");
* `Printer dialog: <title>` – any dialog the firmware announces as a host prompt, such as
  "Heating disabled due to 30 minutes of inactivity".

Nothing is paused and nothing is sent to the printer. OctoPrint keeps streaming the
moment the firmware starts accepting commands again, and the state goes back to
**Printing** by itself: when the dialog is closed, or, for a stall, when the first
movement command after it goes out (the firmware does not acknowledge the stuck move
until the filament has been reloaded, so no movement is sent before then).

## Why "Error"

OctoPrint's state is a fixed set of strings and Home Assistant's integration maps them
to a closed enum; `Error` is the only one that is not a normal step of a print, and the
only one Home Assistant exposes that fits. The reason goes into the state's error
string, which OctoPrint's UI shows behind the red (!) next to the state. Home Assistant
ignores that string, but gets a clean `error` value to trigger on.

## Home Assistant

With the OctoPrint integration set up, an automation such as

```yaml
triggers:
  - trigger: state
    entity_id: sensor.<printer>_current_state
    to: error
conditions:
  - condition: state
    entity_id: binary_sensor.<printer>_printing
    state: "on"
actions:
  - action: notify.mobile_app_<phone>
    data:
      message: The printer is waiting for you.
```

fires when the printer needs you and nothing else. A real serial error also produces
`error`, but then `binary_sensor.<printer>_printing` goes off, which the condition
rules out. The integration polls OctoPrint every 30 s, so expect up to that much delay.

## Install

Plugin Manager → Get More → *…from URL*:

```
https://github.com/BackSlasher/OctoPrint-Attention-State/archive/main.zip
```

## Events

For other plugins: `plugin_attention_state_begin` (payload `reason`) and
`plugin_attention_state_end`.

## Caveat

The override uses OctoPrint's internal state monitor, not a public plugin API. It has
been stable for years; if an OctoPrint release changes it, the plugin logs an error at
startup and does nothing else. Tested on OctoPrint 1.11 with a Prusa CORE One + INDX on
firmware 6.9.1.

## License

AGPLv3.
