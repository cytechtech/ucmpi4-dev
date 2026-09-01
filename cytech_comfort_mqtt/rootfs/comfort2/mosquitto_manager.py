import os
import logging

import requests

logger = logging.getLogger(__name__)

SUPERVISOR_URL = "http://supervisor"
MOSQUITTO_ADDON = "core_mosquitto"


def get_mosquitto_options():
    """
    Read the current Mosquitto add-on options from the Home Assistant
    Supervisor API.

    This function does not modify the Mosquitto configuration.
    """
    token = os.environ.get("SUPERVISOR_TOKEN")

    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN is not available")

    response = requests.get(
        f"{SUPERVISOR_URL}/addons/{MOSQUITTO_ADDON}/info",
        headers={
            "Authorization": f"Bearer {token}",
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if data.get("result") != "ok":
        raise RuntimeError(
            f"Unable to read Mosquitto configuration: {data}"
        )

    options = data.get("data", {}).get("options", {})

    return options