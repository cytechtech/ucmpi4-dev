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
# cclx_parser.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Any, Optional, Union, Tuple
import os

import defusedxml.ElementTree as ET

import logging
logger = logging.getLogger(__name__)


CheckNameFn = Callable[[str], bool]
CheckIndexFn = Callable[[str, int], bool]  # your code uses CheckIndexNumberFormat(value, max_index=1024)


@dataclass
class CclxParseFlags:
    devicemap: bool = False
    zonemap: bool = False
    countermap: bool = False
    flagmap: bool = False
    outputmap: bool = False
    sensormap: bool = False
    timermap: bool = False
    usermap: bool = False


@dataclass
class CclxParseResult:
    found: bool
    flags: CclxParseFlags = field(default_factory=CclxParseFlags)

    device_properties: Dict[str, Any] = field(default_factory=dict)
    input_properties: Dict[str, Dict[str, Any]] = field(default_factory=dict)   # { "1": {"Name":..,"ZoneWord":..,"VirtualInput":..}, ... }
    counter_properties: Dict[str, str] = field(default_factory=dict)
    flag_properties: Dict[str, str] = field(default_factory=dict)
    output_properties: Dict[str, str] = field(default_factory=dict)
    sensor_properties: Dict[str, str] = field(default_factory=dict)
    timer_properties: Dict[str, str] = field(default_factory=dict)
    user_properties: Dict[str, str] = field(default_factory=dict)


def parse_cclx(
    file_path: Union[str, Path],
    *,
    device_properties_in: Optional[Dict[str, Any]] = None,
    check_zone_name: CheckNameFn,
    check_index_number: CheckIndexFn,
    logger,
    max_outputs: int = 96,
) -> CclxParseResult:
    """
    Parse a Comfort configurator .cclx file and return the dictionaries that were previously
    populated by add_descriptions().

    This function mirrors the logic in comfort2.py add_descriptions():
    - truncates names/numbers exactly the same way
    - validates using the same check_* functions
    - sets the same "MAPFILE" boolean flags
    - populates the same dictionaries
    """

    file = Path(file_path)
    device_properties = dict(device_properties_in or {})

    # Prepare outputs (mirrors your add_descriptions() reinitialising these dicts)
    result = CclxParseResult(found=False)
    result.device_properties = device_properties
    result.input_properties = {}
    result.counter_properties = {}
    result.flag_properties = {}
    result.output_properties = {}
    result.sensor_properties = {}
    result.user_properties = {}
    result.timer_properties = {}

    if not file.is_file():
        # Mirrors your "else:" branch for file not found
        device_properties["CustomerName"] = None
        device_properties["Reference"] = None
        device_properties["Version"] = None
        device_properties["ComfortFileSystem"] = None
        device_properties["ComfortFirmwareType"] = None

        logger.info("Comfigurator (CCLX) File Not Found")
        device_properties["uid"] = None
        result.found = False
        return result

    # File exists
    try:
        file_stats = os.stat(file)
        logger.info("Comfigurator (CCLX) File detected, %s Bytes", file_stats.st_size)

        tree = ET.parse(file)
        root = tree.getroot()
    except Exception as e:
        # Keep this robust: parse errors shouldn't crash your add-on
        logger.error("Failed to parse CCLX file '%s': %s", str(file), e)
        device_properties["uid"] = None
        result.found = True  # it exists, but parsing failed
        return result

    result.found = True

    # ---- ConfigInfo -> device_properties ----
    for entry in root.iter("ConfigInfo"):
        customer_name = entry.attrib.get("CustomerName")[:200] if entry.attrib.get("CustomerName") else None
        reference = entry.attrib.get("Reference")[:200] if entry.attrib.get("Reference") else None
        comfort_filesystem = entry.attrib.get("ComfortFileSystem")[:2] if entry.attrib.get("ComfortFileSystem") else None
        comfort_firmware = entry.attrib.get("ComfortFirmwareType")

        device_properties["CustomerName"] = customer_name
        device_properties["Reference"] = reference
        device_properties["ComfortFileSystem"] = comfort_filesystem
        device_properties["ComfortFirmwareType"] = comfort_firmware
        device_properties["CPUType"] = "N/A"

        result.flags.devicemap = True

    # ---- Zones -> input_properties ----
    for zone in root.iter("Zone"):
        name = zone.attrib.get("Name")[:16] if zone.attrib.get("Name") else ""
        number = zone.attrib.get("Number")[:3] if zone.attrib.get("Number") else ""
        virtualinput = zone.attrib.get("VirtualInput")[:5] if zone.attrib.get("VirtualInput") else ""

        zoneword_parts = []
        zw1 = zone.attrib.get("ZoneWord1")[:16] if zone.attrib.get("ZoneWord1") else ""
        zw2 = zone.attrib.get("ZoneWord2")[:16] if zone.attrib.get("ZoneWord2") else ""
        zw3 = zone.attrib.get("ZoneWord3")[:16] if zone.attrib.get("ZoneWord3") else ""
        zw4 = zone.attrib.get("ZoneWord4")[:16] if zone.attrib.get("ZoneWord4") else ""
        if zw1 is not None:
            zoneword_parts.append(zw1)
        if zw2 is not None:
            zoneword_parts.append(zw2)
        if zw3 is not None:
            zoneword_parts.append(zw3)
        if zw4 is not None:
            zoneword_parts.append(zw4)
        zoneword = " ".join(p for p in zoneword_parts if p).strip()

        if check_index_number(number, 1024):
            result.flags.zonemap = True
        else:
            number = ""
            logger.error("Invalid Zone Number detected in '%s'.", str(file))
            result.flags.zonemap = False
            break

        if check_zone_name(name):
            result.flags.zonemap = True
        else:
            name = ""
            logger.error("Invalid Zone Name detected in '%s'.", str(file))
            result.flags.zonemap = False
            break

        result.input_properties[number] = {
            "Name": name,
            "ZoneWord": zoneword,
            "VirtualInput": virtualinput,
        }

    # ---- Counters ----
    for counter in root.iter("Counter"):
        name = counter.attrib.get("Name")[:16] if counter.attrib.get("Name") else ""
        number = counter.attrib.get("Number")[:3] if counter.attrib.get("Number") else ""

        if check_index_number(number, 1024):
            result.flags.countermap = True
        else:
            number = ""
            logger.error("Invalid Counter Number detected in '%s'.", str(file))
            result.flags.countermap = False
            break

        if check_zone_name(name):
            result.flags.countermap = True
        else:
            name = ""
            logger.error("Invalid Counter Name detected in '%s'.", str(file))
            result.flags.countermap = False
            break

        result.counter_properties[number] = name

    # ---- Flags ----
    for flag in root.iter("Flag"):
        name = flag.attrib.get("Name")[:16] if flag.attrib.get("Name") else ""
        number = flag.attrib.get("Number")[:3] if flag.attrib.get("Number") else ""

        if check_index_number(number, 1024):
            result.flags.flagmap = True
        else:
            number = ""
            logger.error("Invalid Flag Number detected in '%s'.", str(file))
            result.flags.flagmap = False
            break

        if check_zone_name(name):
            result.flags.flagmap = True
        else:
            name = ""
            logger.error("Invalid Flag Name detected in '%s'.", str(file))
            result.flags.flagmap = False
            break

        result.flag_properties[number] = name

    # ---- Outputs ----
    # ---- Outputs ----
    for output in root.iter("Output"):
        name = output.attrib.get("Name")[:16] if output.attrib.get("Name") else ""
        number = output.attrib.get("Number")[:3] if output.attrib.get("Number") else ""

        if check_index_number(number, 1024):
            result.flags.outputmap = True
        else:
            number = ""
            logger.error("Invalid Output Number detected in '%s'.", str(file))
            result.flags.outputmap = False
            break

        # NEW: exclude SCSRIO outputs > max_outputs (eg > 96)
        try:
            out_n = int(number)
        except ValueError:
            logger.error("Invalid Output Number detected in '%s'.", str(file))
            result.flags.outputmap = False
            break

        if out_n < 1 or out_n > max_outputs:
            continue

        if check_zone_name(name):
            result.flags.outputmap = True
        else:
            name = ""
            logger.error("Invalid Output Name detected in '%s'.", str(file))
            result.flags.outputmap = False
            break

        result.output_properties[number] = name


    # ---- Sensors (SensorResponse) ----
    for sensor in root.iter("SensorResponse"):
        name = sensor.attrib.get("Name")[:16] if sensor.attrib.get("Name") else ""
        number = sensor.attrib.get("Number")[:3] if sensor.attrib.get("Number") else ""

        if check_index_number(number, 1024):
            result.flags.sensormap = True
        else:
            number = ""
            logger.error("Invalid Sensor Number detected in '%s'.", str(file))
            result.flags.sensormap = False
            break

        if check_zone_name(name):
            result.flags.sensormap = True
        else:
            name = ""
            logger.error("Invalid Sensor Name detected in '%s'.", str(file))
            result.flags.sensormap = False
            break

        result.sensor_properties[number] = name

    # ---- Timers ----
    for timer in root.iter("Timer"):
        name = timer.attrib.get("Name")[:16] if timer.attrib.get("Name") else ""
        number = timer.attrib.get("Number")[:3] if timer.attrib.get("Number") else ""

        if check_index_number(number, 1024):
            result.flags.timermap = True
        else:
            number = ""
            logger.error("Invalid Timer Number detected in '%s'.", str(file))
            result.flags.timermap = False
            break

        if check_zone_name(name):
            result.flags.timermap = True
        else:
            name = ""
            logger.error("Invalid Timer Name detected in '%s'.", str(file))
            result.flags.timermap = False
            break

        result.timer_properties[number] = name

    # ---- Users (Authorisation) ----
    for user in root.iter("Authorisation"):
        name = user.attrib.get("Name")[:16] if user.attrib.get("Name") else ""
        number = user.attrib.get("Number")[:3] if user.attrib.get("Number") else ""

        if check_index_number(number, 1024):
            result.flags.usermap = True
        else:
            number = ""
            logger.error("Invalid User Number detected in '%s'.", str(file))
            result.flags.usermap = False
            break

        if check_zone_name(name):
            result.flags.usermap = True
        else:
            name = ""
            logger.error("Invalid User Name detected in '%s'.", str(file))
            result.flags.usermap = False
            break

        result.user_properties[number] = name

    # Mirrors end-of-method behaviour
    device_properties["uid"] = None
    return result
