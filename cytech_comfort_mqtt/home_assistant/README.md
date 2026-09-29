# Comfort Alarm: HA image integration

These YAML files are for the **Home Assistant image's `/config` directory**. They are not add-on options and are not installed automatically by the add-on Dockerfile.

The button appears below **Comfort Message** on the existing **Comfort Alarm** dashboard. It opens an automatically updated table as a subview at `/comfort-alarm/am-status`; the back arrow returns to `/comfort-alarm/0`. It does not register another sidebar dashboard.

## Image files

Copy these repository files into the image:

| Repository file | Image destination |
| --- | --- |
| `packages/comfort_am_status.yaml` | `/config/packages/comfort_am_status.yaml` |
| `dashboards/includes/alarm_status_button.yaml` | `/config/dashboards/includes/alarm_status_button.yaml` |
| `dashboards/includes/alarm_status_view.yaml` | `/config/dashboards/includes/alarm_status_view.yaml` |

### configuration.yaml

The image must load packages. If its existing `homeassistant` section already has this entry, keep it; otherwise merge it into that section:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Keep the existing `comfort-alarm` YAML dashboard registration pointing to `dashboards/alarm.yaml`. Do not add a new dashboard registration or duplicate the top-level `homeassistant` / `mqtt` keys.

If the image does not use packages, merge the sensor entry from `packages/comfort_am_status.yaml` into the existing `mqtt.sensor` list instead. Use one installation method, not both.

### dashboards/alarm.yaml

Immediately after the existing **Comfort Message** card, add the button include at the **same list indentation** as that card. For the image layout discussed here:

```yaml
    - type: markdown
      title: Comfort Message
      content: "{{ states('input_text.comfort_alarm_message') }}"
    - !include includes/alarm_status_button.yaml
```

Then append the view include to the top-level **views list**, alongside the existing Home view (not inside its cards or sections):

```yaml
views:
  - title: Home
    # Keep the entire existing Home view here, unchanged.
  - !include includes/alarm_status_view.yaml
```

The examples show insertion points, not replacement dashboard files. Preserve the existing arming buttons, keypad, zones, messages, and other views. The current image dashboard is not present in this add-on repository, so this bundle intentionally supplies includes rather than a stale full-dashboard replacement.

## Data and behavior

- Requires the matching `1.0.10-dev2` add-on code from this repository.
- Publishes `cytech_comfort_mqtt/alarm/am_status` on events and at five-second heartbeat intervals. Payloads are not retained.
- The MQTT sensor is normally `sensor.comfort_am_status`. If a pre-existing entity causes a suffix, update the entity references in the table include to match.
- A new login resets observations. The bridge refreshes current trouble bits at 30-second intervals and after AM/AR events. No serial reports for 90 seconds makes monitoring offline; a stopped bridge's MQTT sensor expires after 45 seconds.
- Active/Cleared applies where the protocol supplies current trouble bits or restore reports. Event received applies where an ongoing state cannot be established. Unknown is never presented as clear.
- Each row includes the AM code (decimal), description, trigger policy, current status, last observation time in UTC, and details. Observed device/zone reports are shown separately below the table.
- For custom MQTT domains or dashboard URL paths, adjust the topic and navigation paths in these YAML files to match the image.

## Test the image

1. Build/install the `1.0.10-dev2` add-on from this repository.
2. Merge the YAML above into the HA image, validate its configuration, and reload/restart HA as appropriate for the image build process.
3. Confirm `sensor.comfort_am_status` becomes `online` and has a `rows` attribute.
4. Open Comfort Alarm. Confirm the new button is below Comfort Message and opens the table, and the back arrow returns correctly.
5. In a test setup, confirm an AM trouble report updates its row without publishing `triggered`; its AR/current trouble snapshot clears it. Confirm a normal triggering event still publishes `triggered`.
6. Stop the test add-on and confirm the table changes to Unknown after the sensor expires.

No live HA instance has been modified by adding this bundle to the repository. Hardware and HA frontend validation remain part of the image test.

## Local regression tests

From the `cytech_comfort_mqtt` directory:

```sh
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -p 'test_*.py' -v
```

The tests execute extracted protocol/bridge handlers without starting serial, MQTT, or Home Assistant services, and validate the YAML and Jinja table template.

References: [HA subviews](https://www.home-assistant.io/dashboards/views/#subview), [Markdown templates](https://www.home-assistant.io/dashboards/markdown/), [MQTT sensors](https://www.home-assistant.io/integrations/sensor.mqtt/).
