# Copyright (c) 2018 Khor Chin Heong (koochyrat@gmail.com)
# Copyright (c) 2025 Ingo de Jager (ingodejager@gmail.com)
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


"""Observed AM/AR state published to the Home Assistant dashboard via MQTT."""
import logging
import threading
import time
from datetime import datetime, timezone
NAMES = {
    0: 'Intruder', 1: 'Zone Trouble', 2: 'Low Battery', 3: 'Power Failure',
    4: 'Phone Trouble', 5: 'Duress', 6: 'Arm Failure', 7: 'Family Care',
    8: 'Security Off', 9: 'System Armed', 10: 'Tamper', 12: 'Entry Warning',
    13: 'Alarm Abort', 14: 'Siren Tamper', 15: 'Bypass', 17: 'Dial Test',
    19: 'Entry Alert', 20: 'Fire', 21: 'Panic', 22: 'GSM Trouble',
    23: 'New Message', 24: 'Doorbell', 25: 'Comms Failure RS485', 26: 'Signin Tamper',
}
RESTORABLE = frozenset({1, 2, 3, 4, 10, 14, 22, 25})
# The XX trouble bits already decoded/documented by Comfort_A_SecurityInformationReport.
TROUBLE_BITS = {3: 0, 2: 1, 1: 2, 25: 3, 10: 4, 4: 5, 22: 6}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class AlarmStatusTracker:
    def __init__(self, publish, trigger_policy):
        self.publish = publish
        self.trigger_policy = trigger_policy
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        """A new connection cannot inherit certainty from missed events."""
        with self.lock:
            self.rows = {}
            self.connected = False
            self.last_write = 0
            self.started = utc_now()
            self._write()

    def heartbeat(self, connected):
        with self.lock:
            changed = self.connected != bool(connected)
            self.connected = bool(connected)
            if changed or time.monotonic() - self.last_write >= 5:
                self._write()

    def _row(self, code):
        return self.rows.setdefault(str(code), {
            'status': 'Unknown', 'updated': None, 'message': '',
            'source': '', 'instances': {}, 'snapshot_active': False,
        })

    def event(self, report, restored=False):
        with self.lock:
            code = report.alarm
            row = self._row(code)
            row.update(updated=utc_now(), message=report.message,
                       source='AR restore' if restored else 'AM event')
            if code in RESTORABLE:
                # Phone trouble has no device identity in its displayed report.
                key = 'system' if code == 4 else str(report.parameter)
                row['instances'][key] = {
                    'status': 'Cleared' if restored else 'Active',
                    'message': report.message, 'updated': row['updated'],
                }
                active = any(v['status'] == 'Active' for v in row['instances'].values())
                # A restore for one device cannot clear an unidentified fault
                # from a prior aggregate snapshot. Await the next a? snapshot.
                row['status'] = 'Active' if active else (
                    'Unknown' if row['snapshot_active'] else 'Cleared'
                )
            else:
                row['status'] = 'Event received'
            self._write()

    def snapshot(self, report):
        with self.lock:
            for code, bit in TROUBLE_BITS.items():
                active = bool(report.XX & (1 << bit))
                row = self._row(code)
                row.update(status='Active' if active else 'Cleared',
                           snapshot_active=active, updated=utc_now(),
                           source='Current trouble bits (a?)')
                if not active:
                    for instance in row['instances'].values():
                        instance['status'] = 'Cleared'
                # Positive bits identify a fault category, not every device.
            self._write()

    def _write(self):
        """Called under the lock; failures must not interrupt alarm delivery."""
        try:
            self.publish(self.payload())
            self.last_write = time.monotonic()
        except Exception:
            logging.getLogger(__name__).exception('Cannot publish alarm status snapshot')

    def payload(self):
        rows = []
        for code in sorted(set(range(27)) | {int(code) for code in self.rows}):
            observed = self.rows.get(str(code), {})
            rows.append({
                'code': code, 'name': NAMES.get(code, f'Unknown({code})'),
                'triggers': self.trigger_policy(code),
                'status': observed.get('status', 'Unknown') if self.connected else 'Unknown',
                'last_status': observed.get('status', 'Unknown'),
                'updated': observed.get('updated'), 'message': observed.get('message', ''),
                'source': observed.get('source', ''),
                'instances': observed.get('instances', {}),
            })
        return {'status': 'online' if self.connected else 'offline',
                'updated': utc_now(), 'started': self.started, 'rows': rows}
