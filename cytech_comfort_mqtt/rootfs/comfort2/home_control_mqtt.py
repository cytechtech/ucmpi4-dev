"""MQTT contract and Home Assistant presentation for Home Control."""
import json
import re
from dataclasses import asdict


class HomeControlMqtt:
    def __init__(self, client, domain):
        self.client, self.domain = client, domain

    def base(self, group, key):
        return f"{self.domain}/home_control/{group:02d}/{key:02d}"

    def state(self, control, value, raw):
        self.client.publish(self.base(control.group, control.key) + "/state",
                            json.dumps({"value": value, "raw": raw}), qos=1, retain=True)

    def clear(self):
        # Bounded full namespace cleanup also covers removed controls after restart.
        for g in range(6):
            for k in range(10):
                stem = f"home_control_{g:02d}_{k:02d}"
                self.client.publish(f"homeassistant/sensor/{self.domain}/{stem}/config", None, qos=1, retain=True)
                self.client.publish(self.base(g, k) + "/state", None, qos=1, retain=True)
                for a in range(10):
                    self.client.publish(f"homeassistant/button/{self.domain}/{stem}_{a}/config", None, qos=1, retain=True)

    def discovery(self, controls, device, availability):
        metadata_topic = f"{self.domain}/meta/home_control"
        menu = {"name": "Home Control Menu", "unique_id": f"{self.domain}_home_control_menu",
                "default_entity_id": f"sensor.{self.domain}_home_control_menu",
                "device": device, "state_topic": metadata_topic,
                "value_template": '{{ value_json["items"] | count }}',
                "json_attributes_topic": metadata_topic,
                "json_attributes_template": '{{ {"items": value_json["items"], "comfort_home_control_menu": ' + json.dumps(self.domain) + '} | tojson }}',
                "availability": availability, "availability_mode": "all"}
        self.client.publish(f"homeassistant/sensor/{self.domain}/home_control_menu/config", json.dumps(menu), qos=1, retain=True)
        self.client.publish(f"{self.domain}/meta/home_control", json.dumps({
            "items": [asdict(c) for c in controls.values()]}), qos=1, retain=True)
        for c in controls.values():
            stem = f"home_control_{c.group:02d}_{c.key:02d}"
            common = {"device": device, "availability": availability, "availability_mode": "all"}
            def identity(suffix):
                return {"json_attributes_topic": metadata_topic,
                        "json_attributes_template": '{{ {"comfort_home_control": ' +
                        json.dumps(f"{self.domain}:{c.group}:{c.key}:{suffix}") + '} | tojson }}'}
            name = f"{c.group_label} {c.label}".strip()
            if c.has_feedback:
                payload = dict(common, name=name, unique_id=f"{self.domain}_{stem}",
                               default_entity_id=f"sensor.{self.domain}_{stem}",
                               state_topic=self.base(c.group, c.key) + "/state",
                               value_template="{{ value_json.value if value_json.value is not none else 'unknown' }}")
                payload.update(identity("state"))
                self.client.publish(f"homeassistant/sensor/{self.domain}/{stem}/config", json.dumps(payload), qos=1, retain=True)
            for a in c.actions:
                payload = dict(common, name=f"{name} {a.label}", unique_id=f"{self.domain}_{stem}_{a.number}",
                               default_entity_id=f"button.{self.domain}_{stem}_{a.number}",
                               command_topic=self.base(c.group, c.key) + "/set", payload_press=str(a.number))
                payload.update(identity(a.number))
                self.client.publish(f"homeassistant/button/{self.domain}/{stem}_{a.number}/config", json.dumps(payload), qos=1, retain=True)

    def command(self, msg, service):
        if getattr(msg, "retain", False):
            raise ValueError("Retained Home Control commands are ignored")
        match = re.fullmatch(re.escape(self.domain) + r"/home_control/(\d{2})/(\d{2})/(set|query)", msg.topic)
        if match is None:
            raise ValueError("Invalid Home Control topic")
        group, key = int(match[1]), int(match[2])
        number = None
        if match[3] == "set":
            payload = msg.payload.decode("ascii").strip()
            if not re.fullmatch(r"[0-9]", payload):
                raise ValueError("Action must be a digit from 0 to 9")
            number = int(payload)
        service.command(group, key, number)
