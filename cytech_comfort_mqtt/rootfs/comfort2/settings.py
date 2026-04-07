import secrets
import logging
from datetime import timedelta
logger = logging.getLogger(__name__)


DOMAIN = "cytech_comfort_mqtt"
ADDON_SLUG = ''
ADDON_VERSION = "N/A"
COMFORT_SERIAL = "00000000"       # Default Serial Number.
COMFORT_KEY = "00000000"          # Default Refresh Key.

RELOADTOPIC = f"{DOMAIN}/reload"         # WebUI -> Bridge
RELOAD_REQUIRE_KEY = False               
RELOAD_COOLDOWN_SECONDS = 5              # prevent accidental spam


SupportedFirmware = float(7.201)  # Minimum Supported firmware.

MAX_ZONES = 96                    # Configurable for future expansion
MAX_OUTPUTS = 96                  # Configurable for future expansion
MAX_RESPONSES = 1024              # Configurable for future expansion
COMFORT_TIMERS = 64               # Default number of timers supported by Comfort II. Max 64.
MAX_FLAGS = 254                   # Configurable for future expansion. Max 254.
MAX_COUNTERS = 255                # Configurable for future expansion. Max 255.
MAX_SENSORS = 32                 # Configurable for future expansion. Max 32.
MAX_TIMERS = 64                  # Configurable for future expansion. Max 64.

BUFFER_SIZE = 4096
COMFORT_BATTERY_STATUS_ID = 1
COMFORT_CCLX_FILE = None    # Path to active CCLX file (set at runtime)

# ============================================================
# MQTT SETTINGS
# ============================================================

lower = 268435456
upper = 4294967295
rand_int = lower + secrets.randbelow(upper - lower + 1)
rand_hex_str = hex(rand_int)
mqtt_client_id = DOMAIN+"-"+str(rand_hex_str[2:])       # Generate pseudo random client-id each time it starts.

MQTTBROKER = "core-mosquitto"
MQTTBROKERIP = None
MQTTPORT = 1883

MQTTUSERNAME = None
MQTTPASSWORD = None

MQTTPROTOCOL = "TCP"


LOG_VERBOSITY = "INFO"

# Alarm state (used by M?/MD/S? handlers)
ALARMSTATE = 0

# Command / retry timing
SAVEDTIME = None        # datetime when last command sent
TIMEOUT = timedelta(seconds=30)                         
RETRY = timedelta(seconds=10)

# Runtime-configured values (set by bridge.py at startup)
COMFORT_INPUTS = 0
COMFORT_OUTPUTS = 0
COMFORT_RESPONSES = 0
UI_FLAG_COUNT = 0
UI_COUNTER_COUNT = 0
UI_TIMER_COUNT = 0
UI_SENSOR_COUNT = 0

REFRESHTOPIC = DOMAIN+"/alarm/refresh"                  # Use this topic to refresh objects. Not a full Reload but request Update-All from Addon. Use 'key' for auth.
BATTERYREFRESHTOPIC = DOMAIN+"/alarm/battery_update"    # Used to request Battery and DC Supply voltage updates. To be used by HA Automation for periodic polling.
BATTERYSTATUSTOPIC = DOMAIN+"/alarm/battery_status"     # List of Battery and DC Supply Output Status.

ALARMSTATETOPIC = DOMAIN+"/alarm"
ALARMSTATUSTOPIC = DOMAIN+"/alarm/status"
ALARMBYPASSTOPIC = DOMAIN+"/alarm/bypass"               # List of Bypassed Zones.
ALARMCONNECTEDTOPIC = DOMAIN+"/alarm/connected"
ALARMMODETOPIC = DOMAIN+"/alarm/mode"                   # Integer value of current Mode. See M? and MD.

ALARMCOMMANDTOPIC = DOMAIN+"/alarm/set"
ALARMAVAILABLETOPIC = DOMAIN+"/alarm/online"
ALARMLWTTOPIC = DOMAIN+"/alarm/LWT"
ALARMMESSAGETOPIC = DOMAIN+"/alarm/message"
ALARMTIMERTOPIC = DOMAIN+"/alarm/timer"
ALARMDOORBELLTOPIC = DOMAIN+"/alarm/doorbell"

ALARMLOGTOPIC = DOMAIN + "/alarm/log"
ALARMLOGCLEARTOPIC = DOMAIN + "/alarm/log/clear"

ALARMINPUTTOPIC = DOMAIN+"/input%d"        
ALARMINPUTCOMMANDTOPIC = DOMAIN+"/input%d/set"  

ALARMOUTPUTTOPIC = DOMAIN+"/output%d"   
ALARMOUTPUTCOMMANDTOPIC = DOMAIN+"/output%d/set"

ALARMRESPONSECOMMANDTOPIC = DOMAIN+"/response%d/set" 

ALARMNUMBEROFFLAGS = 254                                # Max Flags for system
ALARMFLAGTOPIC = DOMAIN+"/flag%d"                       #flag1,flag2,...flag254
ALARMFLAGCOMMANDTOPIC = DOMAIN+"/flag%d/set"            #flag1/set,flag2/set,... flag254/set

ALARMNUMBEROFSENSORS = 32                               # Use system default = 32 (0-31)
ALARMSENSORTOPIC = DOMAIN+"/sensor%d"                   #sensor0,sensor1,...sensor31
ALARMSENSORCOMMANDTOPIC = DOMAIN+"/sensor%d/set"        #sensor0,sensor1,...sensor31

ALARMNUMBEROFCOUNTERS = 255                             # Hardcoded to 255
ALARMCOUNTERTOPIC = DOMAIN+"/counter%d"                 # each counter represents a value EG. light level
ALARMCOUNTERCOMMANDTOPIC = DOMAIN+"/counter%d/set"      # set the counter to a value for between 0 (off) to 255 (full on) or any signed 16-bit value.

COMFORTTIMERSTOPIC = DOMAIN+"/timer%d"                  #timer1,timer2,...sensor64


FIRST_LOGIN = False         # Don't scan Comfort until MQTT connection is made.
RUN = True
BYPASSEDZONES = []          # Global list of Bypassed Zones
BROKERCONNECTED = False     # MQTT Broker Status
COMFORTCONNECTED = False    # Comfort LAN connection Status
ZONEMAPFILE = False         # CCLX file present or not.
OUTPUTMAPFILE = False
COUNTERMAPFILE = False
SENSORMAPFILE = False
FLAGMAPFILE = False
DEVICEMAPFILE = False
USERMAPFILE = False
TIMERMAPFILE = False

# -------------------------------------------------------------------
# Enrichment dictionaries (from CCLX / description files)
# Must exist even if files are not present
# -------------------------------------------------------------------
device_properties = {}
input_properties = {}
output_properties = {}
counter_properties = {}
sensor_properties = {}
flag_properties = {}
user_properties = {}
timer_properties = {}

file_exists  = False
ACFail = False              # Indicates ACFail status.

device_properties['CPUType'] = "N/A"
device_properties['Version'] = "N/A"
device_properties['BatteryVoltageMain'] = "-1"
device_properties['BatteryVoltageSlave1'] = "-1"
device_properties['BatteryVoltageSlave2'] = "-1"
device_properties['BatteryVoltageSlave3'] = "-1"
device_properties['BatteryVoltageSlave4'] = "-1"
device_properties['BatteryVoltageSlave5'] = "-1"
device_properties['BatteryVoltageSlave6'] = "-1"    # Experimental
device_properties['BatteryVoltageSlave7'] = "-1"    # Experimental
device_properties['ChargeVoltageMain'] = "-1"
device_properties['ChargeVoltageSlave1'] = "-1"
device_properties['ChargeVoltageSlave2'] = "-1"
device_properties['ChargeVoltageSlave3'] = "-1"
device_properties['ChargeVoltageSlave4'] = "-1"
device_properties['ChargeVoltageSlave5'] = "-1"
device_properties['ChargeVoltageSlave6'] = "-1"    # Experimental
device_properties['ChargeVoltageSlave7'] = "-1"    # Experimental
device_properties['ComfortHardwareModel'] = "CM9000-ULT"
device_properties['sem_id'] = 0
device_properties['SerialNumber'] = "00000000"
device_properties['BatteryStatus'] = "N/A"
device_properties['ChargerStatus'] = "N/A"
device_properties['BridgeConnected'] = 0
device_properties['CustomerName'] = None
device_properties['Reference'] = None
device_properties['Version'] = None
device_properties['ComfortFileSystem'] = None
device_properties['ComfortFirmwareType'] = None

# Comfort FileSystem values and Model Numbers
models = {34: "Comfort II ULTRA",
          31: "Comfort II Optimum",
          36: "Logic Engine",
          37: "EMS",
          38: "EMS2",
          39: "KS",
          35: "CM9001-EX",
          30: "Comfort II SPC",
          18: "Comfort I PRO (Obsolete)",
          17: "Comfort I ENTRY (Obsolete)",
          24: "Comfort I ULTRA (Obsolete)"
        }

# Includes possible future expansion to 7 Slaves.
BatterySlaveIDs = {1:"BatteryVoltageMain",
          33:"BatteryVoltageSlave1",
          34:"BatteryVoltageSlave2",
          35:"BatteryVoltageSlave3",
          36:"BatteryVoltageSlave4",
          37:"BatteryVoltageSlave5",
          38:"BatteryVoltageSlave6",
          39:"BatteryVoltageSlave7"
}
ChargerSlaveIDs = {1:"ChargeVoltageMain",
          33:"ChargeVoltageSlave1",
          34:"ChargeVoltageSlave2",
          35:"ChargeVoltageSlave3",
          36:"ChargeVoltageSlave4",
          37:"ChargeVoltageSlave5",
          38:"ChargeVoltageSlave6",
          39:"ChargeVoltageSlave7"

}

BatteryVoltageNameList = {0:"BatteryVoltageMain",
                      1:"BatteryVoltageSlave1",
                      2:"BatteryVoltageSlave2",
                      3:"BatteryVoltageSlave3",
                      4:"BatteryVoltageSlave4",
                      5:"BatteryVoltageSlave5",
                      6:"BatteryVoltageSlave6",
                      7:"BatteryVoltageSlave7"
}
ChargerVoltageNameList = {0:"ChargeVoltageMain",
                      1:"ChargeVoltageSlave1",
                      2:"ChargeVoltageSlave2",
                      3:"ChargeVoltageSlave3",
                      4:"ChargeVoltageSlave4",
                      5:"ChargeVoltageSlave5",
                      6:"ChargeVoltageSlave6",
                      7:"ChargeVoltageSlave7"
}

BatteryVoltageList = {0:"-1",
                      1:"-1",
                      2:"-1",
                      3:"-1",
                      4:"-1",
                      5:"-1",
                      6:"-1",
                      7:"-1"
}
ChargerVoltageList = {0:"-1",
                      1:"-1",
                      2:"-1",
                      3:"-1",
                      4:"-1",
                      5:"-1",
                      6:"-1",
                      7:"-1"
}

ZoneCache = {}              # Zone Cache dictionary.
#BypassCache = {}            # Zone Bypass Cache dictionary.
BypassCache = {i: 0 for i in range(1,MAX_ZONES + 1)}   # generate empty bypass cache for all zones. (Up to MAX_ZONES)
CacheState = False          # Initial Cache state. False when not in sync with Bypass Zones (b?). True, when in Sync.

