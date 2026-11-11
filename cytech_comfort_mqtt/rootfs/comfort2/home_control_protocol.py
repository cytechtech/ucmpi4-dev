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

"""CM wire format, independent of transport and presentation."""
import re
from dataclasses import dataclass


def query(group, key):
    if type(group) is not int or type(key) is not int or not 0 <= group <= 5 or not 0 <= key <= 9:
        raise ValueError("Invalid Home Control address")
    return f"CM{group:02X}{key:02X}"


def action(group, key, number):
    if type(number) is not int or not 0 <= number <= 9:
        raise ValueError("Invalid Home Control action")
    return query(group, key) + f"{number:02X}"


@dataclass(frozen=True)
class Report:
    group: int
    key: int
    raw: str

    def value(self, sensor=False):
        if not self.raw:
            return None
        low = int(self.raw[:2], 16)
        if not sensor:
            return low
        value = low | ((int(self.raw[2:], 16) if len(self.raw) == 4 else 0) << 8)
        return value - 65536 if value & 32768 else value


def decode(message):
    if not re.fullmatch(r"cm[0-9A-Fa-f]{4}(?:[0-9A-Fa-f]{2}){0,2}", message):
        raise ValueError("Malformed CM report")
    group, key = int(message[2:4], 16), int(message[4:6], 16)
    query(group, key)
    return Report(group, key, message[6:])
