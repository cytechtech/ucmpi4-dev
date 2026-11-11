# Copyright (c) 2026 Cytech Technology Pte Ltd
#
# Original project code by Khor Chin Heong.
# Modifications in 2025 by Ingo de Jager.

# Further modifications and enhancements in 2026 by Cytech Technology Pte Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Session-scoped CM work and feedback, independent of MQTT/HA."""
from collections import deque
from threading import RLock
from home_control_protocol import action, query, decode


class HomeControl:
    def __init__(self, publish_state):
        self.lock = RLock()
        self.controls = {}
        self.pending = deque()
        self.active = False
        self.next_send = 0
        self.publish_state = publish_state

    def configure(self, controls):
        with self.lock:
            self.controls = dict(controls)
            self.start(self.active)

    def start(self, active=True):
        with self.lock:
            self.active = active
            self.pending.clear()
            self.next_send = 0
            if active:
                for c in self.controls.values():
                    if c.has_feedback:
                        self.publish_state(c, None, "")
                self.pending.extend(query(*address) for address, c in self.controls.items() if c.has_feedback)

    def command(self, group, key, number=None):
        with self.lock:
            control = self.controls.get((group, key))
            if not self.active or control is None or len(self.pending) >= 128:
                raise ValueError("Home Control unavailable or command queue full")
            if number is not None and number not in {a.number for a in control.actions}:
                raise ValueError("Action is not defined in CCLX")
            self.pending.append(query(group, key) if number is None else action(group, key, number))

    def tick(self, now, ready, send):
        with self.lock:
            if not ready:
                self.start(False)
                return
            if self.active and self.pending and now >= self.next_send:
                command = self.pending.popleft()
                self.next_send = now + 0.1
                send(("\x03" + command + "\r").encode("ascii"))

    def receive(self, message):
        report = decode(message)
        with self.lock:
            control = self.controls.get((report.group, report.key))
            if self.active and control is not None:
                self.publish_state(control, report.value(control.feedback_type.lower() == "sensor"), report.raw)
