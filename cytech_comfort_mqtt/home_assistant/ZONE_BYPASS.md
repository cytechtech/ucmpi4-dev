# Per-zone bypass controls (dev6)

The add-on discovers two MQTT buttons and one status sensor for every configured zone.
Set bypass sends DA4BZZ immediately. Clear bypass sends DA4CZZ immediately.
Each action requests B?ZZ; BY, B? and startup b?00 reports supply the actual status.
No scheduling, persistent bypass policy, or automatic clearing on disarm is added.
Status is not changed optimistically when a button is pressed.

Topic contract (zone number is decimal in MQTT and hexadecimal on the serial wire):
- cytech_comfort_mqtt/zone/1/bypass/set: SET or CLEAR, never retained.
- cytech_comfort_mqtt/zone/1/bypass/state: Bypassed or Not bypassed, retained.
- Discovery uses the existing panel availability and connected topics together.
- Retained commands, out-of-range zones, and offline/passthrough requests are ignored.

The customer-owned Comfort Entities dashboard must include these new entities.
Use dashboards/includes/zone_bypass_example.yaml as a native entities-card example;
repeat for each zone and adjust IDs to those assigned by Home Assistant.
An add-on update does not edit the live dashboard or install this YAML.

MQTT button documentation: https://www.home-assistant.io/integrations/button.mqtt/
