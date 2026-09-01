import json
import logging
import os
from pathlib import Path

import requests


logger = logging.getLogger(__name__)

SUPERVISOR_URL = "http://supervisor"
MOSQUITTO_ADDON = "core_mosquitto"

MANAGED_USER_FILE = Path("/data/mosquitto_managed_user.json")


def _get_supervisor_token():
    token = os.environ.get("SUPERVISOR_TOKEN")

    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN is not available")

    return token


def get_mosquitto_options():
    """
    Read the current Mosquitto add-on options from the
    Home Assistant Supervisor API.
    """
    token = _get_supervisor_token()

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

    Returns None if no managed username has yet been recorded.
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


def _write_mosquitto_options(options):
    """
    Write Mosquitto add-on options using the
    Home Assistant Supervisor API.
    """
    token = _get_supervisor_token()

    response = requests.post(
        f"{SUPERVISOR_URL}/addons/{MOSQUITTO_ADDON}/options",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "options": options,
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if data.get("result") != "ok":
        raise RuntimeError(
            f"Unable to update Mosquitto configuration: {data}"
        )


def ensure_managed_login(username, password):
    """
    Ensure that Mosquitto contains the username/password requested
    by the Comfort add-on.

    Only the Comfort-managed login is changed. Other Mosquitto
    logins and all other Mosquitto options are preserved.

    Returns:
        True if the Mosquitto configuration was changed.
        False if no Mosquitto configuration change was required.
    """
    if not username:
        raise RuntimeError(
            "Comfort MQTT username must not be empty"
        )

    if not password:
        raise RuntimeError(
            "Comfort MQTT password must not be empty"
        )

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

    #
    # First installation/upgrade:
    # If the requested account already exists with the correct
    # password, adopt it as the Comfort-managed account.
    #
    if previous_username is None:
        for login in logins:
            if not isinstance(login, dict):
                continue

            if login.get("username") == username:
                if login.get("password") == password:
                    save_managed_username(username)

                    logger.info(
                        "Existing Mosquitto login adopted as "
                        "Comfort-managed account"
                    )

                    return False

                raise RuntimeError(
                    "Requested Comfort MQTT username already exists "
                    "in Mosquitto with a different password"
                )

    new_logins = []

    #
    # Preserve every login except the previously managed
    # Comfort account.
    #
    for login in logins:
        if not isinstance(login, dict):
            new_logins.append(login)
            continue

        login_username = login.get("username")

        if (
            previous_username is not None
            and login_username == previous_username
        ):
            continue

        #
        # The requested new username must not belong to another
        # existing Mosquitto account.
        #
        if login_username == username:
            raise RuntimeError(
                "Requested Comfort MQTT username already belongs "
                "to another Mosquitto account"
            )

        new_logins.append(login)

    #
    # Add the required Comfort account.
    #
    new_logins.append(
        {
            "username": username,
            "password": password,
        }
    )

    options["logins"] = new_logins

    _write_mosquitto_options(options)

    #
    # Only record the new username after Supervisor has
    # successfully accepted the Mosquitto configuration.
    #
    save_managed_username(username)

    logger.info(
        "Comfort-managed Mosquitto login updated successfully"
    )

    return True