import json
import logging
import os
from pathlib import Path

import requests


logger = logging.getLogger(__name__)

SUPERVISOR_URL = "http://supervisor"
MOSQUITTO_ADDON = "core_mosquitto"

MANAGED_USER_FILE = Path("/data/mosquitto_managed_user.json")


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

    return data.get("data", {}).get("options", {})


def get_managed_username():
    """
    Return the MQTT username previously managed by Comfort.

    Returns None on a new installation where no managed username
    has yet been recorded.
    """
    if not MANAGED_USER_FILE.is_file():
        return None

    try:
        data = json.loads(
            MANAGED_USER_FILE.read_text(encoding="utf-8")
        )

        username = data.get("username")

        if isinstance(username, str) and username:
            return username

    except Exception:
        logger.exception(
            "Unable to read managed Mosquitto username"
        )

    return None


def save_managed_username(username):
    """
    Record the MQTT username managed by Comfort.
    """
    MANAGED_USER_FILE.write_text(
        json.dumps(
            {"username": username},
            indent=2,
        ),
        encoding="utf-8",
    )


def check_managed_login(username, password):
    """
    Compare the requested Comfort MQTT login with the current
    Mosquitto configuration.

    This function is read-only. It does not modify Mosquitto.

    Returns True if Mosquitto would need to be changed.
    Returns False if the required login already exists with the
    correct password.
    """
    options = get_mosquitto_options()

    logins = options.get("logins", [])

    if not isinstance(logins, list):
        raise RuntimeError(
            "Mosquitto 'logins' option is not a list"
        )

    previous_username = get_managed_username()

    logger.info(
        "Checking Comfort-managed Mosquitto login "
        "(requested user: %s, previous managed user: %s)",
        username,
        previous_username or "not recorded",
    )

    for login in logins:
        if not isinstance(login, dict):
            continue

        if login.get("username") == username:
            if login.get("password") == password:
                logger.info(
                    "Comfort Mosquitto login already matches"
                )
                return False

            logger.info(
                "Comfort Mosquitto password requires updating"
            )
            return True

    logger.info(
        "Comfort Mosquitto username requires adding/updating"
    )

    return True