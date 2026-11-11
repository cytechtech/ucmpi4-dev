# Automatic Comfort Home Control dashboard

After one-time installation, apply a new CCLX in the add-on to update the
dashboard automatically. Groups, controls, action labels and feedback are read
from MQTT metadata and HA entities. Do not create another dashboard, regenerate
YAML, or change the alarm dashboard when a CCLX changes.

## One-time installation

1. Install the updated add-on and apply a CCLX. Its MQTT discovery creates a
   Home Control Menu sensor as well as feedback sensors and action buttons.
2. Copy `www/comfort-home-control-card.js` from this folder to
   `/config/www/comfort-home-control-card.js` in Home Assistant. Create `www`
   if necessary. This bundled custom card requires no HACS installation.
3. Register the JavaScript resource once. For UI-managed resources, enable
   Advanced Mode in your HA profile, then open Settings → Dashboards → menu →
   Resources. Add `/local/comfort-home-control-card.js?v=1` as a JavaScript
   module. Reload the browser after registering it.
4. Create a new dashboard named **Comfort Home Control**, open its raw
   configuration editor, and paste `dashboards/home_control.yaml`. Users of
   the previous static dashboard can replace its raw configuration instead.
   If using a custom MQTT domain, change the card's `domain` once.

The card finds entities by their metadata, so HA entity renames or numeric
suffixes do not require dashboard changes. Buttons invoke HA's `button.press`
action with the resolved entity. No broker credentials are needed by the card.

## YAML-managed HA images

Copy the JavaScript file as above and copy `dashboards/home_control.yaml` to
`/config/dashboards/home_control.yaml`. Merge this into the existing
`lovelace` mapping, preserving the alarm dashboard and other registrations:

```yaml
lovelace:
  dashboards:
    comfort-home-control:
      mode: yaml
      title: Comfort Home Control
      icon: mdi:home-automation
      show_in_sidebar: true
      filename: dashboards/home_control.yaml
```

Keep the existing resource mode. If resources are managed in the UI, register
the module in Settings → Dashboards → Resources as described above. If resources
are already managed in YAML, append the module to the existing `lovelace.resources`
list. Switching resource modes affects every dashboard. Check the HA configuration
and restart HA for the new dashboard registration. Open `/comfort-home-control/home`.

## Everyday use

Upload and apply the changed CCLX through the add-on. Discovery and retained
menu metadata update; the open dashboard adds/removes groups and controls,
updates labels and shows current actions. It also reads retained definitions
after HA restarts. No CCLX-specific YAML is required. The older Python generator
remains an optional static export tool and is not used by this dashboard.

Feedback is raw numeric CM feedback. Unknown means no feedback has arrived.
When the panel/bridge is unavailable, actions are disabled and feedback is
marked unavailable. No-feedback controls are labelled explicitly. An empty
menu shows an empty-state message. A selected group removed by a reload falls
back to the first remaining group.

## Verify on the HA test image

Confirm groups and controls appear, feedback updates and buttons invoke the
correct action. Rename an HA action entity and verify it still works. Apply
a CCLX with renamed, added and removed controls: the open card should update
without editing YAML. Check empty menus, disconnect/reconnect and Comfort
Alarm independently. Live HA frontend/hardware validation is still required;
these files have not been installed on a running HA system.

For later card software updates, replace the JavaScript file and increment the
resource URL version to refresh browser caches. CCLX changes do not require this.

Run the card state-transition tests from the repository root with
`node --test cytech_comfort_mqtt/tests/test_home_control_card.cjs`. These cover
metadata changes, renamed entities, offline/empty states and action errors;
they do not replace visual verification in Home Assistant.
