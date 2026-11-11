# Home Assistant Add-on: Comfort to MQTT
Cytech Comfort to MQTT bridge for Home Assistant.

![Supports aarch64 Architecture][aarch64-shield] ![Supports amd64 Architecture][amd64-shield] ![Supports armhf Architecture][armhf-shield] ![Supports armv7 Architecture][armv7-shield] ![Supports i386 Architecture][i386-shield]

[mosquitto]: https://mosquitto.org
[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[armv7-shield]: https://img.shields.io/badge/armv7-yes-green.svg
[i386-shield]: https://img.shields.io/badge/i386-yes-green.svg

For more information about Cytech Comfort systems, please see the [Cytech Technology Pte Ltd.](http://cytech.biz) website.


## About
This Addon is used to bridge a Cytech Comfort II ULTRA Alarm system to MQTT for use in Home Assistant. Other Comfort systems are partially supported.

This is a customised version of the original comfort2mqtt project by 'koochyrat' and the derivative code from 
'Ingo de Jager'. More information about the original source projects is available [here](https://github.com/koochyrat/comfort2) and [here](https://github.com/djagerif/comfort2mqtt)


The following objects are supported:

* Zone Inputs [1-96]
* Zone Outputs [1-96]
* Counters [0-254]
* Flags [1-254]
* Sensors [0-31]
* Responses [1-1024]


⚠️ This Add-on was specifically developed for Home Assistant OS. Home Assistant Container and Core have not been tested and is not supported at present.

Copyright 2026 Cytech Technology Pte Ltd. Licensed under Apache-2.0. For more details see the [LICENSE](LICENSE) file.

## Live alarm status dashboard

The AM alarm status publisher and Home Assistant image YAML are available for testing.
See [HA image integration](home_assistant/README.md) for the MQTT sensor and the button/table within the existing Comfort Alarm dashboard.
# Home Control Menu

Home Control uses a separate MQTT namespace from the alarm. Definitions come
from the active CCLX Home Control Menu; no dashboard automations are required
to translate its actions into Comfort Responses.

For group 2, key 4 (substitute your configured MQTT domain):

| Topic | Payload / purpose |
| --- | --- |
| `<DOMAIN>/home_control/02/04/set` | Action digit `0`–`9`, defined by CCLX |
| `<DOMAIN>/home_control/02/04/query` | Any non-retained payload requests status |
| `<DOMAIN>/home_control/02/04/state` | Retained JSON: `value` and raw status bytes `raw` |
| `<DOMAIN>/meta/home_control` | Retained definitions, labels, actions and feedback references |

Addresses in MQTT topics use two decimal digits. CM wire addresses use two
hexadecimal digits. Action commands must not be retained. Offline actions are
rejected; queued actions are discarded at disconnect or configuration change.

Home Assistant discovers action buttons and feedback sensors under the existing
Comfort device. Numeric identities remain stable when labels change. Feedback
is authoritative: `OK` does not imply that an external device has changed state.
No immediate status query follows an action.

After successful login/reconnect or CCLX reload, status-capable controls are
queried at 100 ms intervals to initialise UCM unsolicited reporting. UCM 7.xxx
or newer is required for ongoing automatic feedback; older firmware is not
continuously polled. Initial sensor state is unknown until feedback arrives.
Sensor feedback uses signed 16-bit, low-byte-first decoding; a missing high byte
defaults to zero. Missing feedback remains unknown. Other feedback retains the
unsigned low-byte value (0–255), without assuming a device type or scaling.

Empty action placeholders and action 10 are excluded. Labelled actions without
a Response reference retain their labels and can be sent as CM action keys.
X10 feedback and directly identified X10 action Responses are excluded. The
bridge does not interpret arbitrary Response programs or recursively classify
their indirect effects.

The CM codec and Home Control service are independent of Home Assistant.
Dashboard designs can consume the MQTT contract without changing serial logic.

The bundled Home Control dashboard now reads this metadata automatically.
Install its JavaScript resource and dashboard once using
[these instructions](home_assistant/HOME_CONTROL_DASHBOARD.md). Subsequent CCLX
changes update the displayed groups, labels and actions without YAML edits.
Discovery includes a Home Control Menu sensor holding the menu definitions and
stable identity attributes on feedback/action entities so the card can resolve
entities even after Home Assistant entity IDs have been renamed.
