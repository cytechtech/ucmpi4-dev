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

import defusedxml.ElementTree as ET
import os
import requests
import json
from pathlib import Path
import re
import signal
import ipaddress
import socket
import serial
import time
import datetime
import threading
import logging
from datetime import datetime, timedelta
import secrets
import paho.mqtt.client as mqtt
from argparse import ArgumentParser
from comfort_protocol import (
    ComfortLUUserLoggedIn,
    ComfortIPInputActivationReport,
    ComfortCTCounterActivationReport,
    ComfortTRReport,
    ComfortOPOutputActivationReport,
    ComfortFLFlagActivationReport,
    ComfortBYBypassActivationReport,
    ComfortZ_ReportAllZones,
    Comfort_RSensorActivationReport,
    Comfort_R_ReportAllSensors,
    ComfortY_ReportAllOutputs,
    Comfort_Y_ReportAllOutputs,
    ComfortB_ReportAllBypassZones,
    Comfortf_ReportAllFlags,
    ComfortM_SecurityModeReport,
    ComfortS_SecurityModeReport,
    ComfortERArmReadyNotReady,
    ComfortAMSystemAlarmReport,
    ComfortALSystemAlarmReport,
    Comfort_A_SecurityInformationReport,
    ComfortARSystemAlarmReport,
    ComfortV_SystemTypeReport,
    Comfort_U_SystemCPUTypeReport,
    Comfort_EL_HardwareModelReport,
    Comfort_D_SystemVoltageReport,
    ComfortSN_SerialNumberReport,
    ComfortEXEntryExitDelayStarted,
)

from cclx_parser import parse_cclx
import settings
from collections import deque
import json
from pathlib import Path

import inspect

from options import load_options, get_str, get_int, get_bool

from queue import Queue, Empty

def is_ipv4_address(address):
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False

def resolve_to_ip(fqdn):
    try:
        return socket.gethostbyname(fqdn)
    except socket.gaierror:
        return None

def is_ipv4_address(address):
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False


def get_ip_address(input_value):
    if is_ipv4_address(input_value):
        return input_value
    else:
        return resolve_to_ip(input_value)



logger = logging.getLogger(__name__)
_opts = load_options()

# ----------------------------
# Runtime configuration
# ----------------------------

# MQTT
settings.MQTTBROKER = get_str(_opts, "mqtt_broker_address", "core-mosquitto")
settings.MQTTPORT = get_int(_opts, "mqtt_broker_port", 1883)
settings.MQTTUSERNAME = get_str(_opts, "mqtt_user", None)
settings.MQTTPASSWORD = get_str(_opts, "mqtt_password", None)
settings.MQTTPROTOCOL = get_str(_opts, "mqtt_protocol", "TCP")
# Optional resolved broker IP for diagnostics
settings.MQTTBROKERIP = get_ip_address(settings.MQTTBROKER)

# Comfort
settings.COMFORT_LOGIN_ID = get_str(_opts, "comfort_login_id", "")
settings.COMFORT_CCLX_FILE = get_str(_opts, "comfort_cclx_file", None)
settings.COMFORT_TIME = get_bool(_opts, "comfort_time", False)

battery_id = get_int(_opts, "comfort_battery_update", 1)
settings.COMFORT_BATTERY_STATUS_ID = (
    battery_id if battery_id in [0, 1] + list(range(33, 40)) else 1
)


# Alarm sizing
settings.COMFORT_INPUTS = get_int(_opts, "alarm_inputs", 8)
settings.COMFORT_OUTPUTS = get_int(_opts, "alarm_outputs", 0)
settings.COMFORT_RESPONSES = get_int(_opts, "alarm_responses", 0)
settings.UI_FLAG_COUNT = get_int(_opts, "flag_count", 8)
settings.UI_COUNTER_COUNT = get_int(_opts, "counter_count", 8)
settings.UI_TIMER_COUNT = get_int(_opts, "timer_count", 8)
settings.UI_SENSOR_COUNT = get_int(_opts, "sensor_count", 8)


if settings.COMFORT_INPUTS < 8:
    settings.COMFORT_INPUTS = 8
if settings.COMFORT_INPUTS > settings.MAX_ZONES:
    settings.COMFORT_INPUTS = settings.MAX_ZONES
ALARMVIRTUALINPUTRANGE = range(1, settings.COMFORT_INPUTS + 1)

if settings.COMFORT_OUTPUTS < 0:
    settings.COMFORT_OUTPUTS = 0
if settings.COMFORT_OUTPUTS > settings.MAX_OUTPUTS:
    settings.COMFORT_OUTPUTS = settings.MAX_OUTPUTS
ALARMNUMBEROFOUTPUTS = settings.COMFORT_OUTPUTS

if settings.COMFORT_RESPONSES < 0:
    settings.COMFORT_RESPONSES = 0
if settings.COMFORT_RESPONSES > settings.MAX_RESPONSES:
    settings.COMFORT_RESPONSES = settings.MAX_RESPONSES
ALARMNUMBEROFRESPONSES = settings.COMFORT_RESPONSES

if settings.UI_FLAG_COUNT < 0:
    settings.UI_FLAG_COUNT = 0
if settings.UI_FLAG_COUNT > settings.MAX_FLAGS:
    settings.UI_FLAG_COUNT = settings.MAX_FLAGS

if settings.UI_COUNTER_COUNT < 0:
    settings.UI_COUNTER_COUNT = 0
if settings.UI_COUNTER_COUNT > settings.MAX_COUNTERS:
    settings.UI_COUNTER_COUNT = settings.MAX_COUNTERS

if settings.UI_TIMER_COUNT < 0:
    settings.UI_TIMER_COUNT = 0
if settings.UI_TIMER_COUNT > settings.MAX_TIMERS:
    settings.UI_TIMER_COUNT = settings.MAX_TIMERS

if settings.UI_SENSOR_COUNT < 0:
    settings.UI_SENSOR_COUNT = 0
if settings.UI_SENSOR_COUNT > settings.MAX_SENSORS:
    settings.UI_SENSOR_COUNT = settings.MAX_SENSORS

# Logging
settings.LOG_VERBOSITY = get_str(_opts, "log_verbosity", "INFO").upper()
if settings.LOG_VERBOSITY not in ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]:
    settings.LOG_VERBOSITY = "INFO"

logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=getattr(logging, settings.LOG_VERBOSITY, logging.INFO),
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger.info("Completed importing addon configuration options")
logger.debug("MQTT_USER = %s", settings.MQTTUSERNAME)
logger.debug("MQTT_PASSWORD = ******")
logger.debug("MQTT_SERVER = %s", settings.MQTTBROKERIP)

logger.debug("MQTT_PROTOCOL = %s/%s", settings.MQTTPROTOCOL, settings.MQTTPORT)
logger.debug("COMFORT_LOGIN_ID = ******")
logger.debug("COMFORT_CCLX_FILE = %s", settings.COMFORT_CCLX_FILE)
logger.debug("COMFORT_BATTERY_STATUS_ID = %s", settings.COMFORT_BATTERY_STATUS_ID)
logger.debug("MQTT_LOG_LEVEL = %s", settings.LOG_VERBOSITY)
logger.debug("COMFORT_TIME = %s", settings.COMFORT_TIME)
logger.debug("BATTERYREFRESHTOPIC = %s", settings.BATTERYREFRESHTOPIC)
logger.debug("COMFORT_BATTERY_STATUS_ID = %s", settings.COMFORT_BATTERY_STATUS_ID)
logger.debug("CPUType = %s", settings.device_properties.get("CPUType"))


ACTIVE_CLIENT = None
MQTT_DEVICE_COMFORT = None  # Comfort device dict used for MQTT discovery republish on reload

class LoggedSerial(serial.Serial):
    """Serial wrapper with concise TX/RX logging."""

    def write(self, data):
        try:
            text = data.decode("ascii", errors="replace")
        except Exception:
            text = repr(data)

        logger.debug("TX: %r", text)
        return super().write(data)

    def read(self, size=1):
        data = super().read(size)
        if data:
            try:
                text = data.decode("ascii", errors="replace")
            except Exception:
                text = repr(data)

           # logger.debug("RX: %r", text)

        return data


TOKEN = os.getenv('SUPERVISOR_TOKEN')

supervisor_url = 'http://supervisor'
addon_info_url = f'{supervisor_url}/addons/self/info'

headers = {
    'Authorization': f'Bearer {TOKEN}',
    'Content-Type': 'application/json'
}

try:
    response = requests.get(addon_info_url, headers=headers, timeout=5)
except:
    logger.error("Failed to connect to Home Assistant Supervisor")
else:
    if response.status_code == 200:
        addon_info = response.json()
        ADDON_SLUG = addon_info['data']['slug']
        ADDON_VERSION = addon_info['data']['version']
    else:
        logger.error("Failed to get Addon Info: Error Code %s, %s", response.status_code, response.reason)




def validate_port(_port, min=1, max=65535):
    try:
        port = int(_port)
        if min <= int(port) <= max:
            return True
        else:
            logging.error(f"Invalid parameter: {port}")     #Integer
            return False
    except Exception as e:
        logging.error(f"Invalid parameter: {_port}")        #Original passed value
        return False    

# Send all alarm related data to HA so it can be shown in the UX as a live log of events.
# This is for debugging and also to see the history of events leading up to an alarm.

class RollingMqttLog:
    def __init__(self, mqtt_client, topic, max_lines=80, ts_format="%H:%M:%S"):
        self.mqtt = mqtt_client
        self.topic = topic
        self.lines = deque(maxlen=max_lines)
        self.ts_format = ts_format
        self._last_key = None
        self._last_time = None


    def add(self, text, level="INFO"):
        safe = str(text).replace("\r", " ").replace("\n", " ").strip()
        if not safe:
            return

        now = datetime.now()
        key = f"{level}:{safe}"

        # Drop identical repeats within 2 seconds
        if self._last_key == key and self._last_time and (now - self._last_time).total_seconds() < 2:
            return

        self._last_key = key
        self._last_time = now

        ts = datetime.now().strftime(self.ts_format)
        line = f"[{ts}] {level}: {safe}"
        self.lines.append(line)

        payload_text = "\n".join(self.lines)
        payload = json.dumps({"state": ts, "log": payload_text})

        self.mqtt.publish(self.topic, payload, qos=1, retain=True)

    def clear(self, note="Log cleared"):
        self.lines.clear()
        self.add(note, level="INFO")


class Comfort2(mqtt.Client):

    def init(self, mqtt_ip, mqtt_port, mqtt_username, mqtt_password, comfort_pincode, mqtt_version):
        self.mqtt_ip = mqtt_ip
        self.mqtt_port = mqtt_port
        self.comfort_pincode = comfort_pincode
        self.connected = False
        self.username_pw_set(mqtt_username, mqtt_password)
        self.version = mqtt_version

        self._last_reload_ts = 0.0
        self._reload_lock = threading.Lock()

        # Debounced writes for counters and sensors
        self.pending_counter_updates = {}
        self.pending_sensor_updates = {}
        self.counter_timers = {}
        self.sensor_timers = {}
        self.update_lock = threading.Lock()
        self.serial_queue = Queue(maxsize=1000)
        self.serial_running = True
        self._line_pattern = re.compile(r'(\x03[a-zA-Z0-9!?]*)$')

    def handler(self, signum, frame):                 # Ctrl-Z Keyboard Interrupt
        logger.debug('SIGTSTP (Ctrl-Z) intercepted')

    def sigquit_handler(self, signum, frame):         # Ctrl-\ Keyboard Interrupt
        logger.debug("SIGQUIT intercepted")
        settings.RUN = False
    
    
    if os.name != 'nt':
        signal.signal(signal.SIGTSTP, handler)

    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc, properties):

        settings.FIRST_LOGIN = True      # Set to True to start refresh on_connect

        if rc == 'Success':

            settings.BROKERCONNECTED = True
            settings.device_properties['BridgeConnected'] = 1

            logger.info('MQTT Broker Connection %s', str(rc))

            logger.info("Clearing discovery (inputs/outputs/flags)")
            self.clear_input_discovery()
            self.clear_output_discovery()
            self.clear_flag_discovery()
            self.clear_counter_discovery()
            self.clear_sensor_discovery()
            self.clear_timer_discovery()
            self.clear_battery_voltage_discovery()

            time.sleep(0.25)    # Short wait for MQTT to be ready to accept commands.

            # You need to subscribe to your own topics to enable publish messages activating Comfort entities.
            self.subscribe(settings.ALARMCOMMANDTOPIC)
            self.subscribe(settings.REFRESHTOPIC)
            self.subscribe(settings.RELOADTOPIC, qos=1)
            self.subscribe(settings.BATTERYREFRESHTOPIC)
            self.subscribe(settings.DOMAIN)
            self.subscribe("homeassistant/status")      # Track Status changes for Home Assistant via MQTT Broker.

            self.subscribe(settings.ALARMLOGCLEARTOPIC)


            for i in range(1, ALARMNUMBEROFOUTPUTS + 1):
                self.subscribe(settings.ALARMOUTPUTCOMMANDTOPIC % i)
            
            if ALARMNUMBEROFOUTPUTS > 0:
                logger.debug("Subscribed to %d Zone Outputs", ALARMNUMBEROFOUTPUTS)
            else:
                logger.debug("Not Subscribed to any Zone Outputs")

            for i in ALARMVIRTUALINPUTRANGE: #for virtual inputs #inputs+1 to 128
                self.subscribe(settings.ALARMINPUTCOMMANDTOPIC % i)

            logger.debug("Subscribed to %d Zone Inputs", ALARMVIRTUALINPUTRANGE[-1])

            for i in range(1, settings.ALARMNUMBEROFFLAGS + 1):
                if i >= 255:
                    break
                self.subscribe(settings.ALARMFLAGCOMMANDTOPIC % i)
            logger.debug("Subscribed to %d Flags", settings.ALARMNUMBEROFFLAGS)
                
                ## Sensors ##
            for i in range(0, settings.ALARMNUMBEROFSENSORS):
                self.subscribe(settings.ALARMSENSORCOMMANDTOPIC % i)
            logger.debug("Subscribed to %d Sensors", settings.ALARMNUMBEROFSENSORS)

            for i in range(0, settings.ALARMNUMBEROFCOUNTERS + 1):
                self.subscribe(settings.ALARMCOUNTERCOMMANDTOPIC % i)    # Value or Level
            logger.debug("Subscribed to %d Counters", settings.ALARMNUMBEROFCOUNTERS)

            for i in range(1, ALARMNUMBEROFRESPONSES + 1):      # Responses as specified from HA options.
                self.subscribe(settings.ALARMRESPONSECOMMANDTOPIC % i)
            if ALARMNUMBEROFRESPONSES > 0:
                logger.debug("Subscribed to %d Responses", ALARMNUMBEROFRESPONSES)
            else:
                logger.debug("Not Subscribed to any Responses")

            if settings.FIRST_LOGIN == True:
                logger.debug("Synchronizing Comfort Data...")
                self.readcurrentstate()
                logger.debug("Synchronization Done.")
            
            # Publish zone names/zonewords from CCLX as retained metadata
            self.publish_all_maps()  

            self.alarm_log = RollingMqttLog(self, settings.ALARMLOGTOPIC, max_lines=80)
            # CLear any old data and start the log with a fresh entry for the new connection.
            self.publish(
                settings.ALARMLOGTOPIC,
                '{"state":"starting","log":""}',
                qos=1,
                retain=True
            )
            # self.alarm_log.add("Addon Started, MQTT Broker Connected.", level="INFO")
            # logger.warning("BOOT: calling initial reload")
            # self._handle_reload_request(source="startup", reason="boot")
            # logger.warning("BOOT: initial reload complete")

        else:
            logger.error('MQTT Broker Connection Failed (%s)', str(rc))
            settings.BROKERCONNECTED = False
            settings.device_properties['BridgeConnected'] = 0

    def on_disconnect(self, client, userdata, flags, reasonCode, properties):  #client, userdata, flags, reason_code, properties
        if reasonCode == 0:
            logger.info('MQTT Broker Disconnect Successfull (%s)', str(reasonCode))
        else:
            settings.BROKERCONNECTED = False
            settings.device_properties['BridgeConnected'] = 0
            logger.error('MQTT Broker Connection Failed (%s). Check Network or MQTT Broker connection settings', str(reasonCode))
            settings.FIRST_LOGIN = True

    # The callback for when a PUBLISH message is received from the server.
    # Converted to use serial comms - send commands to Comfort via uart.
    def on_message(self, client, userdata, msg):    #=0
        payload_raw = (msg.payload or b"").decode("utf-8", errors="replace").strip()

        # Default behaviour for non-alarm topics:
        msgstr = payload_raw
        pin_entered = ""

        # Only parse "COMMAND [PIN]" on the alarm command topic
        if msg.topic == settings.ALARMCOMMANDTOPIC:
            logger.debug("cmd is %s", payload_raw)
            parts = payload_raw.split(maxsplit=1)
            msgstr = (parts[0] if parts else "").strip().upper()
            pin_entered = (parts[1] if len(parts) > 1 else "").strip()

            # Only log PIN when it's actually a DISARM command
            if msgstr == "DISARM" and pin_entered:
                logger.debug("PIN entered in command: %s", pin_entered)

        if msg.topic == settings.ALARMLOGCLEARTOPIC:
            logger.debug("In ALARMLOGCLEARTOPIC topic is %s",msg.topic )
            if hasattr(self, "alarm_log"):
                logger.debug("Calling self.alarm_log.clear")
                self.alarm_log.clear(note="Log cleared by user")
            return

        if msg.topic == settings.RELOADTOPIC:
            logger.info("In RELOADTOPIC, topic is %s",msg.topic )
            self._on_reload_message(msg)
            return


        if msg.topic == settings.ALARMCOMMANDTOPIC:    
            logger.debug("In ALARMCOMMANDTOPIC topic is %s",msg.topic )
            if hasattr(self, "alarm_log"):
                self.alarm_log.add(f"{msgstr}", level="CMD")
                if msgstr in ("ARM_AWAY", "ARM_HOME", "ARM_NIGHT", "ARM_VACATION", "REM_ARM_AWAY"):
                   self.alarm_log.add("Arm requested — checking zones (if any are open, Comfort will report them).", level="INFO")

            if self.connected:

                if msgstr == "ARM_VACATION":
                    # self.serial.write(("\x03m!04"+self.comfort_pincode+"\r").encode()) #Local arm to 04 vacation mode. Requires # for open zones
                    self.serial.write(("\x03m!04"+self.comfort_pincode+"\r").encode()) #Local arm to 04 vacation mode. Requires # for open zones
                    settings.SAVEDTIME = datetime.now()
                    self.publish(settings.ALARMSTATETOPIC, "arming",qos=2,retain=False)
                elif msgstr == "ARM_HOME":
                    self.serial.write(("\x03m!03"+self.comfort_pincode+"\r").encode()) #Local arm to 03 day mode. Requires # for open zones
                    settings.SAVEDTIME = datetime.now()
                    self.publish(settings.ALARMSTATETOPIC, "arming",qos=2,retain=False)
                elif msgstr == "ARM_NIGHT":
                    self.serial.write(("\x03m!02"+self.comfort_pincode+"\r").encode()) #Local arm to 02 night mode. Requires # for open zones
                    settings.SAVEDTIME = datetime.now()
                    self.publish(settings.ALARMSTATETOPIC, "arming",qos=2,retain=False)
                elif msgstr == "ARM_AWAY":
                    self.serial.write(("\x03m!01"+self.comfort_pincode+"\r").encode()) #Local arm to 01 away mode. Requires # for open zones + Exit door
                    settings.SAVEDTIME = datetime.now()
                    self.publish(settings.ALARMSTATETOPIC, "arming",qos=2,retain=False)
                elif msgstr == "REM_ARM_AWAY":
                    self.serial.write(("\x03M!01"+self.comfort_pincode+"\r").encode()) #Remote arm to 01 away mode. Requires # for open zones
                    settings.SAVEDTIME = datetime.now()
                    self.publish(settings.ALARMSTATETOPIC, "arming",qos=2,retain=False)
                elif msgstr == "ARM_CUSTOM_BYPASS":
                    self.serial.write("\x03KD1A\r".encode())                           #Send '#' key code (KD1A)
                    settings.SAVEDTIME = datetime.now()
                elif msgstr == "DISARM":
                    expected_pin = (self.comfort_pincode or "").strip()

                    # Require PIN entry from UI
                    if not pin_entered:
                        logger.warning("Disarm rejected: PIN required")
                        if hasattr(self, "alarm_log"):
                            self.alarm_log.add("Disarm rejected: PIN required", level="WARN")
                        # Optional: publish a message topic you already have
                        # self.publish(settings.ALARMMESSAGETOPIC, "PIN required", qos=2, retain=False)
                        return

                    if pin_entered != expected_pin:
                        logger.warning("Disarm rejected: invalid PIN")
                        if hasattr(self, "alarm_log"):
                            self.alarm_log.add("Disarm rejected: invalid PIN", level="WARN")
                        # Optional:
                        # self.publish(settings.ALARMMESSAGETOPIC, "Invalid PIN", qos=2, retain=False)
                        return

                    # OK: disarm (you can use expected_pin or pin_entered; expected_pin is fine)
                    self.serial.write(("\x03m!00" + expected_pin + "\r").encode())
                    settings.SAVEDTIME = datetime.now()
                    self.publish(settings.ALARMSTATETOPIC, "disarming", qos=2, retain=False)

        elif msg.topic.startswith(settings.DOMAIN) and msg.topic.endswith("/refresh"):
            if msgstr == settings.COMFORT_KEY:
                logger.info("Valid Refresh AUTH key detected, initiating MQTT refresh...")
                if settings.COMFORT_CCLX_FILE != None:
                    config_filename = self.sanitize_filename(settings.COMFORT_CCLX_FILE,'cclx')
                    if config_filename:
                        self.add_descriptions(Path("/config/" + config_filename))
                self.readcurrentstate()
        
        elif msg.topic.startswith(settings.DOMAIN) and msg.topic.endswith("/battery_update"):
            logger.debug("Battery update MQTT received: topic=%s payload=%r", msg.topic, msg.payload)

            Devices = ['0','1']        # Mainboard + Installed Slaves EG. ['0', '1','33','34','35' ti '39'].
            for device in range(0, int(settings.device_properties['sem_id'])):
                Devices.append(str(device + 33))    # First Slave at address 33 DEC.

            msgstr_cleaned = msgstr.strip('"')
            if msgstr_cleaned in Devices and (str(settings.device_properties['CPUType']) == 'ARM' or str(settings.device_properties['CPUType']) == 'Toshiba'):
                
                ID = str(f"{int(msgstr_cleaned):02X}")

                #logger.info("msgstr: %s", msgstr.strip('"'))
                #logger.info("msgstr type: %s", type(msgstr.strip('"')))

                #logger.info("ID: %s", ID)
                if msgstr_cleaned == '0':
                    Command = "\x03D?0000\r"
                    self.serial.write(Command.encode()) # Battery and DC Supply Status Update
                else:
                    Command = "\x03D?" + ID + "01\r"
                    self.serial.write(Command.encode()) # Battery Status Update
                    time.sleep(0.01)
                    Command = "\x03D?" + ID + "02\r"
                    self.serial.write(Command.encode()) # DC Supply Status Update
                    time.sleep(0.1)
                settings.SAVEDTIME = datetime.now()
            else:
                logger.warning("Unsupported MQTT Battery Update query received for ID: %s.", msgstr_cleaned)
                logger.warning("Valid ID's: [0,1,33-39] with ARM-powered Comfort is required.")

        elif msg.topic.startswith("homeassistant") and msg.topic.endswith("/status"):
            if msgstr == "online":
                logger.info("Home Assistant Status: %s", msgstr)
                if settings.COMFORT_CCLX_FILE != None:
                    config_filename = self.sanitize_filename(settings.COMFORT_CCLX_FILE,'cclx')
                    if config_filename:
                        self.add_descriptions(Path("/config/" + config_filename))
                        self.publish_all_maps()  # cytech26 
                self.readcurrentstate()

            elif msgstr == "offline":
                logger.info("Home Assistant Status: %s", msgstr)

        elif msg.topic.startswith(settings.DOMAIN+"/output") and msg.topic.endswith("/set"):
            output = int(msg.topic.split("/")[1][6:])
            try:
                state = int(msgstr)
            except ValueError:
                logger.debug("Invalid 'output%s/set' value '%s'. Only Integers allowed.", output, msgstr)
                return
            if self.connected:
                if state >= 0 and state < 5:
                    self.serial.write(("\x03O!%02X%02X\r" % (output, state)).encode())
                    settings.SAVEDTIME = datetime.now()
        elif msg.topic.startswith(settings.DOMAIN+"/response") and msg.topic.endswith("/set"):
            response = int(msg.topic.split("/")[1][8:])
            if self.connected:
                if (response in range(1, ALARMNUMBEROFRESPONSES + 1)) and (response in range(256, 1025)):   # Check for  valid response numbers > 255 but less than Max.
                    result = self.DecimalToSigned16(response)                                               # Returns hex value.
                    self.serial.write(("\x03R!%s\r" % result).encode())                              # Response with 16-bit converted hex number
                    settings.SAVEDTIME = datetime.now()
                elif (response in range(1, ALARMNUMBEROFRESPONSES + 1)) and (response in range(1, 256)):    # Check for 8-bit values
                    self.serial.write(("\x03R!%02X\r" % response).encode())                          # Response with 8-bit number
                    settings.SAVEDTIME = datetime.now()
                logger.debug("Activating Response %d",response )
        elif msg.topic.startswith(settings.DOMAIN+"/input") and msg.topic.endswith("/set"):                          # Can only set the State, the Bypass, Name and Time cannot be changed.
            virtualinput = int(msg.topic.split("/")[1][5:])
            try:
                state = int(msgstr)
            except ValueError:
                logger.debug("Invalid 'input%s/set' value '%s'. Only Integers allowed.", virtualinput, msgstr)
                return
            if self.connected:
                self.serial.write(("\x03I!%02X%02X\r" % (virtualinput, state)).encode())
                settings.SAVEDTIME = datetime.now()
        elif msg.topic.startswith(settings.DOMAIN+"/flag") and msg.topic.endswith("/set"):
            flag = int(msg.topic.split("/")[1][4:])
            try:
                state = int(msgstr)
            except ValueError:
                logger.debug("Invalid 'flag%s/set' value '%s'. Only Integers allowed.", flag, msgstr)
                return
            if self.connected:
                self.serial.write(("\x03F!%02X%02X\r" % (flag, state)).encode()) #was F!
                settings.SAVEDTIME = datetime.now()
        elif msg.topic.startswith(settings.DOMAIN + "/counter") and msg.topic.endswith("/set"):  # counter set
            try:
                counter = int(msg.topic.split("/")[1][7:])
            except (IndexError, ValueError):
                logger.warning("Invalid counter topic: %s", msg.topic)
                return

            if msgstr == "ON":
                state = 255
            elif msgstr == "OFF":
                state = 0
            else:
                try:
                    state = int(msgstr)
                except ValueError:
                    logger.debug(
                        "Invalid Counter%s Set value detected ('%s'), only 'ON', 'OFF' and Integer values allowed",
                        str(counter), str(msgstr)
                    )
                    return

            if state < -32768 or state > 32767:
                logger.debug(
                    "Invalid Counter%s Set value detected ('%s'), only signed 16-bit values allowed",
                    str(counter), str(state)
                )
                return

            self.queue_counter_update(counter, state)

        elif msg.topic.startswith(settings.DOMAIN + "/sensor") and msg.topic.endswith("/set"):  # sensor set
            try:
                sensor = int(msg.topic.split("/")[1][6:])
            except (IndexError, ValueError):
                logger.warning("Invalid sensor topic: %s", msg.topic)
                return

            try:
                state = int(msgstr)
            except ValueError:
                logger.debug("Invalid 'sensor%s/set' value '%s'. Only Integers allowed.", sensor, msgstr)
                return

            if state < -32768 or state > 32767:
                logger.debug("Invalid 'sensor%s/set' value '%s'. Only signed 16-bit Integers allowed.", sensor, msgstr)
                return

            self.queue_sensor_update(sensor, state)
 
  
    def queue_counter_update(self, counter: int, value: int) -> None:
        """Queue a counter write and debounce rapid updates."""
        with self.update_lock:
            current = self.pending_counter_updates.get(counter)
            if current == value:
                logger.info("Counter %d update already pending with value %d", counter, value)
                return

            self.pending_counter_updates[counter] = value

            existing = self.counter_timers.get(counter)
            if existing is not None:
                existing.cancel()

            timer = threading.Timer(0.5, self.flush_counter_update, args=[counter])
            timer.daemon = True
            self.counter_timers[counter] = timer
            timer.start()

        logger.info("Queued counter %d update to %d", counter, value)

    def queue_sensor_update(self, sensor: int, value: int) -> None:
        """Queue a sensor write and debounce rapid updates."""
        with self.update_lock:
            current = self.pending_sensor_updates.get(sensor)
            if current == value:
                logger.info("Sensor %d update already pending with value %d", sensor, value)
                return

            self.pending_sensor_updates[sensor] = value

            existing = self.sensor_timers.get(sensor)
            if existing is not None:
                existing.cancel()

            timer = threading.Timer(0.5, self.flush_sensor_update, args=[sensor])
            timer.daemon = True
            self.sensor_timers[sensor] = timer
            timer.start()

        logger.info("Queued sensor %d update to %d", sensor, value)

    def flush_counter_update(self, counter: int) -> None:
        """Send the final debounced counter value to Comfort."""
        with self.update_lock:
            value = self.pending_counter_updates.pop(counter, None)
            self.counter_timers.pop(counter, None)

        if value is None:
            return

        logger.info("Flushing counter %d update to %d", counter, value)

        try:
            self.set_counter(counter, value)
        except Exception as e:
            logger.exception("Failed to set counter %d to %d: %s", counter, value, e)

    def flush_sensor_update(self, sensor: int) -> None:
        """Send the final debounced sensor value to Comfort."""
        with self.update_lock:
            value = self.pending_sensor_updates.pop(sensor, None)
            self.sensor_timers.pop(sensor, None)

        if value is None:
            return

        logger.info("Flushing sensor %d update to %d", sensor, value)

        try:
            self.set_sensor(sensor, value)
        except Exception as e:
            logger.exception("Failed to set sensor %d to %d: %s", sensor, value, e)

    def cancel_pending_updates(self) -> None:
        """Cancel all pending debounced writes."""
        with self.update_lock:
            for timer in self.counter_timers.values():
                try:
                    timer.cancel()
                except Exception:
                    pass

            for timer in self.sensor_timers.values():
                try:
                    timer.cancel()
                except Exception:
                    pass

            self.counter_timers.clear()
            self.sensor_timers.clear()
            self.pending_counter_updates.clear()
            self.pending_sensor_updates.clear()

        logger.info("Cancelled all pending counter/sensor updates")

    def set_counter(self, counter: int, value: int) -> None:
        """Write a counter value to Comfort."""
        if value < -32768 or value > 32767:
            logger.debug("Invalid Counter%s Set value detected ('%s'), only signed 16-bit values allowed", str(counter), str(value))
            return

        if self.connected:
            self.serial.write(("\x03C!%02X%s\r" % (counter, self.DecimalToSigned16(value))).encode())
            settings.SAVEDTIME = datetime.now()
            logger.info("Sent counter %d = %d to Comfort", counter, value)
        else:
            logger.warning("Counter %d update ignored because Comfort is not connected", counter)

    def set_sensor(self, sensor: int, value: int) -> None:
        """Write a sensor value to Comfort."""
        if value < -32768 or value > 32767:
            logger.debug("Invalid sensor%s Set value detected ('%s'), only signed 16-bit values allowed", str(sensor), str(value))
            return

        if self.connected:
            self.serial.write(("\x03s!%02X%s\r" % (sensor, self.DecimalToSigned16(value))).encode())
            settings.SAVEDTIME = datetime.now()
            logger.info("Sent sensor %d = %d to Comfort", sensor, value)
        else:
            logger.warning("Sensor %d update ignored because Comfort is not connected", sensor)


    def DecimalToSigned16(self,value):      # Returns Comfort corrected HEX string value from signed 16-bit decimal value.
        return ('{:04X}'.format((int((value & 0xff) * 0x100 + (value & 0xff00) / 0x100))) )
    
    def CheckZoneNameFormat(self,value):      # Checks CSV file Zone Name to only contain valid characters. Return False if it fails else True
        pattern = r'^(?![ ]{1,}).{1}[a-zA-Z0-9_ -/]+$'
        return bool(re.match(pattern, value))
    
    def CheckIndexNumberFormat(self,value,max_index = 1024):      # Checks CSV file Zone Number to only contain valid characters. Return False if it fails else True
        pattern = r'^[0-9]+$'
        if bool(re.match(pattern, value)):
            if value.isnumeric() & (int(value) <= max_index):
                return True
            else:
                return False
        else:
            return False
    
    def HexToSigned16Decimal(self,value):        # Returns Signed Decimal value from HEX string EG. FFFF = -1
        return -(int(value,16) & 0x8000) | (int(value,16) & 0x7fff)

    def byte_swap_16_bit(self, hex_string):
        # Ensure the string is prefixed with '0x' for hex conversion
        if not hex_string.startswith('0x'):
            hex_string = '0x' + hex_string
    
        # Convert hex string to integer
        value = int(hex_string, 16)
        # Perform byte swapping
        swapped_value = ((value << 8) & 0xFF00) | ((value >> 8) & 0x00FF)
        # Convert back to hex string and return
        return hex(swapped_value)[2:].upper().zfill(4)

    def on_publish(self, client, obj, mid, reason_codes, properties):
        pass

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        for sub_result in reason_codes:
            if sub_result == 1:
                pass
            if sub_result >= 128:
                logger.debug("Error processing subscribe message")

    def on_log(self, client, userdata, level, buf):
        pass

    def entryexit_timer(self):
        self.publish(settings.ALARMTIMERTOPIC, self.entryexitdelay,qos=2,retain=True)
        self.entryexitdelay -= 1
        if self.entryexitdelay >= 0:
            threading.Timer(1, self.entryexit_timer).start()

    def publish_alarm_message(self, text, *, retain=True, qos=2, also_log=True):
        self.publish(settings.ALARMMESSAGETOPIC, text, qos=qos, retain=retain)
        if also_log and hasattr(self, "alarm_log"):
            self.alarm_log.add(text, level="MSG")

   
    def readlines(self, delim=b'\r'):
        """
        Read CR-terminated lines from the Comfort serial port.

        This is lower latency than read(recv_buffer) because it returns as soon
        as a full Comfort message ending in CR is received, instead of waiting
        for a large buffer or a long timeout.
        """

        while True:
            try:
                # Read one complete Comfort message, ending at CR
                raw = self.serial.read_until(delim)

            except serial.SerialException as e:
                logger.error("Serial read error from Comfort: %s", e)
                settings.COMFORTCONNECTED = False
                settings.FIRST_LOGIN = True
                raise

            # Serial timeout with no data
            if not raw:
                continue

            try:
                line = raw.decode(errors="ignore").strip()
            except Exception:
                continue

            if not line:
                continue

            settings.COMFORTCONNECTED = True
            settings.SAVEDTIME = datetime.now()

            yield line



    def SendCommand(self, command):

        try:
            self.serial.write(("\x03"+command+"\r").encode())
            #self.serial.write((command).encode())
            settings.SAVEDTIME = datetime.now()
            #logger.debug("Sending Command %s", command)    # Debug sent command to Comfort.
        except:
            logger.error("Error sending command '%s', closing socket.", command)
            self.comfortsock.close()
            raise


    def login(self):

        masked = "*" * len(self.comfort_pincode)
        logger.info("Sending Comfort login LI%s", masked)

        self.serial.write(("\x03LI"+self.comfort_pincode+"\r").encode())
        settings.COMFORTCONNECTED = True
        if settings.BROKERCONNECTED:         # Check to see if Broker is connected. Is not always at this point in the startup.
            self.publish(settings.ALARMCONNECTEDTOPIC, 1, qos=2, retain=True)
        settings.SAVEDTIME = datetime.now()




    def readcurrentstate(self):
 
        logger.info("In readcurrentstate connected = %d", self.connected)
        if self.connected == True:

            settings.device_properties['BatteryVoltageMain'] = "-1"
            settings.device_properties['BatteryVoltageSlave1'] = "-1"
            settings.device_properties['BatteryVoltageSlave2'] = "-1"
            settings.device_properties['BatteryVoltageSlave3'] = "-1"
            settings.device_properties['BatteryVoltageSlave4'] = "-1"
            settings.device_properties['BatteryVoltageSlave5'] = "-1"
            settings.device_properties['BatteryVoltageSlave6'] = "-1"
            settings.device_properties['BatteryVoltageSlave7'] = "-1"
            settings.device_properties['ChargeVoltageMain'] = "-1"
            settings.device_properties['ChargeVoltageSlave1'] = "-1"
            settings.device_properties['ChargeVoltageSlave2'] = "-1"
            settings.device_properties['ChargeVoltageSlave3'] = "-1"
            settings.device_properties['ChargeVoltageSlave4'] = "-1"
            settings.device_properties['ChargeVoltageSlave5'] = "-1"
            settings.device_properties['ChargeVoltageSlave6'] = "-1"
            settings.device_properties['ChargeVoltageSlave7'] = "-1"
            settings.device_properties['ChargerStatus'] = "N/A"
            settings.device_properties['BatteryStatus'] = "N/A"


            settings.device_properties['CPUType'] = 'N/A'                  # Reset CPU type to default

            #get Bypassed Zones
            logger.info("Requesting Bypassed Zones")
            self.serial.write("\x03b?00\r".encode())       # b?00 Bypassed Zones first
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)
            
            #get Comfort FileSystem
            self.serial.write("\x03V?\r".encode())
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)
            
            #get CPU Type
            self.serial.write("\x03u?01\r".encode())         # Get CPU type for Main board.
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)

            # Get the battery and DC supply status for main board
            self.serial.write("\x03D?0000\r".encode())       # Mainboard Battery and DC Supply Status
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)

            # Get battery and DC supply status for installed SEM boards
            try:
                installed_slaves = int(settings.device_properties.get("sem_id", 0))
            except Exception:
                installed_slaves = 0

            installed_slaves = max(0, min(installed_slaves, 7))

            logger.info("Requesting battery/DC voltages for %d installed SEM boards", installed_slaves)

            for sem in range(1, installed_slaves + 1):
                sem_address_dec = sem + 32          # SEM1=33, SEM2=34 ... SEM7=39
                sem_address_hex = f"{sem_address_dec:02X}"

                # Battery voltage/status
                self.serial.write((f"\x03D?{sem_address_hex}01\r").encode())
                settings.SAVEDTIME = datetime.now()
                logger.info("Requested SEM %d battery status using D?%s01", sem, sem_address_hex)
                time.sleep(0.01)

                # DC supply voltage/status
                self.serial.write((f"\x03D?{sem_address_hex}02\r").encode())
                settings.SAVEDTIME = datetime.now()
                logger.info("Requested SEM %d DC supply status using D?%s02", sem, sem_address_hex)
                time.sleep(0.01)

                      
            #get HW model
            self.serial.write("\x03EL\r".encode())
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)

            #Used for Unique ID
            self.serial.write("\x03UL7FF904\r".encode())
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)
            
            #get Mainboard Serial Number
            self.serial.write("\x03SN01\r".encode())
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)
            
            self.serial.write("\x03M?\r".encode())
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)
            # #get all zone input states
            self.serial.write("\x03Z?\r".encode())       # Comfort Zones/Inputs
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)

            #get all output states
            if ALARMNUMBEROFOUTPUTS > 0:
                self.serial.write("\x03Y?\r".encode())
                settings.SAVEDTIME = datetime.now()
                time.sleep(0.01)

            #get all flag states
            self.serial.write("\x03f?00\r".encode())
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)
            #get Alarm Status Information
            self.serial.write("\x03S?\r".encode())       # S? Status Request
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)
            #get Alarm Additional Information
            self.serial.write("\x03a?\r".encode())       # a? Status Request - For Future Use !!!
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)

            #get all sensor values. 0 - 31
            self.serial.write("\x03r?010010\r".encode())
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)
            self.serial.write("\x03r?011010\r".encode())
            settings.SAVEDTIME = datetime.now()
            time.sleep(0.01)

            #get all counter values
            for i in range(0, int((settings.ALARMNUMBEROFCOUNTERS+1) / 16)):          # Counters 0 to 254 Using 256/16 = 16 iterations
                if i == 15:
                    self.serial.write("\x03r?00%X00F\r".encode() % (i))
                else:
                    self.serial.write("\x03r?00%X010\r".encode() % (i))
                settings.SAVEDTIME = datetime.now()
                time.sleep(0.1)
            
            self.publish(settings.ALARMAVAILABLETOPIC, 1,qos=2,retain=True)
            time.sleep(0.01)
            self.publish(settings.ALARMLWTTOPIC, 'Online',qos=2,retain=True)
            time.sleep(0.01)
            self.publish(settings.ALARMMESSAGETOPIC, "",qos=2,retain=True)       # Empty string removes topic.
            time.sleep(0.01)



            if settings.BROKERCONNECTED and settings.COMFORTCONNECTED:
                self.publish(settings.ALARMCONNECTEDTOPIC, 1,qos=2,retain=True)
                time.sleep(0.01)


    def UpdateBatteryStatus(self):

        discoverytopic = settings.DOMAIN + "/alarm/battery_status"
        MQTT_MSG=json.dumps({"BatteryStatus": str(settings.device_properties['BatteryStatus']),
                             "DCSupplyStatus": str(settings.device_properties['ChargerStatus']),
                             "BatteryMain": str(settings.device_properties['BatteryVoltageMain']),
                             "BatterySlave1": str(settings.device_properties['BatteryVoltageSlave1']),
                             "BatterySlave2": str(settings.device_properties['BatteryVoltageSlave2']),
                             "BatterySlave3": str(settings.device_properties['BatteryVoltageSlave3']),
                             "BatterySlave4": str(settings.device_properties['BatteryVoltageSlave4']),
                             "BatterySlave5": str(settings.device_properties['BatteryVoltageSlave5']),
                             "BatterySlave6": str(settings.device_properties['BatteryVoltageSlave6']),
                             "BatterySlave7": str(settings.device_properties['BatteryVoltageSlave7']),
                             "DCSupplyMain": str(settings.device_properties['ChargeVoltageMain']),
                             "DCSupplySlave1": str(settings.device_properties['ChargeVoltageSlave1']),
                             "DCSupplySlave2": str(settings.device_properties['ChargeVoltageSlave2']),
                             "DCSupplySlave3": str(settings.device_properties['ChargeVoltageSlave3']),
                             "DCSupplySlave4": str(settings.device_properties['ChargeVoltageSlave4']),
                             "DCSupplySlave5": str(settings.device_properties['ChargeVoltageSlave5']),
                             "DCSupplySlave6": str(settings.device_properties['ChargeVoltageSlave6']),
                             "DCSupplySlave7": str(settings.device_properties['ChargeVoltageSlave7']),
                             "InstalledSlaves": int(settings.device_properties['sem_id'])
                            })
        logging.debug("Battery status publish: %s", MQTT_MSG)
        self.publish(discoverytopic, MQTT_MSG,qos=2,retain=False)
        time.sleep(0.1)

        self.PublishBatteryVoltageStates() # publish the voltages as individual topics for easier use in HA without needing to parse JSON.

    def UpdateDeviceInfo(self, _file = False):

        #option = parser.parse_args()
        #COMFORT_BATTERY_STATUS_ID=option.comfort_battery_update
        global MQTT_DEVICE_COMFORT
        
        file_exists = _file
  
        if ADDON_SLUG.strip() == "":
            MQTT_DEVICE = { "name": "Cytech Comfort MQTT",
                            "identifiers": ["cytech_comfort_mqtt"],
                            "manufacturer": "Cytech Technology Pte Ltd",
                            "sw_version": ADDON_VERSION,
                            "hw_version": "Comfort Panel",
                            "model": "Comfort"
                          }
        else:
            MQTT_DEVICE = { "name": "Cytech Comfort MQTT",
                            "identifiers": ["cytech_comfort_mqtt"],
                            "manufacturer": "Cytech Technology Pte Ltd",
                            "sw_version": ADDON_VERSION,
                            "hw_version": "Comfort Panel",
                            "configuration_url": "homeassistant://hassio/addon/" + ADDON_SLUG + "/info",
                            "model": "Comfort"
                        }
        
        MQTT_MSG=json.dumps({"CustomerName": settings.device_properties['CustomerName'] if file_exists else None,
                             "support_url": "https://www.cytech.biz",
                             "Reference": settings.device_properties['Reference'] if file_exists else None,
                             "ComfortFileSystem": settings.device_properties['ComfortFileSystem'] if file_exists else None,
                             "ComfortFirmwareType": settings.device_properties['ComfortFirmwareType'] if file_exists else None,
                             "sw_version":str(settings.device_properties['Version']),
                             "hw_version":str(settings.device_properties['ComfortHardwareModel']),
                             "serial_number": settings.device_properties['SerialNumber'],
                             "cpu_type": str(settings.device_properties['CPUType']),
                             "InstalledSlaves": int(settings.device_properties['sem_id']),
                             "model": settings.models[int(settings.device_properties['ComfortFileSystem'])] if int(settings.device_properties['ComfortFileSystem']) in settings.models else "Unknown",
                             "BridgeConnected": str(settings.device_properties['BridgeConnected']),
                             "device": MQTT_DEVICE
                            })

        self.publish(settings.DOMAIN, MQTT_MSG,qos=2,retain=True)
        time.sleep(0.1)


        discoverytopic = f"homeassistant/binary_sensor/{settings.DOMAIN}/bridge_status/config"
        MQTT_MSG=json.dumps({"name": "Bridge MQTT Status",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "binary_sensor."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "state_topic": settings.DOMAIN,
                             "value_template": "{{ value_json.BridgeConnected }}",
                             "qos": "2",
                             "device_class": "connectivity",
                             "payload_on": "1",
                             "payload_off": "0",
                             "device": MQTT_DEVICE
                            })
        self.publish(discoverytopic, MQTT_MSG, qos=2, retain=True)
        time.sleep(0.1)

        availability =  [
             {
                 "topic": settings.ALARMAVAILABLETOPIC,
                 "payload_available": "1",
                 "payload_not_available": "0"
             },
             {
                 "topic": settings.DOMAIN,
                 "payload_available": "1",
                 "payload_not_available": "0",
                 "value_template": "{{ value_json.BridgeConnected }}"
             }
            ]
        discoverytopic = f"homeassistant/button/{settings.DOMAIN}/refresh/config"
        MQTT_MSG=json.dumps({"name": "Refresh",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "button."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "availability": availability,
                             "availability_mode": "all",
                             "command_topic": settings.REFRESHTOPIC,
                             "payload_available": "1",
                             "payload_not_available": "0",
                             "payload_press": settings.COMFORT_KEY,
                             "icon":"mdi:refresh",
                             "qos": "2",
                             "device": MQTT_DEVICE
                            })
        self.publish(discoverytopic, MQTT_MSG, qos=2, retain=False)
        time.sleep(0.1)
        
        discoverytopic = f"homeassistant/button/{settings.DOMAIN}/battery_update/config"
        MQTT_MSG=json.dumps({"name": "Battery Update",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "button."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "availability": availability,
                             "availability_mode": "all",
                             "command_topic": settings.BATTERYREFRESHTOPIC,
                             "payload_available": "1",
                             "payload_not_available": "0",
                             "payload_press": str(settings.COMFORT_BATTERY_STATUS_ID),
                             "icon":"mdi:battery-sync-outline",
                             "qos": "2",
                             "device": MQTT_DEVICE
                            })
        if settings.device_properties['CPUType'] != "N/A":
            self.publish(discoverytopic, MQTT_MSG, qos=2, retain=False)
            time.sleep(0.1)
     
        MQTT_DEVICE = {
                        "name": "Comfort",  # Short, clean device name
                        "identifiers": ["comfort_device"],
                        "manufacturer": "Cytech Technology Pte Ltd",
                        "hw_version": str(settings.device_properties['ComfortHardwareModel']),
                        "serial_number": settings.device_properties['SerialNumber'],
                        "sw_version": str(settings.device_properties['Version']),

                        # Use the readable model name instead of numeric hardware model
                        "model": settings.models[int(settings.device_properties['ComfortFileSystem'])]
                            if int(settings.device_properties['ComfortFileSystem']) in settings.models
                            else "Unknown",

                        "via_device": "cytech_comfort_mqtt"
                        }
     
     
        # Store the Comfort device dict for reload/discovery republish
        MQTT_DEVICE_COMFORT = MQTT_DEVICE

        self.MQTT_DEVICE_COMFORT = MQTT_DEVICE
        
        # Publish Input discovery entities under the Comfort device  # Cytech26
        if not getattr(self, "_inputs_discovery_published", False):
            self.publish_input_discovery(MQTT_DEVICE_COMFORT)
            self._inputs_discovery_published = True

        # Publish Output discovery entities under the Comfort device
        if not getattr(self, "_outputs_discovery_published", False):
            self.publish_output_discovery(MQTT_DEVICE_COMFORT)
            self._outputs_discovery_published = True

        # Publish Flag discovery entities under the Comfort device
        if not getattr(self, "_flags_discovery_published", False):
            self.publish_flag_discovery(MQTT_DEVICE_COMFORT)
            self._flags_discovery_published = True

        # Publish Counter discovery entities under the Comfort device
        if not getattr(self, "_counters_discovery_published", False):
            self.publish_counter_discovery(MQTT_DEVICE_COMFORT)
            self._counters_discovery_published = True

        # Publish Sensor discovery entities under the Comfort device
        if not getattr(self, "_sensors_discovery_published", False):
            self.publish_sensor_discovery(MQTT_DEVICE_COMFORT)
            self._sensors_discovery_published = True

         # Publish Timer discovery entities under the Comfort device
        if not getattr(self, "_timers_discovery_published", False):
            self.publish_timer_discovery(MQTT_DEVICE_COMFORT)
            self._timers_discovery_published = True

        self.PublishBatteryVoltageDiscovery()

        discoverytopic = f"homeassistant/sensor/{settings.DOMAIN}/comfort_state/config"
        MQTT_MSG=json.dumps({"name": "State",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "sensor."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "state_topic": settings.ALARMSTATUSTOPIC,
                             "availability_topic": settings.ALARMAVAILABLETOPIC,
                             "payload_available": "1",
                             "payload_not_available": "0",
                             "icon":"mdi:shield-alert",
                             "qos": "2",
                             "native_value": "string",
                             "device": MQTT_DEVICE
                            })
        self.publish(discoverytopic, MQTT_MSG, qos=2, retain=True)
        time.sleep(0.1)

        discoverytopic = f"homeassistant/sensor/{settings.DOMAIN}/comfort_firmware/config"
        MQTT_MSG=json.dumps({"name": "Firmware",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "sensor."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "availability_topic": settings.ALARMAVAILABLETOPIC,
                             "payload_available": "1",
                             "payload_not_available": "0",
                             "state_topic": settings.DOMAIN,
                             "value_template": "{{ value_json.sw_version }}",
                             "entity_category": "diagnostic",
                             "native_value": "string",
                             "icon":"mdi:chip",
                             "qos": "2",
                             "device": MQTT_DEVICE
                        })
        self.publish(discoverytopic, MQTT_MSG, qos=2, retain=False)
        time.sleep(0.1)

        discoverytopic = f"homeassistant/sensor/{settings.DOMAIN}/comfort_filesystem/config"
        MQTT_MSG=json.dumps({"name": "FileSystem",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "sensor."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "availability_topic": settings.ALARMAVAILABLETOPIC,
                             "payload_available": "1",
                             "payload_not_available": "0",
                             "state_topic": settings.DOMAIN,
                             "value_template": "{{ value_json.ComfortFileSystem }}",
                             "entity_category": "diagnostic",
                             "native_value": "int",
                             "icon":"mdi:file-chart",
                             "qos": "2",
                             "device": MQTT_DEVICE
                        })
        self.publish(discoverytopic, MQTT_MSG, qos=2, retain=False)
        time.sleep(0.1)

        discoverytopic = f"homeassistant/sensor/{settings.DOMAIN}/battery_status/config"
        MQTT_MSG=json.dumps({"name": "Battery/Charger Status",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "sensor."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "availability_topic": settings.ALARMAVAILABLETOPIC,
                             "payload_available": "1",
                             "payload_not_available": "0",
                             "state_topic": settings.DOMAIN+"/alarm/battery_status",
                             "value_template": "{{ value_json.BatteryStatus }}",
                             "json_attributes_topic": settings.DOMAIN+"/alarm/battery_status",
                             "json_attributes_template": '''
                                {% set data = value_json %}
                                {% set slaves = data['InstalledSlaves'] %}
                                {% set ns = namespace(dict_items='') %}
                                {% for key, value in data.items() %}
                                    {% if 'BatteryMain' in key or ('BatterySlave' in key and key[-1:] | int <= slaves) %}
                                        {% if ns.dict_items %}
                                            {% set ns.dict_items = ns.dict_items + ', "' ~ key ~ '":"' ~ value ~ '"' %}
                                        {% else %}
                                            {% set ns.dict_items = '"' ~ key ~ '":"' ~ value ~ '"' %}
                                        {% endif %}
                                    {% endif %}
                                {% endfor %}
                                {% set dict_str = '{' ~ ns.dict_items ~ '}' %}
                                {% set result = dict_str | from_json %}
                                {{ result | tojson }}
                                ''',
                             "entity_category": "diagnostic",
                             "icon":"mdi:battery-check",
                             "qos": "2",
                             "device": MQTT_DEVICE
                        })
        if settings.device_properties['CPUType'] != "N/A":
            self.publish(discoverytopic, MQTT_MSG, qos=2, retain=False)
            time.sleep(0.1)

        discoverytopic = f"homeassistant/sensor/{settings.DOMAIN}/charger_status/config"
        MQTT_MSG=json.dumps({"name": "DC Supply Status",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "sensor."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "availability_topic": settings.ALARMAVAILABLETOPIC,
                             "payload_available": "1",
                             "payload_not_available": "0",
                             "state_topic": settings.DOMAIN+"/alarm/battery_status",
                             "value_template": "{{ value_json.DCSupplyStatus }}",
                             "json_attributes_topic": settings.DOMAIN+"/alarm/battery_status",
                             "json_attributes_template": '''
                                {% set data = value_json %}
                                {% set slaves = data['InstalledSlaves'] %}
                                {% set ns = namespace(dict_items='') %}
                                {% for key, value in data.items() %}
                                    {% if 'DCSupplyMain' in key or ('DCSupplySlave' in key and key[-1:] | int <= slaves) %}
                                        {% if ns.dict_items %}
                                            {% set ns.dict_items = ns.dict_items + ', "' ~ key ~ '":"' ~ value ~ '"' %}
                                        {% else %}
                                            {% set ns.dict_items = '"' ~ key ~ '":"' ~ value ~ '"' %}
                                        {% endif %}
                                    {% endif %}
                                {% endfor %}
                                {% set dict_str = '{' ~ ns.dict_items ~ '}' %}
                                {% set result = dict_str | from_json %}
                                {{ result | tojson }}
                                ''',
                             "entity_category": "diagnostic",
                             "icon":"mdi:battery-charging",
                             "qos": "2",
                             "device": MQTT_DEVICE
                        })
        if settings.device_properties['CPUType'] != "N/A":
            self.publish(discoverytopic, MQTT_MSG, qos=2, retain=False)
            time.sleep(0.1)
            #logging.debug(MQTT_MSG)

        discoverytopic = f"homeassistant/sensor/{settings.DOMAIN}/comfort_bypass_zones/config"
        MQTT_MSG=json.dumps({"name": "Bypassed Zones",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "sensor."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "state_topic": settings.ALARMBYPASSTOPIC,
                             "availability_topic": settings.ALARMAVAILABLETOPIC,
                             "payload_available": "1",
                             "payload_not_available": "0",
                             "icon":"mdi:shield-remove",
                             "qos": "2",
                             "native_value": "string",
                             "device": MQTT_DEVICE
                            })
        self.publish(discoverytopic, MQTT_MSG, qos=2, retain=False)
        time.sleep(0.1)

        #Mode_Description = {0:"Disarmed", 1:"Away Mode", 2:"Night Mode", 3:"Day Mode", 4:"Vacation Mode"}
        discoverytopic = f"homeassistant/sensor/{settings.DOMAIN}/comfort_mode/config"
        MQTT_MSG=json.dumps({"name": "Mode",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "sensor."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "availability_topic": settings.ALARMAVAILABLETOPIC,
                             "payload_available": "1",
                             "payload_not_available": "0",
                             "state_topic": settings.ALARMMODETOPIC,
                             "icon":"mdi:home",
                             "device": MQTT_DEVICE
                        })
        self.publish(discoverytopic, MQTT_MSG, qos=2, retain=True)
        time.sleep(0.1)

        discoverytopic = f"homeassistant/sensor/{settings.DOMAIN}/comfort_customername/config"
        MQTT_MSG=json.dumps({"name": "Customer Name",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "sensor."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "availability_topic": settings.ALARMAVAILABLETOPIC,
                             "payload_available": "1",
                             "payload_not_available": "0",
                             "state_topic": settings.DOMAIN,
                             "value_template": "{{ value_json.CustomerName }}",
                             "entity_category": "diagnostic",
                             "native_value": "string",
                             "icon":"mdi:shield-account",
                             "qos": "2",
                             "device": MQTT_DEVICE
                            })
        self.publish(discoverytopic, MQTT_MSG, qos=2, retain=False)
        time.sleep(0.1)

        discoverytopic = f"homeassistant/sensor/{settings.DOMAIN}/comfort_reference/config"
        MQTT_MSG=json.dumps({"name": "Reference",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "sensor."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "availability_topic": settings.ALARMAVAILABLETOPIC,
                             "payload_available": "1",
                             "payload_not_available": "0",
                             "state_topic": settings.DOMAIN,
                             "value_template": "{{ value_json.Reference }}",
                             "entity_category": "diagnostic",
                             "native_value": "string",
                             "icon":"mdi:home-circle",
                             "qos": "2",
                             "device": MQTT_DEVICE
                            })
        self.publish(discoverytopic, MQTT_MSG, qos=2, retain=False)
        time.sleep(0.1)
        
        discoverytopic = f"homeassistant/sensor/{settings.DOMAIN}/comfort_serial_number/config"
        MQTT_MSG=json.dumps({"name": "Serial Number",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "sensor."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "availability_topic": settings.ALARMAVAILABLETOPIC,
                             "payload_available": "1",
                             "payload_not_available": "0",
                             "state_topic": settings.DOMAIN,
                             "value_template": "{{ value_json.serial_number }}",
                             "entity_category": "diagnostic",
                             "native_value": "string",
                             "icon":"mdi:numeric",
                             "qos": "2",
                             "device": MQTT_DEVICE
                            })
        self.publish(discoverytopic, MQTT_MSG, qos=2, retain=False)
        time.sleep(0.1)


        discoverytopic = f"homeassistant/binary_sensor/{settings.DOMAIN}/comfort_connection_state/config"
        MQTT_MSG=json.dumps({"name": "LAN Status",
                             "unique_id": settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "default_entity_id": "sensor."+settings.DOMAIN+"_"+discoverytopic.split('/')[3],
                             "state_topic": settings.ALARMCONNECTEDTOPIC,
                             "device_class": "connectivity",
                             "entity_category": "diagnostic",
                             "payload_off": "0",
                             "payload_on": "1",
                             "qos": "2",
                             "device": MQTT_DEVICE
                            })
        self.publish(discoverytopic, MQTT_MSG, qos=2, retain=True)
        time.sleep(0.1)

    def BatteryStatus(*voltages):  # Tuple of all voltages
        for voltage in voltages:
            if voltage > 15:        # Critical Overcharge
                return "Critical"
            if voltage > 14.6:      # Overcharge
                return "Warning"
            if voltage <= 9.5:     # Discharged/Crital Charge or No Charge
                return "Critical"
            elif voltage < 11.5:   # Severely Discharged/Low Charge
                return "Warning"
        return "Ok"

#        Example usage with 5 battery voltages
#           battery_voltages = [13.0, 12.1, 12.8, 13.5, 14.2]                          # Test
#           print(battery_status(*battery_voltages))  # Output will be "Critical"      # Test
    
    def setdatetime(self):

        if self.connected == True:  #set current date and time if COMFORT_TIME Flag is set to True
            if settings.COMFORT_TIME == 'True':
                logger.info('Setting Comfort Date/Time')
                now = datetime.now()
                self.serial.write(("\x03DT%02d%02d%02d%02d%02d%02d\r" % (now.year, now.month, now.day, now.hour, now.minute, now.second)).encode())
                settings.SAVEDTIME = datetime.now()
                time.sleep(0.1)


    def exit_gracefully(self, signum, frame):
        
        logger.debug("SIGNUM: %s received, Shutting down.", str(signum))
        
        settings.device_properties['BridgeConnected'] = 0
        if self.connected == True:
            self.serial.write("\x03LI\r".encode()) #Logout command.
            settings.SAVEDTIME = datetime.now()
            self.connected = False
        if settings.BROKERCONNECTED == True:      # MQTT Connected
            infot = self.publish(settings.ALARMCONNECTEDTOPIC, 0,qos=2,retain=True)
            infot = self.publish(settings.ALARMAVAILABLETOPIC, 0,qos=2,retain=True)
            infot = self.publish(settings.ALARMLWTTOPIC, 'Offline',qos=2,retain=True)

            if ADDON_SLUG.strip() == "":
                           MQTT_DEVICE = { "name": "Cytech Comfort MQTT",
                            "identifiers": ["cytech_comfort_mqtt"],
                            "manufacturer": "Cytech Technology Pte Ltd",
                            "sw_version": ADDON_VERSION,
                            "hw_version": "Comfort Panel",
                            "model": "Comfort"
                          }
            else:
                          MQTT_DEVICE = { "name": "Cytech Comfort MQTT",
                                          "identifiers": ["cytech_comfort_mqtt"],
                                          "manufacturer": "Cytech Technology Pte Ltd",
                                          "sw_version": ADDON_VERSION,
                                          "hw_version": "Comfort Panel",
                                          "configuration_url": "homeassistant://hassio/addon/" + ADDON_SLUG + "/info",
                                          "model": "Comfort"
                                        }

            MQTT_MSG=json.dumps({"CustomerName": settings.device_properties['CustomerName'] if settings.file_exists else None,
                             "support_url": "https://www.cytech.biz",
                             "Reference": settings.device_properties['Reference'] if settings.file_exists else None,
                             "ComfortFileSystem": settings.device_properties['ComfortFileSystem'] if settings.file_exists else None,
                             "ComfortFirmwareType": settings.device_properties['ComfortFirmwareType'] if settings.file_exists else None,
                             "sw_version":str(settings.device_properties['Version']),
                             "hw_version":str(settings.device_properties['ComfortHardwareModel']),
                             "serial_number": settings.device_properties['SerialNumber'],
                             "cpu_type": str(settings.device_properties['CPUType']),
                             "InstalledSlaves": int(settings.device_properties['sem_id']),
                             "model": settings.models[int(settings.device_properties['ComfortFileSystem'])] if int(settings.device_properties['ComfortFileSystem']) in settings.models else "Unknown",
                             "BridgeConnected": str(settings.device_properties['BridgeConnected']),
                             "device": MQTT_DEVICE
                            })
            infot = self.publish(settings.DOMAIN, MQTT_MSG,qos=2,retain=False)
            infot.wait_for_publish()

            discoverytopic = settings.DOMAIN + "/alarm/battery_status"
            MQTT_MSG=json.dumps({"BatteryStatus": str(settings.device_properties['BatteryStatus']),
                             "DCSupplyStatus": str(settings.device_properties['ChargerStatus']),
                             "BatteryMain": str(settings.device_properties['BatteryVoltageMain']),
                             "BatterySlave1": str(settings.device_properties['BatteryVoltageSlave1']),
                             "BatterySlave2": str(settings.device_properties['BatteryVoltageSlave2']),
                             "BatterySlave3": str(settings.device_properties['BatteryVoltageSlave3']),
                             "BatterySlave4": str(settings.device_properties['BatteryVoltageSlave4']),
                             "BatterySlave5": str(settings.device_properties['BatteryVoltageSlave5']),
                             "BatterySlave6": str(settings.device_properties['BatteryVoltageSlave6']),
                             "BatterySlave7": str(settings.device_properties['BatteryVoltageSlave7']),
                             "DCSupplyMain": str(settings.device_properties['ChargeVoltageMain']),
                             "DCSupplySlave1": str(settings.device_properties['ChargeVoltageSlave1']),
                             "DCSupplySlave2": str(settings.device_properties['ChargeVoltageSlave2']),
                             "DCSupplySlave3": str(settings.device_properties['ChargeVoltageSlave3']),
                             "DCSupplySlave4": str(settings.device_properties['ChargeVoltageSlave4']),
                             "DCSupplySlave5": str(settings.device_properties['ChargeVoltageSlave5']),
                             "DCSupplySlave6": str(settings.device_properties['ChargeVoltageSlave6']),
                             "DCSupplySlave7": str(settings.device_properties['ChargeVoltageSlave7']),
                             "InstalledSlaves": int(settings.device_properties['sem_id'])
                            })
            infot = self.publish(discoverytopic, MQTT_MSG,qos=2,retain=False)
            infot.wait_for_publish()

        settings.RUN = False
        exit(0)


    def add_descriptions(self, file):

        res = parse_cclx(
            file_path=file,
            device_properties_in=settings.device_properties,
            check_zone_name=self.CheckZoneNameFormat,
            check_index_number=self.CheckIndexNumberFormat,
            logger=logger,
            max_outputs=96
        )

        # Copy results back into the globals the rest of the code expects
        settings.device_properties = res.device_properties
        settings.input_properties = res.input_properties
        settings.counter_properties = res.counter_properties
        settings.flag_properties = res.flag_properties
        settings.output_properties = res.output_properties
        settings.sensor_properties = res.sensor_properties
        settings.timer_properties = res.timer_properties
        settings.user_properties = res.user_properties

        settings.DEVICEMAPFILE  = res.flags.devicemap
        settings.ZONEMAPFILE    = res.flags.zonemap
        settings.COUNTERMAPFILE = res.flags.countermap
        settings.FLAGMAPFILE    = res.flags.flagmap
        settings.OUTPUTMAPFILE  = res.flags.outputmap
        settings.SENSORMAPFILE  = res.flags.sensormap
        settings.TIMERMAPFILE   = res.flags.timermap
        settings.USERMAPFILE    = res.flags.usermap

        return file

    
    def sanitize_filename(self, input_string, valid_extensions=None):     # Thanks ChatGPT :-)
        """
        Sanitize the input filename string to ensure it is a valid filename with an extension,
        and prevent directory tree walking.

        :param input_string: The user input string to sanitize.
        :param valid_extensions: List of valid extensions (e.g., ['cclx']). None to allow any extension.
        :return: A sanitized filename or None if invalid.
        """
        # Define a regular expression pattern for a valid filename (alphanumeric and specific special characters)
        valid_filename_pattern = r'^[\w\-. ]+$'  # Alphanumeric characters, underscores, hyphens and dots. Spaces (for future development)
    
        # Split the filename and extension
        base, ext = os.path.splitext(input_string)
    
        # Check if the base name is valid
        if not re.match(valid_filename_pattern, base):
            return None
    
        # Validate the extension if a list of valid extensions is provided
        if valid_extensions:
            ext = ext.lstrip('.').lower()
            if ext not in valid_extensions:
                return None
    
        # Join the base and extension back
        sanitized_filename = f"{base}.{ext}" if ext else base
        #sanitized_filename = f"\"{base}.{ext}\"" if ext else base
    
        # Ensure no directory traversal characters are present
        if '..' in sanitized_filename or '/' in sanitized_filename or '\\' in sanitized_filename:
            return None
    
        #logging.debug("Sanitized Filename: %s", sanitized_filename)
        return sanitized_filename

    def validate_hex_in_list(self, value, allow_spec):
        """
        value      : hex string (2 characters, e.g. '1F')
        allow_spec : either a list of integers OR a string like '0,49-51,255'
        returns    : True if value (as decimal) is in allowed list, else False
        """

        # If allow_spec is a string like "0,49-51,255", parse and expand it
        if isinstance(allow_spec, str):
            allowed = []
            for part in allow_spec.split(","):
                part = part.strip()
                if "-" in part:
                    try:
                        start, end = map(int, part.split("-"))
                        allowed.extend(range(start, end + 1))
                    except ValueError:
                        pass  # ignore malformed ranges
                else:
                    try:
                        allowed.append(int(part))
                    except ValueError:
                        pass  # ignore invalid numbers
        else:
            # Already a list of integers
            allowed = list(allow_spec)

        try:
            dec_value = int(value, 16)
        except ValueError:
            return False  # invalid hex string

        return dec_value in allowed




    def _reset_enrichment(self):
        """
        Clear CCLX-derived metadata so a reload doesn't retain stale names/descriptions.
        Adjust these attribute names to match whatever you use in your code.
        """
        # Common ones you mentioned previously:
        settings.input_properties = {}
        settings.output_properties = {}
        settings.counter_properties = {}
        settings.sensor_properties = {}
        settings.flag_properties = {}
        settings.user_properties = {}
        settings.timer_properties = {}
        # Anything else add_descriptions() populates should be reset here.
        # also clear these CCLX “flags” so publish_input_discovery uses the new file cleanly
        settings.DEVICEMAPFILE  = False
        settings.ZONEMAPFILE    = False
        settings.COUNTERMAPFILE = False
        settings.FLAGMAPFILE    = False
        settings.OUTPUTMAPFILE  = False
        settings.SENSORMAPFILE  = False
        settings.TIMERMAPFILE   = False
        settings.USERMAPFILE    = False


    # def purge_stale_output_discovery(self, start: int = 129, end: int = 255):
    #     """
    #     One-time cleanup: delete retained HA discovery configs for stale outputs.
    #     Call this once after fixing COMFORT_OUTPUTS publishing.
    #     """
    #     dom = settings.DOMAIN
    #     logger.warning("PURGE outputs: domain=%s range=%d..%d", dom, start, end)

    #     deleted = 0
    #     for i in range(start, end + 1):
    #         topic = f"homeassistant/switch/{dom}/output{i}/config"
    #         self.publish(topic, "", qos=1, retain=True)
    #         deleted += 1

    #     logger.warning("PURGE outputs: done deleted=%d", deleted)




    def _on_reload_message(self, msg):
        logger.info("In _on_reload_message payload=%r retain=%r", msg.payload, getattr(msg, "retain", False))

        if getattr(msg, "retain", False):
            logger.info("Reload: ignored retained message")
            return

        now = time.monotonic()
        if (now - self._last_reload_ts) < settings.RELOAD_COOLDOWN_SECONDS:
            logger.warning("Reload: ignored (cooldown)")
            return

        payload_raw = (msg.payload or b"").decode("utf-8", errors="replace").strip()
        logger.info("Reload: received payload=%r", payload_raw)

        reason = None
        key_ok = True

        if payload_raw and payload_raw.lower() != "reload":
            try:
                data = json.loads(payload_raw)
                reason = data.get("reason")
                if settings.RELOAD_REQUIRE_KEY:
                    key_ok = (data.get("key") == getattr(settings, "COMFORT_KEY", None))
            except Exception:
                if settings.RELOAD_REQUIRE_KEY:
                    key_ok = False

        if settings.RELOAD_REQUIRE_KEY and not key_ok:
            logger.warning("Reload: rejected (bad key)")
            return

        # Prevent overlapping reloads (MQTT callback runs in paho thread)
        if not self._reload_lock.acquire(blocking=False):
            logger.warning("Reload: ignored (already in progress)")
            return

        try:
            self._last_reload_ts = now
            logger.warning("Reload: accepted%s", f" reason={reason!r}" if reason else "")
            self._handle_reload_request(source="mqtt", reason=reason)
        except Exception:
            # Never let exceptions kill the paho network thread
            logger.exception("Reload failed in MQTT callback")
        finally:
            self._reload_lock.release()


    def _handle_reload_request(self, source: str = "mqtt", reason: str | None = None):
        logger.warning("Reload requested via source=%s reason=%r", source, reason)

        try:
            logger.info("Clearing discovery (inputs/outputs/flags)")
            self.clear_input_discovery()
            self.clear_output_discovery()
            self.clear_flag_discovery()
            self.clear_counter_discovery()
            self.clear_sensor_discovery()
            self.clear_timer_discovery()
            self.clear_battery_voltage_discovery()



            data_cclx = Path("/data/site.cclx")
            logger.warning("Reload using CCLX path=%s exists=%s", data_cclx, data_cclx.exists())

            if data_cclx.exists():
                self._reset_enrichment()
                self.add_descriptions(data_cclx)
                self.publish_all_maps()

            mqtt_device_comfort = getattr(self, "MQTT_DEVICE_COMFORT", None) or globals().get("MQTT_DEVICE_COMFORT", None)

            if mqtt_device_comfort is not None:
                logger.info("Publishing discovery (inputs/outputs/flags/counters/sensors)")
                self.publish_input_discovery(mqtt_device_comfort)
                self.publish_output_discovery(mqtt_device_comfort)
                self.publish_flag_discovery(mqtt_device_comfort)
                self.publish_counter_discovery(mqtt_device_comfort)
                self.publish_sensor_discovery(mqtt_device_comfort)
                self.publish_timer_discovery(mqtt_device_comfort)
                self.PublishBatteryVoltageDiscovery()
                self.PublishBatteryVoltageStates()
            else:
                logger.warning("MQTT_DEVICE_COMFORT not set yet; skipping discovery publish on reload")

        except Exception:
            logger.exception("Reload failed source=%s reason=%r", source, reason)
            raise


    def clear_input_discovery(self):
        """
        Clear retained MQTT discovery configs for all known input topic styles.
        This helps HA forget old entity IDs when discovery naming has changed.
        """
        max_inputs = int(getattr(settings, "MAX_ZONES", 96) or 96)
        logger.warning("DISCOVERY CLEAR inputs: domain=%s max_inputs=%d", settings.DOMAIN, max_inputs)

        for i in range(1, max_inputs + 1):
            topics = [
                # current padded format
                f"homeassistant/binary_sensor/{settings.DOMAIN}/input{i:03d}/config",

                # legacy non-padded format
                f"homeassistant/binary_sensor/{settings.DOMAIN}/input{i}/config",
            ]

            for topic in topics:
                logger.info("Clearing input discovery topic: %s", topic)
                self.publish(topic, "", qos=1, retain=True)
                time.sleep(0.005)


    def clear_output_discovery(self):
        """
        Clear retained MQTT discovery configs for all known output topic styles.
        This removes stale HA entities from previous discovery naming schemes.
        """
        max_outputs = int(getattr(settings, "MAX_OUTPUTS", 96) or 96)
        logger.warning("DISCOVERY CLEAR outputs: domain=%s max_outputs=%d", settings.DOMAIN, max_outputs)

        for i in range(1, max_outputs + 1):
            topics = [
                # current padded format
                f"homeassistant/switch/{settings.DOMAIN}/output{i:03d}/config",

                # legacy non-padded format
                f"homeassistant/switch/{settings.DOMAIN}/output{i}/config",

                # possible old alternate naming
                f"homeassistant/switch/{settings.DOMAIN}/switch{i}/config",

                # legacy SCSRIO output topics if they ever existed
                f"homeassistant/switch/{settings.DOMAIN}/scsriooutput{i:03d}/config",
                f"homeassistant/switch/{settings.DOMAIN}/scsriooutput{i}/config",
            ]

            for topic in topics:
                logger.info("Clearing output discovery topic: %s", topic)
                self.publish(topic, "", qos=1, retain=True)
                time.sleep(0.005)

    def clear_flag_discovery(self):
        for i in range(1, 255):
            topic = f"homeassistant/switch/{settings.DOMAIN}/flag{i:03d}/config"
            self.publish(topic, "", qos=2, retain=True)
            time.sleep(0.005)

    def clear_counter_discovery(self):
        for i in range(0, int(settings.ALARMNUMBEROFCOUNTERS)):

            # Clear number entity
            topic_number = f"homeassistant/number/{settings.DOMAIN}/counter{i:03d}/config"
            self.publish(topic_number, "", qos=2, retain=True)

            time.sleep(0.005)

    def clear_sensor_discovery(self):
        for i in range(0, int(settings.ALARMNUMBEROFSENSORS)):

            # Clear number entity
            topic_number = f"homeassistant/number/{settings.DOMAIN}/sensor{i:03d}/config"
            self.publish(topic_number, "", qos=2, retain=True)

            time.sleep(0.005)


    def clear_timer_discovery(self):
        #logging.info("clear_timer_discovery: START")

        for i in range(1, settings.COMFORT_TIMERS + 1):
            number_topic = f"homeassistant/number/{settings.DOMAIN}/timer{i:03d}/config"
            sensor_topic = f"homeassistant/sensor/{settings.DOMAIN}/timer{i:03d}/config"

            # logging.info(
            #     "clear_timer_discovery: clearing timer=%03d number_topic=%s sensor_topic=%s",
            #     i, number_topic, sensor_topic
            # )

            self.publish(number_topic, "", qos=2, retain=True)
            self.publish(sensor_topic, "", qos=2, retain=True)
            time.sleep(0.005)

        #logging.info("clear_timer_discovery: END")



    def clear_battery_voltage_discovery(self):
        """Remove MQTT discovery for battery and DC voltage sensors for main board and all SEM boards."""

        topics = [
            f"homeassistant/sensor/{settings.DOMAIN}/battery_main_voltage/config",
            f"homeassistant/sensor/{settings.DOMAIN}/dc_supply_main_voltage/config",
        ]

        for sem in range(1, 8):
            topics.append(f"homeassistant/sensor/{settings.DOMAIN}/battery_slave{sem}_voltage/config")
            topics.append(f"homeassistant/sensor/{settings.DOMAIN}/dc_supply_slave{sem}_voltage/config")

        for topic in topics:
             self.publish(topic, "", qos=2, retain=True)
             time.sleep(0.02)




    def _ha_discovery_topic(self, component: str, object_id: str) -> str:
        # Example: homeassistant/sensor/cytech_comfort_mqtt/counter244/config
        return f"homeassistant/{component}/{settings.DOMAIN}/{object_id}/config"

    def _publish_discovery(self, topic: str, payload: dict, retain: bool = True):
        self.publish(topic, json.dumps(payload), qos=2, retain=retain)

    def _clear_discovery(self, topic: str):
        # MQTT Discovery deletion: publish empty retained payload
        self.publish(topic, "", qos=2, retain=True)

    def _availability_block(self) -> dict:
        # Keep this consistent across all entities
        return {
            "availability_topic": settings.ALARMONLINETOPIC,
            "payload_available": "1",
            "payload_not_available": "0",
        }

    def _device_block(self) -> dict:
        # Use your existing MQTT_DEVICE if you already have it
        return MQTT_DEVICE_COMFORT


    ####  MQTT Discovery for Inputs, Outputs, Flags, Counters, Timers and Users ####

    def publish_output_discovery(self, mqtt_device):
        try:
            max_outputs = int(getattr(settings, "COMFORT_OUTPUTS", 0) or 0)
            logger.info("publish_output_discovery: COMFORT_OUTPUTS=%r", getattr(settings, "COMFORT_OUTPUTS", None))
        except Exception as e:
            logger.exception("Error reading COMFORT_OUTPUTS: %s", e)
            max_outputs = 0

        if max_outputs <= 0:
            logger.warning("publish_output_discovery: COMFORT_OUTPUTS invalid (%r)", getattr(settings, "COMFORT_OUTPUTS", None))
            return

        for i in range(1, max_outputs + 1):
            logger.warning("OUTPUT DISCOVERY START %03d/%03d", i, max_outputs)

            props_str = settings.output_properties.get(str(i))
            props_int = settings.output_properties.get(i)
            props = settings.output_properties.get(str(i), settings.output_properties.get(i, {}))

            logger.debug(
                "OUTPUT %03d props_str=%r (%s) props_int=%r (%s) chosen=%r (%s)",
                i,
                props_str, type(props_str),
                props_int, type(props_int),
                props, type(props)
            )

            if isinstance(props, dict):
                name = (props.get("Name") or props.get("name") or f"Output{i:03d}").strip()
            elif isinstance(props, str):
                name = props.strip() or f"Output{i:03d}"
            else:
                name = f"Output{i:03d}"

            state_topic = settings.ALARMOUTPUTTOPIC % i
            command_topic = settings.ALARMOUTPUTCOMMANDTOPIC % i
            discovery_topic = f"homeassistant/switch/{settings.DOMAIN}/output{i:03d}/config"

            payload = {
                "name": name,
                "unique_id": f"{settings.DOMAIN}_output{i:03d}",
                "object_id": f"{settings.DOMAIN}_output{i:03d}",
                "state_topic": state_topic,
                "command_topic": command_topic,
                "payload_on": "1",
                "payload_off": "0",
                "state_on": "1",
                "state_off": "0",
                "icon": "mdi:flash",
                "availability": [
                    {
                        "topic": settings.ALARMAVAILABLETOPIC,
                        "payload_available": "1",
                        "payload_not_available": "0",
                    },
                    {
                        "topic": settings.ALARMCONNECTEDTOPIC,
                        "payload_available": "1",
                        "payload_not_available": "0",
                    },
                ],
                "availability_mode": "all",
                "device": mqtt_device,
            }


            self.publish(discovery_topic, json.dumps(payload), qos=1, retain=True)
            time.sleep(0.05)


    def publish_input_discovery(self, mqtt_device):
        try:
            max_inputs = int(settings.COMFORT_INPUTS)
        except Exception:
            max_inputs = 0

        if max_inputs <= 0:
            logger.warning(
                "publish_input_discovery: COMFORT_INPUTS invalid (%r)",
                getattr(settings, "COMFORT_INPUTS", None),
            )
            return

        for i in range(1, max_inputs + 1):
            name = f"Zone{i:03d}"
            device_class = None

            props = settings.input_properties.get(str(i)) if settings.ZONEMAPFILE else None

            if props:
                try:
                    name = props.get("Name") or name
                except Exception:
                    logger.warning("INPUT %03d props malformed: %r", i, props)

            state_topic = settings.ALARMINPUTTOPIC % i
            discovery_topic = f"homeassistant/binary_sensor/{settings.DOMAIN}/input{i:03d}/config"

            payload = {
                "name": name,
                "unique_id": f"{settings.DOMAIN}_input{i:03d}",
                "object_id": f"{settings.DOMAIN}_input{i:03d}",
                "state_topic": state_topic,
                "payload_on": "1",
                "payload_off": "0",
                "state_on": "1",
                "state_off": "0",
                "availability": [
                    {
                        "topic": settings.ALARMAVAILABLETOPIC,
                        "payload_available": "1",
                        "payload_not_available": "0",
                    },
                    {
                        "topic": settings.ALARMCONNECTEDTOPIC,
                        "payload_available": "1",
                        "payload_not_available": "0",
                    },
                ],
                "availability_mode": "all",
                "device": mqtt_device,
            }

            if device_class:
                payload["device_class"] = device_class

            self.publish(discovery_topic, json.dumps(payload), qos=1, retain=True)
            time.sleep(0.05)


    def publish_flag_discovery(self, mqtt_device):
        for key, value in settings.flag_properties.items():
            try:
                i = int(key)
            except ValueError:
                continue

            if i < 1 or i > settings.UI_FLAG_COUNT:  # Only publish flags that are within the UI-supported range
                continue
            # logger.info(
            #     "publish_flag_discovery: raw key=%r value=%r type=%s",
            #     key, value, type(value).__name__
            # )


            if isinstance(value, dict):
                flag_name = (value.get("Name") or value.get("name") or f"Flag{i:03d}").strip()
            elif isinstance(value, str):
                flag_name = value.strip() or f"Flag{i:03d}"
            else:
                flag_name = f"Flag{i:03d}"

            # logger.info(
            #     "publish_flag_discovery: flag=%s resolved_name=%r discovery_topic=%s",
            #     i, flag_name, f"homeassistant/switch/{settings.DOMAIN}/flag{i:03d}/config"
            # )
                
            state_topic = settings.ALARMFLAGTOPIC % i
            command_topic = settings.ALARMFLAGCOMMANDTOPIC % i
            discovery_topic = f"homeassistant/switch/{settings.DOMAIN}/flag{i:03d}/config"

            mqtt_msg = json.dumps({
                "name": flag_name,
                "unique_id": f"{settings.DOMAIN}_flag{i:03d}",
                "object_id": f"{settings.DOMAIN}_flag{i:03d}",
                "state_topic": state_topic,
                "command_topic": command_topic,
                "payload_on": "1",
                "payload_off": "0",
                "state_on": "1",
                "state_off": "0",
                "availability": [
                    {
                        "topic": settings.ALARMAVAILABLETOPIC,
                        "payload_available": "1",
                        "payload_not_available": "0",
                    },
                    {
                        "topic": settings.ALARMCONNECTEDTOPIC,
                        "payload_available": "1",
                        "payload_not_available": "0",
                    },
                ],
                "availability_mode": "all",
                "icon": "mdi:flag",
                "device": mqtt_device,
            })

            self.publish(discovery_topic, mqtt_msg, qos=2, retain=True)
            time.sleep(0.01)


    def publish_counter_discovery(self, mqtt_device):
        for key, value in settings.counter_properties.items():
            try:
                i = int(key)
            except ValueError:
                continue

            if i < 0 or i >= settings.UI_COUNTER_COUNT:
                continue

            if isinstance(value, dict):
                counter_name = (value.get("Name") or value.get("name") or f"Counter{i:03d}").strip()
            elif isinstance(value, str):
                counter_name = value.strip() or f"Counter{i:03d}"
            else:
                counter_name = f"Counter{i:03d}"

            state_topic = settings.ALARMCOUNTERTOPIC % i
            command_topic = settings.ALARMCOUNTERCOMMANDTOPIC % i

            availability = [
                {
                    "topic": settings.ALARMAVAILABLETOPIC,
                    "payload_available": "1",
                    "payload_not_available": "0",
                },
                {
                    "topic": settings.ALARMCONNECTEDTOPIC,
                    "payload_available": "1",
                    "payload_not_available": "0",
                },
            ]

            # Editable number entity
            number_discovery_topic = f"homeassistant/number/{settings.DOMAIN}/counter{i:03d}/config"
            number_msg = json.dumps({
                "name": counter_name,
                "unique_id": f"{settings.DOMAIN}_counter{i:03d}",
                "object_id": f"{settings.DOMAIN}_counter{i:03d}",
                "state_topic": state_topic,
                "command_topic": command_topic,
                "value_template": "{{ value | int }}",
                "command_template": "{{ value }}",
                "availability": availability,
                "availability_mode": "all",
                "mode": "box",
                "min": -32768,
                "max": 32767,
                "step": 1,
                "icon": "mdi:counter",
                "device": mqtt_device,
            })
            self.publish(number_discovery_topic, number_msg, qos=2, retain=True)
            time.sleep(0.01)



    def publish_sensor_discovery(self, mqtt_device):
        for key, value in settings.sensor_properties.items():
            try:
                i = int(key)
            except ValueError:
                continue

            if i < 0 or i >= settings.UI_SENSOR_COUNT:
                continue

            if isinstance(value, dict):
                sensor_name = (value.get("Name") or value.get("name") or f"Sensor{i:03d}").strip()
            elif isinstance(value, str):
                sensor_name = value.strip() or f"Sensor{i:03d}"
            else:
                sensor_name = f"Sensor{i:03d}"

            state_topic = settings.ALARMSENSORTOPIC % i
            command_topic = settings.ALARMSENSORCOMMANDTOPIC % i

            availability = [
                {
                    "topic": settings.ALARMAVAILABLETOPIC,
                    "payload_available": "1",
                    "payload_not_available": "0",
                },
                {
                    "topic": settings.ALARMCONNECTEDTOPIC,
                    "payload_available": "1",
                    "payload_not_available": "0",
                },
            ]

            # Editable number entity
            number_discovery_topic = f"homeassistant/number/{settings.DOMAIN}/sensor{i:03d}/config"
            number_msg = json.dumps({
                "name": sensor_name,
                "unique_id": f"{settings.DOMAIN}_sensor{i:03d}",
                "object_id": f"{settings.DOMAIN}_sensor{i:03d}",
                "state_topic": state_topic,
                "command_topic": command_topic,
                "value_template": "{{ value | int }}",
                "command_template": "{{ value }}",
                "availability": availability,
                "availability_mode": "all",
                "mode": "box",
                "min": -32768,
                "max": 32767,
                "step": 1,
                "icon": "mdi:gauge",
                "device": mqtt_device,
            })
            self.publish(number_discovery_topic, number_msg, qos=2, retain=True)
            time.sleep(0.01)



    def publish_timer_discovery(self, mqtt_device):

        for key, value in settings.timer_properties.items():
     
            try:
                i = int(key)
            except ValueError:
                logging.warning("publish_timer_discovery: skipping non-integer key=%r", key)
                continue

            if i < 1 or i > settings.UI_TIMER_COUNT:  # Only publish timers that are within the UI-supported range
                continue


            if isinstance(value, dict):
                timer_name = (value.get("Name") or value.get("name") or f"Timer{i:03d}").strip()
            elif isinstance(value, str):
                timer_name = value.strip() or f"Timer{i:03d}"
            else:
                timer_name = f"Timer{i:03d}"

            discovery_topic = f"homeassistant/sensor/{settings.DOMAIN}/timer{i:03d}/config"
            state_topic = settings.COMFORTTIMERSTOPIC % i

            mqtt_msg = json.dumps({
                "name": timer_name,
                "unique_id": f"{settings.DOMAIN}_timer{i:03d}",
                "object_id": f"{settings.DOMAIN}_timer{i:03d}",
                "state_topic": state_topic,
                "availability": [
                    {
                        "topic": settings.ALARMAVAILABLETOPIC,
                        "payload_available": "1",
                        "payload_not_available": "0",
                    },
                    {
                        "topic": settings.ALARMCONNECTEDTOPIC,
                        "payload_available": "1",
                        "payload_not_available": "0",
                    },
                ],
                "availability_mode": "all",
                "icon": "mdi:timer-outline",
                "device": mqtt_device,
            })

            # logging.info(
            #     "publish_timer_discovery: publishing timer=%03d name=%r discovery_topic=%s state_topic=%s",
            #     i, timer_name, discovery_topic, state_topic
            # )
            # logging.debug("publish_timer_discovery: payload=%s", mqtt_msg)

            self.publish(discovery_topic, mqtt_msg, qos=2, retain=True)
            time.sleep(0.01)


    def PublishBatteryVoltageDiscovery(self):
        """Publish MQTT discovery for main battery/DC voltage sensors and installed SEM boards only.
        Also clears retained discovery topics for SEM boards that are no longer installed.
        """
        device_block = self.MQTT_DEVICE_COMFORT

        availability = [
            {
                "topic": settings.ALARMAVAILABLETOPIC,
                "payload_available": "1",
                "payload_not_available": "0"
            },
            {
                "topic": settings.ALARMCONNECTEDTOPIC,
                "payload_available": "1",
                "payload_not_available": "0"
            }
        ]

        try:
            installed_slaves = int(settings.device_properties.get("sem_id", 0))
        except Exception:
            installed_slaves = 0

        installed_slaves = max(0, min(installed_slaves, 7))

        logger.info(
            "Publishing battery voltage discovery for main board and %d installed SEM boards",
            installed_slaves
        )

        # Clear retained discovery for SEM boards above the installed count
        for sem in range(installed_slaves + 1, 8):
            battery_discovery_topic = f"homeassistant/sensor/{settings.DOMAIN}/battery_slave{sem}_voltage/config"
            dc_discovery_topic = f"homeassistant/sensor/{settings.DOMAIN}/dc_supply_slave{sem}_voltage/config"

            self.publish(battery_discovery_topic, "", qos=2, retain=True)
            time.sleep(0.02)

            self.publish(dc_discovery_topic, "", qos=2, retain=True)
            time.sleep(0.02)

        sensors = [
            {
                "suffix": "battery_main_voltage",
                "name": "Battery Main Voltage",
                "icon": "mdi:car-battery"
            },
            {
                "suffix": "dc_supply_main_voltage",
                "name": "DC Supply Main Voltage",
                "icon": "mdi:flash"
            }
        ]

        for sem in range(1, installed_slaves + 1):
            sensors.append({
                "suffix": f"battery_slave{sem}_voltage",
                "name": f"Battery SEM {sem} Voltage",
                "icon": "mdi:car-battery"
            })
            sensors.append({
                "suffix": f"dc_supply_slave{sem}_voltage",
                "name": f"DC Supply SEM {sem} Voltage",
                "icon": "mdi:flash"
            })

        for sensor in sensors:
            state_topic = f"{settings.DOMAIN}/alarm/{sensor['suffix']}"
            discovery_topic = f"homeassistant/sensor/{settings.DOMAIN}/{sensor['suffix']}/config"

            payload = {
                "name": sensor["name"],
                "unique_id": f"{settings.DOMAIN}_{sensor['suffix']}",
                "object_id": f"{settings.DOMAIN}_{sensor['suffix']}",
                "state_topic": state_topic,
                "unit_of_measurement": "V",
                "device_class": "voltage",
                "state_class": "measurement",
                "suggested_display_precision": 2,
                "icon": sensor["icon"],
                "availability": availability,
                "availability_mode": "all",
                "device": device_block
            }

            self.publish(discovery_topic, json.dumps(payload), qos=2, retain=True)
            #logger.info("Published battery voltage discovery: %s", discovery_topic)
            time.sleep(0.05)



    
    def PublishBatteryVoltageStates(self):
        """Publish main battery/DC voltages and installed SEM board voltages.
        Also clears retained state topics for SEM boards that are no longer installed.
        """
        try:
            installed_slaves = int(settings.device_properties.get("sem_id", 0))
        except Exception:
            installed_slaves = 0

        # Clamp to valid SEM range
        installed_slaves = max(0, min(installed_slaves, 7))

        logger.info(
            "Publishing battery voltage states for main board and %d installed SEM boards",
            installed_slaves
        )

        def publish_voltage(topic, raw_value, label):
            try:
                value = f"{float(raw_value):.2f}"
            except Exception:
                value = "-1"

            # logger.info(
            #     "PublishBatteryVoltageStates: topic=%s label=%s value=%s raw=%s",
            #     topic,
            #     label,
            #     value,
            #     raw_value
            # )

            if value != "-1":
                self.publish(topic, value, qos=2, retain=True)
                logger.info("Published %s: %s -> %s", label, topic, value)
            else:
                logger.warning("Skipping %s publish because raw value = %r", label, raw_value)

        # --------------------------------------------------
        # 1. CLEAR OLD SEM STATE TOPICS
        # --------------------------------------------------
        for sem in range(installed_slaves + 1, 8):
            battery_topic = f"{settings.DOMAIN}/alarm/battery_slave{sem}_voltage"
            dc_topic = f"{settings.DOMAIN}/alarm/dc_supply_slave{sem}_voltage"

            self.publish(battery_topic, "", qos=2, retain=True)
            #logger.info("Cleared retained battery state topic: %s", battery_topic)
            time.sleep(0.02)

            self.publish(dc_topic, "", qos=2, retain=True)
            #logger.info("Cleared retained DC supply state topic: %s", dc_topic)
            time.sleep(0.02)

        # --------------------------------------------------
        # 2. PUBLISH MAIN BOARD
        # --------------------------------------------------
        publish_voltage(
            f"{settings.DOMAIN}/alarm/battery_main_voltage",
            settings.device_properties.get("BatteryVoltageMain", "-1"),
            "Battery Main Voltage"
        )
        time.sleep(0.05)

        publish_voltage(
            f"{settings.DOMAIN}/alarm/dc_supply_main_voltage",
            settings.device_properties.get("ChargeVoltageMain", "-1"),
            "DC Supply Main Voltage"
        )
        time.sleep(0.05)

        # --------------------------------------------------
        # 3. PUBLISH INSTALLED SEM BOARDS
        # --------------------------------------------------
        for sem in range(1, installed_slaves + 1):
            publish_voltage(
                f"{settings.DOMAIN}/alarm/battery_slave{sem}_voltage",
                settings.device_properties.get(f"BatteryVoltageSlave{sem}", "-1"),
                f"Battery SEM {sem} Voltage"
            )
            time.sleep(0.05)

            publish_voltage(
                f"{settings.DOMAIN}/alarm/dc_supply_slave{sem}_voltage",
                settings.device_properties.get(f"ChargeVoltageSlave{sem}", "-1"),
                f"DC Supply SEM {sem} Voltage"
            )
            time.sleep(0.05)
            """Publish main battery/DC voltages and installed SEM board voltages as individual MQTT topics."""
            try:
                installed_slaves = int(settings.device_properties.get("sem_id", 0))
            except Exception:
                installed_slaves = 0

            installed_slaves = max(0, min(installed_slaves, 7))

            def publish_voltage(topic, raw_value, label):
                try:
                    value = f"{float(raw_value):.2f}"
                except Exception:
                    value = "-1"

                # logging.info(
                #     "PublishBatteryVoltageStates: topic=%s label=%s value=%s raw=%s",
                #     topic,
                #     label,
                #     value,
                #     raw_value
                # )

                if value != "-1":
                    self.publish(topic, value, qos=2, retain=True)
                    # logging.info("Published %s: %s -> %s", label, topic, value)
                else:
                    logging.warning("Skipping %s publish because raw value = %r", label, raw_value)

            # Main board
            publish_voltage(
                f"{settings.DOMAIN}/alarm/battery_main_voltage",
                settings.device_properties.get("BatteryVoltageMain", "-1"),
                "Battery Main Voltage"
            )
            time.sleep(0.05)

            publish_voltage(
                f"{settings.DOMAIN}/alarm/dc_supply_main_voltage",
                settings.device_properties.get("ChargeVoltageMain", "-1"),
                "DC Supply Main Voltage"
            )
            time.sleep(0.05)

            # Installed SEM boards only
            for sem in range(1, installed_slaves + 1):
                publish_voltage(
                    f"{settings.DOMAIN}/alarm/battery_slave{sem}_voltage",
                    settings.device_properties.get(f"BatteryVoltageSlave{sem}", "-1"),
                    f"Battery SEM {sem} Voltage"
                )
                time.sleep(0.05)

                publish_voltage(
                    f"{settings.DOMAIN}/alarm/dc_supply_slave{sem}_voltage",
                    settings.device_properties.get(f"ChargeVoltageSlave{sem}", "-1"),
                    f"DC Supply SEM {sem} Voltage"
                )
                time.sleep(0.05)


    def run(self):

        signal.signal(signal.SIGTERM, self.exit_gracefully)
        if os.name != 'nt':
            signal.signal(signal.SIGQUIT, self.exit_gracefully)

        data_cclx = Path("/data/site.cclx")

        if data_cclx.exists():
            logger.info("Loading CCLX enrichment from %s", data_cclx)
            self.add_descriptions(data_cclx)

        elif settings.COMFORT_CCLX_FILE is not None:
            config_filename = self.sanitize_filename(settings.COMFORT_CCLX_FILE, "cclx")
            if config_filename:
                cfg = Path("/config/" + config_filename)
                logger.info("Loading CCLX enrichment from %s", cfg)
                self.add_descriptions(cfg)
            else:
                logger.info("Illegal Configurator CCLX filename detected")
        else:
            logger.info("No CCLX file configured")

        self.connect_async(self.mqtt_ip, self.mqtt_port, 60)

        if self.connected:
            settings.BROKERCONNECTED = True
            settings.device_properties['BridgeConnected'] = 1
            self.publish(settings.ALARMAVAILABLETOPIC, 0, qos=2, retain=True)
            self.will_set(settings.ALARMLWTTOPIC, payload="Offline", qos=2, retain=True)

        self.loop_start()

        try:
            while settings.RUN:

                self.serial = None

                try:
                    logger.info("Opening Comfort serial port /dev/serial0 @ 115200")
                    self.serial = LoggedSerial(
                        port='/dev/serial0',
                        baudrate=115200,
                        timeout=0.2
                    )

                    self.serial_running = True
                    threading.Thread(target=self.serial_reader, daemon=True).start()

                    self.login()
                    settings.SAVEDTIME = datetime.now()

                    while settings.RUN and self.serial_running:

                        self.process_serial_queue()

                        time.sleep(0.01)

                except (serial.SerialException, OSError) as v:
                    logger.debug("Comfort serial error '%s'", str(v))

                finally:

                    self.serial_running = False

                    if self.serial:
                        try:
                            self.serial.close()
                        except Exception:
                            pass
                        self.serial = None

                # Reconnect logic (unchanged)
                settings.COMFORTCONNECTED = False
                settings.FIRST_LOGIN = True
                logger.error('Lost connection to Comfort, reconnecting...')

                if settings.BROKERCONNECTED:
                    self.publish(settings.ALARMAVAILABLETOPIC, 0, qos=2, retain=True)
                    self.publish(settings.ALARMLWTTOPIC, 'Offline', qos=2, retain=True)
                    self.publish(
                        settings.ALARMCONNECTEDTOPIC,
                        "1" if settings.COMFORTCONNECTED else "0",
                        qos=2,
                        retain=False
                    )

                time.sleep(settings.RETRY.seconds)

        except KeyboardInterrupt:
            logger.info('Shutting down.')
            self.exit_gracefully(1, 1)

            if self.connected:
                settings.device_properties['BridgeConnected'] = 0
                try:
                    self.serial.write("\x03LI\r".encode())
                except:
                    pass

            settings.RUN = False

        finally:
            if settings.BROKERCONNECTED:
                infot = self.publish(settings.ALARMAVAILABLETOPIC, 0, qos=2, retain=True)
                infot = self.publish(settings.ALARMLWTTOPIC, 'Offline', qos=2, retain=True)
                infot.wait_for_publish(1)

            self.loop_stop()



    def serial_reader(self):
        logger.info("Serial reader thread started")

        while self.serial_running:
            try:
                raw = self.serial.read_until(b'\r')

                if not raw:
                    continue

                line = raw.decode(errors="ignore").strip()

                if not line:
                    continue

                try:
                    self.serial_queue.put_nowait(line)
                except:
                    logger.warning("Serial queue full, dropping: %r", line)

            except Exception as e:
                logger.error("Serial thread error: %s", e)
                time.sleep(1)

    def process_serial_queue(self):
        for _ in range(100):  # optional burst limit
            try:
                line = self.serial_queue.get_nowait()
            except Empty:
                break

            match = self._line_pattern.search(line)
            if not match:
                continue

            line = match.group(1)

         #   logger.debug("RX: %s", line[1:])
            logger.debug("RX FULL: %s", line[1:])

            self.handle_serial_line(line)


    def handle_serial_line(self, line):
        # --- LOGIN ---
        if line[1:3] == "LU":
            luMsg = ComfortLUUserLoggedIn(line[1:])
            if luMsg.user != 0:
                logger.info('Comfort Login Ok - User %s', (luMsg.user if luMsg.user != 254 else 'Engineer'))

                if settings.BROKERCONNECTED:
                    time.sleep(1)
                else:
                    logger.info("Waiting for MQTT Broker to come Online...")

                self.connected = True
                settings.COMFORTCONNECTED = True

                self.publish(settings.ALARMCOMMANDTOPIC, "comm test", qos=2, retain=True)
                time.sleep(0.01)

                self.publish(settings.REFRESHTOPIC, "", qos=2, retain=True)
                time.sleep(0.01)

                self.setdatetime()

                if settings.FIRST_LOGIN:
                    logger.info("Login - reading current state from Comfort...")
                    self.readcurrentstate()
                    settings.FIRST_LOGIN = False

            else:
                logger.debug("Disconnect (LU00)")
                settings.FIRST_LOGIN = True
                settings.COMFORTCONNECTED = False

                if settings.BROKERCONNECTED:
                    self.publish(settings.ALARMAVAILABLETOPIC, 0, qos=2, retain=True)
                    self.publish(settings.ALARMLWTTOPIC, 'Offline', qos=2, retain=True)
                    self.publish(settings.ALARMCONNECTEDTOPIC, "0", qos=2, retain=False)

        # --- TIME SYNC ---
        elif line[1:5] == "PS00":
            self.setdatetime()

        # --- INPUTS ---
        elif line[1:3] == "IP" and settings.CacheState:
            ipMsg = ComfortIPInputActivationReport(line[1:])

            if ipMsg.state < 2:
                try:
                    _name = settings.input_properties[str(ipMsg.input)]['Name'] if settings.ZONEMAPFILE else f"Zone{ipMsg.input:02d}"
                except KeyError:
                    _name = f"Zone{ipMsg.input}"

                try:
                    _zoneword = settings.input_properties[str(ipMsg.input)]['ZoneWord'] if settings.ZONEMAPFILE else ""
                except KeyError:
                    _zoneword = ""

                settings.ZoneCache[ipMsg.input] = ipMsg.state

                if 1 <= ipMsg.input <= int(settings.COMFORT_INPUTS):
                    self.publish(
                        settings.ALARMINPUTTOPIC % ipMsg.input,
                        str(int(ipMsg.state)),
                        qos=2,
                        retain=True
                    )
                    time.sleep(0.01)

                log_msg = json.dumps({
                    "Time": datetime.now().replace(microsecond=0).isoformat(),
                    "Type": "input",
                    "Id": ipMsg.input,
                    "Name": _name,
                    "ZoneWord": _zoneword,
                    "State": int(ipMsg.state),
                    "Bypass": settings.BypassCache[ipMsg.input]
                })
                self.publish(settings.ALARMLOGTOPIC, log_msg, qos=2, retain=False)

        # --- COUNTERS ---
        elif line[1:3] == "CT" and settings.CacheState:
            ipMsgCT = ComfortCTCounterActivationReport(line[1:])

            self.publish(
                settings.ALARMCOUNTERTOPIC % ipMsgCT.counter,
                str(int(ipMsgCT.value)),
                qos=2,
                retain=True
            )
            time.sleep(0.01)

        # --- SENSOR REQUEST RESPONSE ---
        elif line[1:3] == "s?":
            ipMsgSQ = Comfort_RSensorActivationReport(line[1:])
            sensor_id = ipMsgSQ.sensor
            value = int(ipMsgSQ.value)
            topic = settings.ALARMSENSORTOPIC % sensor_id

            self.publish(topic, str(value), qos=2, retain=True)

        # --- SENSOR REPORT ---
        elif line[1:3] == "sr" and settings.CacheState:
            ipMsgSR = Comfort_RSensorActivationReport(line[1:])
            sensor_id = ipMsgSR.sensor
            value = int(ipMsgSR.value)
            topic = settings.ALARMSENSORTOPIC % sensor_id

            self.publish(topic, str(value), qos=2, retain=True)

        # --- TIMER ---
        elif line[1:3] == "TR":
            ipMsgTR = ComfortTRReport(line[1:])
            timer_id = ipMsgTR.timer
            value = ipMsgTR.value
            state = ipMsgTR.state
            topic = settings.COMFORTTIMERSTOPIC % timer_id

            self.publish(topic, str(value), qos=2, retain=True)

            log_msg = json.dumps({
                "Time": datetime.now().replace(microsecond=0).isoformat(),
                "Type": "timer",
                "Id": timer_id,
                "Value": value,
                "State": state
            })
            self.publish(settings.ALARMLOGTOPIC, log_msg, qos=2, retain=False)
            time.sleep(0.01)

        # --- LOGIN REPORT ---
        elif line[1:3] == "LR":
            luMsg = ComfortLUUserLoggedIn(line[1:])
            if luMsg.user != 0:
                message_topic = f"Comfort {luMsg.method} Login - {f'User {luMsg.user}' if luMsg.user != 254 else 'Engineer'}"
                self.publish_alarm_message(message_topic, retain=False)

        # --- BULK ZONES ---
        elif line[1:3] == "Z?":
            zMsg = ComfortZ_ReportAllZones(line[1:])

            for ipMsgZ in zMsg.inputs:
                settings.ZoneCache[ipMsgZ.input] = ipMsgZ.state

                if 1 <= ipMsgZ.input <= int(settings.COMFORT_INPUTS):
                    self.publish(
                        settings.ALARMINPUTTOPIC % ipMsgZ.input,
                        str(int(ipMsgZ.state)),
                        qos=2,
                        retain=True
                    )
                    time.sleep(0.01)

        # --- MODE ---
        elif line[1:3] == "M?" or line[1:3] == "MD":
            mMsg = ComfortM_SecurityModeReport(line[1:])
            self.publish(settings.ALARMSTATETOPIC, mMsg.modename, qos=2, retain=True)
            self.publish(settings.ALARMMODETOPIC, mMsg.mode, qos=2, retain=True)
            self.entryexitdelay = 0
            if hasattr(self, "alarm_log"):
                self.alarm_log.add(f"MODE -> {mMsg.modename} ({mMsg.mode})", level="STATE")

        # --- STATUS ---
        elif line[1:3] == "S?":
            SMsg = ComfortS_SecurityModeReport(line[1:])
            self.publish(settings.ALARMSTATETOPIC, SMsg.modename, qos=2, retain=True)
            if hasattr(self, "alarm_log"):
                self.alarm_log.add(f"STATUS -> {SMsg.modename}", level="STATE")

        # --- SYSTEM INFO / DISCOVERY ---
        elif line[1:3] == "V?":
            VMsg = ComfortV_SystemTypeReport(line[1:])

            settings.device_properties['ComfortFileSystem'] = str(VMsg.filesystem)
            settings.device_properties['ComfortFirmwareType'] = str(VMsg.firmware)
            settings.device_properties['Version'] = str(VMsg.version) + "." + str(VMsg.revision).zfill(3)

            self.UpdateDeviceInfo(True)

            current_firmware = float(str(VMsg.version) + "." + str(VMsg.revision).zfill(3))
            if current_firmware >= settings.SupportedFirmware:
                logging.info(
                    "%s detected (Supported Firmware %d.%03d)",
                    settings.models[int(settings.device_properties['ComfortFileSystem'])]
                    if int(settings.device_properties['ComfortFileSystem']) in settings.models else "Unknown device",
                    VMsg.version,
                    VMsg.revision
                )
            else:
                logging.error(
                    "%s detected (Unsupported Firmware %d.%03d)",
                    settings.models[int(settings.device_properties['ComfortFileSystem'])]
                    if int(settings.device_properties['ComfortFileSystem']) in settings.models else "Unknown device",
                    VMsg.version,
                    VMsg.revision
                )

        elif line[1:5] == "u?01":
            uMsg = Comfort_U_SystemCPUTypeReport(line[1:])

            settings.device_properties['CPUType'] = str(uMsg.cputype)
            if str(uMsg.cputype) == "N/A":
                settings.device_properties['BatteryVoltageMain'] = "-1"
                settings.device_properties['BatteryVoltageSlave1'] = "-1"
                settings.device_properties['BatteryVoltageSlave2'] = "-1"
                settings.device_properties['BatteryVoltageSlave3'] = "-1"
                settings.device_properties['BatteryVoltageSlave4'] = "-1"
                settings.device_properties['BatteryVoltageSlave5'] = "-1"
                settings.device_properties['BatteryVoltageSlave6'] = "-1"
                settings.device_properties['BatteryVoltageSlave7'] = "-1"
                settings.device_properties['ChargeVoltageMain'] = "-1"
                settings.device_properties['ChargeVoltageSlave1'] = "-1"
                settings.device_properties['ChargeVoltageSlave2'] = "-1"
                settings.device_properties['ChargeVoltageSlave3'] = "-1"
                settings.device_properties['ChargeVoltageSlave4'] = "-1"
                settings.device_properties['ChargeVoltageSlave5'] = "-1"
                settings.device_properties['ChargeVoltageSlave6'] = "-1"
                settings.device_properties['ChargeVoltageSlave7'] = "-1"
                settings.device_properties['ChargerStatus'] = "N/A"
                settings.device_properties['BatteryStatus'] = "N/A"

            self.UpdateDeviceInfo(True)

        elif line[1:3] == "EL":
            ELMsg = Comfort_EL_HardwareModelReport(line[1:])
            settings.device_properties['ComfortHardwareModel'] = str(ELMsg.hardwaremodel)
            self.UpdateDeviceInfo(True)

        elif line[1:3] == "D?":
            Comfort_D_SystemVoltageReport(line[1:])
            logger.info(
                "After parse: BatteryVoltageMain=%s ChargeVoltageMain=%s BatteryStatus=%s ChargerStatus=%s",
                settings.device_properties.get("BatteryVoltageMain"),
                settings.device_properties.get("ChargeVoltageMain"),
                settings.device_properties.get("BatteryStatus"),
                settings.device_properties.get("ChargerStatus"),
            )
            self.UpdateBatteryStatus()

        elif line[1:5] == "SN01":
            SNMsg = ComfortSN_SerialNumberReport(line[1:])
            if settings.COMFORT_SERIAL != SNMsg.serial_number:
                pass
            settings.COMFORT_KEY = SNMsg.refreshkey
            logging.info("Refresh Key: %s", settings.COMFORT_KEY)
            logging.info("Serial Number: %s", settings.COMFORT_SERIAL)
            settings.device_properties['SerialNumber'] = settings.COMFORT_SERIAL
            self.UpdateDeviceInfo(True)

        elif line[1:3] == "a?":
            aMsg = Comfort_A_SecurityInformationReport(line[1:])
            self.publish(settings.ALARMSTATUSTOPIC, aMsg.state, qos=2, retain=True)
            if aMsg.type == 'LowBattery':
                logging.warning("Low Battery - %s", aMsg.battery)
            elif aMsg.type == 'PowerFail':
                logging.warning("AC Fail")
            elif aMsg.type == 'Disarm':
                logging.info("System Disarmed")

        # --- ARM READY / NOT READY ---
        elif line[1:3] == "ER" and settings.CacheState:
            erMsg = ComfortERArmReadyNotReady(line[1:])
            if erMsg.zone != 0:
                zone = str(erMsg.zone)

                if settings.ZONEMAPFILE and self.CheckIndexNumberFormat(zone):
                    zone_name = settings.input_properties.get(zone, {}).get("Name", "Unknown zone")
                    message_topic = f"Zone {zone} ({zone_name}) Not Ready"
                else:
                    message_topic = f"Zone {zone} Not Ready"

                self.publish_alarm_message(message_topic, retain=True)
            else:
                logging.info("Ready To Arm...")

        # --- ALARM ---
        elif line[1:3] == "AM":
            amMsg = ComfortAMSystemAlarmReport(line[1:])
            self.publish_alarm_message(amMsg.message, retain=True)
            if amMsg.triggered:
                self.publish(settings.ALARMSTATETOPIC, "triggered", qos=2, retain=False)
                self.publish_alarm_message("triggered", retain=False)

        elif line[1:3] == "AR":
            arMsg = ComfortARSystemAlarmReport(line[1:])
            self.publish_alarm_message(arMsg.message, retain=True)

        # --- ENTRY/EXIT ---
        elif line[1:3] == "EX":
            exMsg = ComfortEXEntryExitDelayStarted(line[1:])
            self.entryexitdelay = exMsg.delay
            self.entryexit_timer()
            if exMsg.type == 1:
                self.publish(settings.ALARMSTATETOPIC, "pending", qos=2, retain=False)
            elif exMsg.type == 2:
                self.publish(settings.ALARMSTATETOPIC, "arming", qos=2, retain=False)

        # --- PHONE / DOORBELL ---
        elif line[1:3] == "RP":
            result = self.validate_hex_in_list(line[3:5], "0,1,255")
            if result and line[3:5] == "01":
                self.publish_alarm_message("Phone Ring", retain=True)
            elif result and line[3:5] == "00":
                self.publish_alarm_message("", retain=True)
            elif result and line[3:5] == "FF":
                self.publish_alarm_message("Phone Answer", retain=True)

        elif line[1:3] == "DB":
            result = self.validate_hex_in_list(line[3:5], "49-51,255")
            if result and line[3:5] == "FF":
                self.publish_alarm_message("", retain=True)
                self.publish_alarm_message(0, retain=True)
            elif result:
                self.publish_alarm_message(1, retain=True)
                message_topic = "Doorbell " + str(int(line[3:5], 16) - 48)
                self.publish_alarm_message(message_topic, retain=True)

        # --- OUTPUT CHANGE ---
        elif line[1:3] == "OP" and settings.CacheState:
            opMsg = ComfortOPOutputActivationReport(line[1:])
            if opMsg.state < 2:
                if 1 <= opMsg.output <= int(settings.COMFORT_OUTPUTS):
                    self.publish(
                        settings.ALARMOUTPUTTOPIC % opMsg.output,
                        str(int(opMsg.state)),
                        qos=2,
                        retain=True
                    )
                    time.sleep(0.01)

        # --- BULK OUTPUTS ---
        elif line[1:3] == "Y?":
            yMsg = ComfortY_ReportAllOutputs(line[1:])
            for opMsgY in yMsg.outputs:
                if 1 <= opMsgY.output <= int(settings.COMFORT_OUTPUTS):
                    self.publish(
                        settings.ALARMOUTPUTTOPIC % opMsgY.output,
                        str(int(opMsgY.state)),
                        qos=2,
                        retain=True
                    )
                    time.sleep(0.01)

        # --- COUNTER BULK ---
        elif line[1:5] == "r?00":
            cMsg = Comfort_R_ReportAllSensors(line[1:])
            for cMsgr in cMsg.counters:
                self.publish(
                    settings.ALARMCOUNTERTOPIC % cMsgr.counter,
                    str(int(cMsgr.value)),
                    qos=2,
                    retain=True
                )
                time.sleep(0.01)

        # --- SENSOR BULK ---
        elif line[1:5] == "r?01":
            sMsg = Comfort_R_ReportAllSensors(line[1:])
            for sMsgr in sMsg.sensors:
                self.publish(
                    settings.ALARMSENSORTOPIC % sMsgr.sensor,
                    str(int(sMsgr.value)),
                    qos=2,
                    retain=True
                )
                time.sleep(0.01)

        # --- BULK FLAGS ---
        elif (line[1:3] == "f?") and (len(line) == 69):
            fMsg = Comfortf_ReportAllFlags(line[1:])
            for fMsgf in fMsg.flags:
                flag_id = fMsgf.flag
                state = int(fMsgf.state)
                payload = "1" if state else "0"

                self.publish(
                    settings.ALARMFLAGTOPIC % flag_id,
                    payload,
                    qos=2,
                    retain=True
                )
                time.sleep(0.01)

        # --- BYPASS LIST ---
        elif line[1:3] == "b?":
            bMsg = ComfortB_ReportAllBypassZones(line[1:])
            if bMsg.value == 0:
                self.publish(settings.ALARMBYPASSTOPIC, 0, qos=2, retain=True)
            else:
                self.publish(settings.ALARMBYPASSTOPIC, bMsg.value, qos=2, retain=True)

        # --- UID / SERIAL FALLBACK ---
        elif line[1:9] == "DL7FF904":
            if len(line[1:]) == 18:
                settings.device_properties['uid'] = line[9:17]
                decoded = ComfortSN_SerialNumberReport(line[5:17])
                if decoded.serial_number != settings.COMFORT_SERIAL:
                    settings.COMFORT_SERIAL = decoded.serial_number
                    settings.device_properties['SerialNumber'] = settings.COMFORT_SERIAL
            else:
                settings.device_properties['uid'] = "00000000"

        # --- FLAG CHANGE ---
        elif line[1:3] == "FL" and settings.CacheState:
            flMsg = ComfortFLFlagActivationReport(line[1:])
            payload = "1" if int(flMsg.state) else "0"
            self.publish(settings.ALARMFLAGTOPIC % flMsg.flag, payload, qos=2, retain=True)
            time.sleep(0.01)

        # --- BYPASS CHANGE ---
        elif line[1:3] == "BY" and settings.CacheState:
            byMsg = ComfortBYBypassActivationReport(line[1:])
            settings.BypassCache[byMsg.zone] = byMsg.state if byMsg.zone <= int(settings.COMFORT_INPUTS) else None

            if byMsg.zone <= int(settings.COMFORT_INPUTS):
                self.publish(settings.ALARMBYPASSTOPIC, byMsg.value, qos=2, retain=True)
                time.sleep(0.01)

        # --- RESET ---
        elif line[1:3] == "RS":
            logger.warning("Reset detected")
            settings.FIRST_LOGIN = True
            self.login()

        else:
            logger.debug("Unhandled line: %s", line)




    # Add the code to publish the maps from the cclx to MQTT - Cytech26
 
    def _publish_meta(self, name: str, payload_obj, qos: int = 1):
        """Publish retained JSON under DOMAIN/meta/<name>."""
        try:
            payload = json.dumps(payload_obj, ensure_ascii=False)
            self.publish(f"{settings.DOMAIN}/meta/{name}", payload, qos=qos, retain=True)
            logger.info("Published meta '%s' (%d bytes)", name, len(payload.encode("utf-8")))
        except Exception as e:
            logger.exception("Failed to publish meta '%s': %s", name, e)


    def publish_all_maps(self):
        """Publish all CCLX-derived maps as retained MQTT metadata."""


        ts = datetime.now().replace(microsecond=0).isoformat()

        self._publish_meta("zones", {
            "time": ts,
            "source": {"cclx_file": settings.COMFORT_CCLX_FILE, "enabled": bool(settings.ZONEMAPFILE)},
            "count": len(settings.input_properties or {}),
            "items": (settings.input_properties or {})
        })

        self._publish_meta("counters", {
            "time": ts,
            "source": {"cclx_file": settings.COMFORT_CCLX_FILE, "enabled": bool(settings.COUNTERMAPFILE)},
            "count": len(settings.counter_properties or {}),
            "items": (settings.counter_properties or {})
        })

        self._publish_meta("flags", {
            "time": ts,
            "source": {"cclx_file": settings.COMFORT_CCLX_FILE, "enabled": bool(settings.FLAGMAPFILE)},
            "count": len(settings.flag_properties or {}),
            "items": (settings.flag_properties or {})
        })

        self._publish_meta("outputs", {
            "time": ts,
            "source": {"cclx_file": settings.COMFORT_CCLX_FILE, "enabled": bool(settings.OUTPUTMAPFILE)},
            "count": len(settings.output_properties or {}),
            "items": (settings.output_properties or {})
        })

        self._publish_meta("sensors", {
            "time": ts,
            "source": {"cclx_file": settings.COMFORT_CCLX_FILE, "enabled": bool(settings.SENSORMAPFILE)},
            "count": len(settings.sensor_properties or {}),
            "items": (settings.sensor_properties or {})
        })


        self._publish_meta("users", {
            "time": ts,
            "source": {"cclx_file": settings.COMFORT_CCLX_FILE, "enabled": bool(settings.USERMAPFILE)},
            "count": len(settings.user_properties or {}),
            "items": (settings.user_properties or {})
        })

        self._publish_meta("timers", {
            "time": ts,
            "source": {"cclx_file": settings.COMFORT_CCLX_FILE, "enabled": bool(settings.TIMERMAPFILE)},
            "count": len(settings.timer_properties or {}),
            "items": (settings.timer_properties or {})
        })

        # Optional: quick index/health topic
        self._publish_meta("summary", {
            "time": ts,
            "cclx_file": settings.COMFORT_CCLX_FILE,
            "enabled": {
                "zones": bool(settings.ZONEMAPFILE),
                "counters": bool(settings.COUNTERMAPFILE),
                "flags": bool(settings.FLAGMAPFILE),
                "outputs": bool(settings.OUTPUTMAPFILE),
                "sensors": bool(settings.SENSORMAPFILE),
                "users": bool(settings.USERMAPFILE),
                "timers": bool(settings.TIMERMAPFILE),
                "devices": bool(settings.DEVICEMAPFILE),
            },
            "counts": {
                "zones": len(settings.input_properties or {}),
                "counters": len(settings.counter_properties or {}),
                "flags": len(settings.flag_properties or {}),
                "outputs": len(settings.output_properties or {}),
                "sensors": len(settings.sensor_properties or {}),
                "users": len(settings.user_properties or {}),
                "timers": len(settings.timer_properties or {}),
            }
        })

mqttc = Comfort2(callback_api_version = mqtt.CallbackAPIVersion.VERSION2, client_id=settings.mqtt_client_id, protocol=mqtt.MQTTv5, transport=settings.MQTTPROTOCOL)


def main():
    global ACTIVE_CLIENT

    MQTT_VERSION = mqtt.MQTTv5

    mqttc = Comfort2(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=settings.mqtt_client_id,
        protocol=MQTT_VERSION,
        transport=settings.MQTTPROTOCOL
    )

    mqttc.init(
        settings.MQTTBROKER,
        settings.MQTTPORT,
        settings.MQTTUSERNAME,
        settings.MQTTPASSWORD,
        settings.COMFORT_LOGIN_ID,
        MQTT_VERSION
    )

    mqttc.run()


if __name__ == "__main__":
    main()



