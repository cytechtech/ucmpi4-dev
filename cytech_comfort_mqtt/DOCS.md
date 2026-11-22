# Home Assistant Add-on: Cytech Comfort → MQTT Bridge

---

## Overview

This add-on connects a Cytech Comfort II / Comfort II ULTRA alarm system to Home Assistant using MQTT.

It provides:

- Alarm control from Home Assistant, including arming, disarming, and per-zone bypass
- Real-time monitoring of alarm states and devices, including live alarm status
- Control of devices through the configured Comfort Home Control Menu, with feedback where available
- Full integration with Home Assistant via MQTT Discovery
- Automatic creation of entities (no YAML configuration required)

---

## Installation

1. In Home Assistant, go to:
   **Settings → Apps** then click the **Install App** button

2. Click the **⋮ (three dots)** in the top-right corner → **Repositories**

3. Add https://github.com/cytechtech/ucmpi4

4. Install:
   **Cytech Comfort MQTT Bridge**

5. Configure the add-on (see below)

6. Start the add-on

---

## Home Assistant Integration

### Automatic Entity Creation (MQTT Discovery)

This add-on uses MQTT Discovery.

➡️ **No manual YAML configuration is required**

Once running:

- Entities are automatically created
- Devices appear under:

Comfort

---

### Available Entities

The following are automatically created:

- Alarm Control Panel
- Zone Inputs (binary sensors)
- Outputs and Flags (switches)
- Counters, Sensors, Timers (number entities)
- Battery & Power sensors
- Per-zone bypass buttons and status sensors
- Home Control action buttons and feedback sensors from the active CCLX

---

## Comfort Configuration File (CCLX)

To enable meaningful names (zones, outputs, etc.):

1. Open the add-on Web UI (Ingress panel)
2. Upload your `.cclx` file
3. Click **Validate**
4. Click **Apply**

The add-on will reload and update all entities.


---

## Battery & Power Monitoring

The add-on provides:

- Battery voltage
- DC supply voltage

---

## Alarm Control

The alarm panel integrates directly with Home Assistant.

Supported modes:

- Arm Home
- Arm Away
- Arm Night
- Disarm

### Custom Bypass (`#` Key)

Comfort requires the `#` key to confirm/bypass zones.


Home Assistant does not include a `#` key.

Example button:
```yaml
type: custom:button-card
name: Comfort # Key
icon: mdi:pound
tap_action:
  action: call-service
  service: alarm_control_panel.alarm_arm_custom_bypass
  target:
```
---

## Alarm MQTT

In the alarm and Home Control topic tables, replace `<DOMAIN>` with the bridge
topic prefix, which is `cytech_comfort_mqtt` by default.

| Topic | Payload or purpose |
| --- | --- |
| `<DOMAIN>/alarm` | State used by the Home Assistant alarm panel, including armed modes and transitions such as `arming` and `triggered` |
| `<DOMAIN>/alarm/mode` | Retained Comfort security mode. `0` is off, `1` is away, `2` is night, `3` is day (Home), and `4` is vacation. |
| `<DOMAIN>/alarm/status` | Retained alarm condition such as `Idle`, `Trouble`, `Alert`, or `Alarm` |
| `<DOMAIN>/alarm/set` | Alarm panel commands. Use the Home Assistant alarm panel for PIN entry when disarming. Publish commands without the retain flag. |
| `<DOMAIN>/alarm/online` | Bridge availability (`1` or `0`) |
| `<DOMAIN>/alarm/connected` | Whether the bridge is connected to Comfort (`1` or `0`) |
| `<DOMAIN>/alarm/am_status` | Live alarm status JSON published on events and at five-second heartbeat intervals, without retention |
| `<DOMAIN>/zone/1/bypass/set` | Per-zone bypass command, `SET` or `CLEAR`. Publish without the retain flag. |
| `<DOMAIN>/zone/1/bypass/state` | Retained status reported by Comfort, `Bypassed` or `Not bypassed` |

Use the decimal zone number in place of `1` for other zones. The bridge
discovers separate Set Bypass and Clear Bypass buttons and a status sensor for
each configured zone.

## Home Control MQTT

The Home Control Menu uses `<DOMAIN>/home_control/` for commands and feedback.
The bridge reads the active CCLX Home Control Menu and sends the selected
action to Comfort. The menu actions defined in CCLX run without dashboard
automations.

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


---

## Support

- Comfort Forums: https://comfortforums.com/

---

## Credits

Based on original projects:

- https://github.com/koochyrat/comfort2
- https://github.com/djagerif/comfort2mqtt

---

## License

Apache 2.0  
https://www.apache.org/licenses/LICENSE-2.0
