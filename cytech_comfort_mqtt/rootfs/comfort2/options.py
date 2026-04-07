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

import json
import os
from pathlib import Path

OPTIONS_PATH = Path("/data/options.json")

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

OPTIONS_PATH = Path("/data/options.json")


# ---------------------------------------------------------
# Core loader
# ---------------------------------------------------------

def load_options() -> Dict[str, Any]:
    """
    Load Home Assistant add-on options from /data/options.json.
    Returns empty dict if file not present.
    """
    if OPTIONS_PATH.exists():
        with OPTIONS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------
# Generic access helpers
# ---------------------------------------------------------

def _empty_to_none(value: Any) -> Any:
    """
    Convert empty string to None (HA optional string fields
    sometimes come through as "").
    """
    if value == "":
        return None
    return value


def get(options: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Read option from options.json.
    Falls back to ENV VAR using upper-case key.
    """
    if key in options:
        return _empty_to_none(options[key])

    env_key = key.upper()
    if env_key in os.environ:
        return _empty_to_none(os.environ[env_key])

    return default


def get_str(options: Dict[str, Any], key: str, default: Optional[str] = None) -> Optional[str]:
    value = get(options, key, default)
    if value is None:
        return None
    return str(value)


def get_int(options: Dict[str, Any], key: str, default: int) -> int:
    value = get(options, key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_bool(options: Dict[str, Any], key: str, default: bool) -> bool:
    value = get(options, key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)