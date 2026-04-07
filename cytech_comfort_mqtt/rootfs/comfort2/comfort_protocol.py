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

import settings
import logging
logger = logging.getLogger(__name__)


class ComfortLUUserLoggedIn(object):
    def __init__(self, datastr="", user=1):             
        if datastr:
            self.user = int(datastr[2:4], 16)
            self.method = "Unknown"
            if len(datastr) == 6:
                try:
                    _method = int(datastr[4:6], 16)
                except ValueError:
                    _method = 0
                self.method = "Local Phone" if _method == 1 else \
                              "Remote Phone" if _method == 2 else \
                             f"Keypad {_method - 64}" if 65 <= _method <= 72 else \
                             f"UCM {_method - 16}" if 17 <= _method <= 24 else \
                              "Unknown"
        else:
            self.user = int(user)
            self.method = "Unknown"

class ComfortIPInputActivationReport(object):
    def __init__(self, datastr="", input=0, state=0):
        if datastr:
            self.input = int(datastr[2:4], 16)
            self.state = int(datastr[4:6], 16)
        else:
            self.input = int(input)
            self.state = int(state)

class ComfortCTCounterActivationReport(object): # in format CT1EFF00 ie CT (counter) 1E = 30; state FF00 = 65280
    def __init__(self, datastr="", counter=0, value=0, state=0):
        if datastr:
            self.counter = int(datastr[2:4], 16)    #Integer value 3
            self.value = self.ComfortSigned16(int("%s%s" % (datastr[6:8], datastr[4:6]),16))            # Use new 16-bit format
            self.state = self.state = 1 if (int(datastr[4:6],16) > 0) else 0                            # 8-bit value used for state
        else:
            self.counter = counter
            self.value = value
            self.state = state

    def ComfortSigned16(self,value):                                            # Returns signed 16-bit value where required.
        return -(value & 0x8000) | (value & 0x7fff)
    
    ### Byte-Swap code below ###
    def HexToSigned16Decimal(self,value):                                       # Returns Signed Decimal value from HEX string EG. FFFF = -1
        return -(int(value,16) & 0x8000) | (int(value,16) & 0x7fff)

    def byte_swap_16_bit(self, hex_string):
        # Ensure the string is prefixed with '0x' for hex conversion            # Trying to cleanup strings.
        if not hex_string.startswith('0x'):
            hex_string = '0x' + hex_string
    
        # Convert hex string to integer
        value = int(hex_string, 16)
    
        # Perform byte swapping
        swapped_value = ((value << 8) & 0xFF00) | ((value >> 8) & 0x00FF)
    
        # Convert back to hex string, remove the leading '0x' and return 16-bit number.
        return hex(swapped_value)

class ComfortTRReport(object):
    def __init__(self, datastr="", timer=1, value=0, state=0):
        if datastr:
            self.timer = int(datastr[2:4], 16)    #Integer value 3
            self.value = self.ComfortSigned16(int("%s%s" % (datastr[6:8], datastr[4:6]),16))            # Use new 16-bit format
            self.state = 1 if (int(self.value) > 0) else 0                          
        else:
            self.timer = timer
            self.value = value
            self.state = state

    def ComfortSigned16(self,value):                                            # Returns signed 16-bit value where required.
        return -(value & 0x8000) | (value & 0x7fff)
    
    ### Byte-Swap code below ###
    def HexToSigned16Decimal(self,value):                                       # Returns Signed Decimal value from HEX string EG. FFFF = -1
        return -(int(value,16) & 0x8000) | (int(value,16) & 0x7fff)

    def byte_swap_16_bit(self, hex_string):
        # Ensure the string is prefixed with '0x' for hex conversion            # Trying to cleanup strings.
        if not hex_string.startswith('0x'):
            hex_string = '0x' + hex_string
    
        # Convert hex string to integer
        value = int(hex_string, 16)
    
        # Perform byte swapping
        swapped_value = ((value << 8) & 0xFF00) | ((value >> 8) & 0x00FF)
    
        # Convert back to hex string, remove the leading '0x' and return 16-bit number.
        return hex(swapped_value)
    
class ComfortOPOutputActivationReport(object):
    def __init__(self, datastr="", output=0, state=0):
        if datastr:
            self.output = int(datastr[2:4], 16)
            self.state = int(datastr[4:6], 16)
        else:
            self.output = int(output)
            self.state = int(state)

class ComfortFLFlagActivationReport(object):
    def __init__(self, datastr="", flag=1, state=0):
        if datastr:
            self.flag = int(datastr[2:4], 16)
            self.state = int(datastr[4:6], 16)
        else:
            self.flag = int(flag)
            self.state = int(state)

class ComfortBYBypassActivationReport(object):


    def __init__(self, datastr="", zone="0", state="0"):
        if datastr:
            self.zone = int(datastr[2:4],16)
            self.state = int(datastr[4:6],16)
        else:
            self.zone = int(zone,16)
            self.state = int(state,16)

        if (self.state == 0) and (self.zone <= int(settings.COMFORT_INPUTS)):
            if (self.zone in settings.BYPASSEDZONES):
                settings.BYPASSEDZONES.remove(self.zone)
                if settings.BYPASSEDZONES.count(-1) == 0 and len(settings.BYPASSEDZONES) == 0:
                    settings.BYPASSEDZONES.append(0)        
            else:
                logger.debug("ValueError Exception: Bypassed Zone (%s) does not appear in settings.BYPASSEDZONES List[]", self.zone)
        elif (self.state == 1) and (self.zone <= int(settings.COMFORT_INPUTS)):                     # State == 1 meaning must be in bypasszones
            if (self.zone not in settings.BYPASSEDZONES):
                settings.BYPASSEDZONES.append(self.zone)
            if settings.BYPASSEDZONES.count(0) >= 1:        
                settings.BYPASSEDZONES.remove(0)

        settings.BYPASSEDZONES.sort(reverse=False)
        result_string = ','.join(map(str, settings.BYPASSEDZONES))
        self.value = result_string

class ComfortZ_ReportAllZones(object):
    def __init__(self, data={}):


        self.inputs = []
        b = (len(data) - 2) // 2            #variable number of zones reported
        self.max_zones = b * 8
        for i in range(1,b+1):
            inputbits = int(data[2*i:2*i+2],16)
            for j in range(0,8):
                self.inputs.append(ComfortIPInputActivationReport("", 8*(i-1)+1+j,(inputbits>>j) & 1))
                settings.ZoneCache[8*(i-1)+1+j] = (inputbits>>j) & 1


class Comfort_RSensorActivationReport(object):
    def __init__(self, datastr="", sensor=0, state=0):
        if datastr:
            self.sensor = int(datastr[2:4], 16)
            self.value = self.ComfortSigned16(int("%s%s" % (datastr[6:8], datastr[4:6]),16))    # Use new 16-bit format
        else:
            self.sensor = sensor
            self.value = state

    def ComfortSigned16(self,value):        # Returns signed 16-bit value where required.
        return -(value & 0x8000) | (value & 0x7fff)

class Comfort_R_ReportAllSensors(object):
    def __init__(self, data={}, sensor=0, value=0, counter=0, state=0):
        self.sensors = []
        self.counters = []
        b = (len(data) - 8) // 4             #Fixed number of sensors reported from r?01 command. 0-15 and 16-31.
        self.RegisterStart = int(data[4:6],16)
        self.RegisterType = int(data[2:4],16)
        for i in range(0,b):
            if self.RegisterType == 1:  #Sensor
                sensorbits = data[8+(4*i):8+(4*i)+4]
                #Swap bits here.
                #Change to Signed value here.
                self.value = int((sensorbits[2:4] + sensorbits[0:2]),16)
                self.sensor =  self.RegisterStart+i
                self.sensors.append(Comfort_RSensorActivationReport("", self.RegisterStart+i, self.value))
            else:
                counterbits = data[8+(4*i):8+(4*i)+4]   #0000
                self.value = int((counterbits[2:4] + counterbits[0:2]),16)
                self.state = 1 if (int(counterbits[0:2],16) > 0) else 0
                self.counter = self.RegisterStart+i
                self.counters.append(ComfortCTCounterActivationReport("", self.RegisterStart+i, self.value, self.state))
    
    def ComfortSigned16(self,value):     # Returns signed 16-bit value from HEX value.
        return -(value & 0x8000) | (value & 0x7fff)


class ComfortY_ReportAllOutputs(object):
    def __init__(self, data={}):
        self.outputs = []
        b = (len(data) - 2) // 2   #variable number of outputs reported
        self.max_zones = b * 8
        for i in range(1,b+1):
            outputbits = int(data[2*i:2*i+2],16)
            for j in range(0,8):
                self.outputs.append(ComfortOPOutputActivationReport("", 8*(i-1)+1+j,(outputbits>>j) & 1))

class Comfort_Y_ReportAllOutputs(object): 
    def __init__(self, data={}):    
        self.outputs = []           
        b = (len(data) - 2) // 2   #variable number of outputs reported
        self.max_zones = b * 8
        for i in range(1,b+1):  
            outputbits = int(data[2*i:2*i+2],16)
            for j in range(0,8):
                self.outputs.append(ComfortOPOutputActivationReport("", 128+8*(i-1)+1+j,(outputbits>>j) & 1))

class ComfortB_ReportAllBypassZones(object):

    def __init__(self, data={}):


        settings.BYPASSEDZONES.clear()       #Clear contents and rebuild again.
        source_length = (len(data[4:]) * 4)    #96
        # Convert the string to a hexadecimal value
        source_hex = int(data[4:], 16)
        # Convert the hex number to binary string
        binary_number = bin(source_hex)[2:].zfill(source_length)  # Convert to binary and zero-fill to 24 bits indicating all zones
        # Determine the length of the binary number
        num_bits = len(binary_number)   #96
        # Extract 8-bit segments from the binary number
        eight_bit_segments = [binary_number[i:i+8] for i in range(0, num_bits, 8)]
        self.zones = []
        for i, segment in enumerate(eight_bit_segments, start=0):
            start_zone = 1 + (8 * i)
            for j in range(1, 9):   # Zone 1 to 8
                if (start_zone + j - 1) < 129:     # Max 128 zones
                    zone_number = int(start_zone + j - 1)
                    zone_state = int(segment[8 - j],2)
                    settings.BypassCache[zone_number] = zone_state   # Populate Cache on startup.
                    if zone_state == 1 and zone_number <= int(settings.COMFORT_INPUTS):       # Was 128, now configured Zones.
                        settings.BYPASSEDZONES.append(zone_number)
                        self.zones.append(ComfortBYBypassActivationReport("", hex(zone_number), hex(zone_state)))
        settings.CacheState = True

        if len(settings.BYPASSEDZONES) == 0:
            settings.BYPASSEDZONES.append(0)

        result_string = ','.join(map(str, settings.BYPASSEDZONES))
        self.value = result_string

class Comfortf_ReportAllFlags(object):
    def __init__(self, data={}):
        self.flags = []         
        source_length = (len(data) * 4 - 16)

        # Convert the string to a hexadecimal value
        source_hex = int(data[4:], 16)
        # Convert the hex number to binary string
        binary_number = bin(source_hex)[2:].zfill(source_length)  # Convert to binary and zero-fill to 24 bits
        # Determine the length of the binary number
        num_bits = len(binary_number)
        # Extract 8-bit segments from the binary number
        eight_bit_segments = [binary_number[i:i+8] for i in range(0, num_bits, 8)]
        for i, segment in enumerate(eight_bit_segments, start=0):
            # Adjust flag numbering for subsequent iterations
            start_flag = 1 + (8 * i)
            # Extract individual bit values and assign to flags
            flags = {}
            for j in range(1, 9):   # Flag 1 to 8 (Saved as 0 - 7)
                if (start_flag + j - 1) < 255:
                    flag_name = "flag" + str(start_flag + j - 1)
                    flags[flag_name] = int(segment[8 - j],2)
                    self.flags.append(ComfortFLFlagActivationReport("", int(start_flag + j - 1),int(segment[8 - j],2) & 1))
            

#mode = { 00=Off, 01=Away, 02=Night, 03=Day, 04=Vacation }
class ComfortM_SecurityModeReport(object):
    def __init__(self, data={}):
        self.mode = int(data[2:4],16)
        if self.mode == 0: self.modename = "disarmed"; logger.info("Security Off")
        elif self.mode == 1: self.modename = "armed_away"; logger.info("Armed Away Mode")
        elif self.mode == 2: self.modename = "armed_night"; logger.info("Armed Night Mode")
        elif self.mode == 3: self.modename = "armed_home"; logger.info("Armed Day Mode")
        elif self.mode == 4: self.modename = "armed_vacation"; logger.info("Armed Vacation Mode")
        else: self.modename = "Unknown"; logger.info("Unknown Mode")

#nn 00 = Idle, 1 = Trouble, 2 = Alert, 3 = Alarm
class ComfortS_SecurityModeReport(object):
    def __init__(self, data={}):
        self.mode = int(data[2:4],16)
        if self.mode == 0: self.modename = "Idle"
        elif self.mode == 1: self.modename = "Trouble"
        elif self.mode == 2: self.modename = "Alert"
        elif self.mode == 3: self.modename = "Alarm"
        else: self.modename = "Unknown"     # Should never happen.

#zone = 00 means system can be armed, no open zones
class ComfortERArmReadyNotReady(object):
    def __init__(self, data={}):
        self.zone = int(data[2:4],16)

class ComfortAMSystemAlarmReport(object):
    def __init__(self, data={}):
        

        self.alarm = int(data[2:4],16)
        self.triggered = True               # For Comfort Alarm State Alert, Trouble, Alarm
        self.parameter = int(data[4:6],16)
        low_battery = ['','Slave 1','Slave 2','Slave 3','Slave 4','Slave 5','Slave 6','Slave 7']
        if settings.ZONEMAPFILE:
            if self.alarm == 0: self.message = "Intruder, Zone "+str(self.parameter)+" ("+ str(settings.input_properties[str(self.parameter)]['Name'])+")"
            elif self.alarm == 1: self.message = str(settings.input_properties[str(self.parameter)]['Name'])+" Trouble"
            elif self.alarm == 2: self.message = "Low Battery - "+('Main' if self.parameter == 1 else low_battery[(self.parameter - 32)])
            elif self.alarm == 3: 
                self.message = "Power Failure - "+('Main' if self.parameter == 1 else low_battery[(self.parameter - 32)])
                ACFail = True
            elif self.alarm == 4: self.message = "Phone Trouble"
            elif self.alarm == 5: self.message = "Duress"
            elif self.alarm == 6: self.message = "Arm Failure"
            elif self.alarm == 7: self.message = "Family Care"
            elif self.alarm == 8: self.message = "Security Off, User "+str(self.parameter); self.triggered = False
            elif self.alarm == 9: self.message = "System Armed, User "+str(self.parameter); self.triggered = False
            elif self.alarm == 10: self.message = "Tamper "+str(self.parameter)
            elif self.alarm == 12: self.message = "Entry Warning, Zone "+str(self.parameter)+" ("+str(settings.input_properties[str(self.parameter)]['Name'])+")"; self.triggered = False
            elif self.alarm == 13: self.message = "Alarm Abort"; self.triggered = False
            elif self.alarm == 14: self.message = "Siren Tamper"
            elif self.alarm == 15: self.message = "Bypass, Zone "+str(self.parameter)+" ("+str(settings.input_properties[str(self.parameter)]['Name'])+")"; self.triggered = False
            elif self.alarm == 17: self.message = "Dial Test, User "+str(self.parameter); self.triggered = False
            elif self.alarm == 19: self.message = "Entry Alert, Zone "+str(self.parameter)+" ("+str(settings.input_properties[str(self.parameter)]['Name'])+")"; self.triggered = False
            elif self.alarm == 20: self.message = "Fire"
            elif self.alarm == 21: self.message = "Panic"
            elif self.alarm == 22: self.message = "GSM Trouble "+str(self.parameter)
            elif self.alarm == 23: self.message = "New Message, User "+str(self.parameter); self.triggered = False
            elif self.alarm == 24: self.message = "Doorbell "+str(self.parameter); self.triggered = False
            elif self.alarm == 25: self.message = "Comms Failure RS485 id "+str(self.parameter)
            elif self.alarm == 26: self.message = "Signin Tamper "+str(self.parameter)
            else: self.message = "Unknown("+str(self.alarm)+")"
        else:
            if self.alarm == 0: self.message = "Intruder, Zone "+str(self.parameter)
            elif self.alarm == 1: self.message = "Zone "+str(self.parameter)+" Trouble"
            elif self.alarm == 2: self.message = "Low Battery - "+('Main' if self.parameter == 1 else low_battery[(self.parameter - 32)])
            elif self.alarm == 3: 
                self.message = "Power Failure - "+('Main' if self.parameter == 1 else low_battery[(self.parameter - 32)])
                ACFail = True
            elif self.alarm == 4: self.message = "Phone Trouble"
            elif self.alarm == 5: self.message = "Duress"
            elif self.alarm == 6: self.message = "Arm Failure"
            elif self.alarm == 7: self.message = "Family Care"
            elif self.alarm == 8: self.message = "Security Off, User "+str(self.parameter); self.triggered = False
            elif self.alarm == 9: self.message = "System Armed, User "+str(self.parameter); self.triggered = False
            elif self.alarm == 10: self.message = "Tamper "+str(self.parameter)
            elif self.alarm == 12: self.message = "Entry Warning, Zone "+str(self.parameter); self.triggered = False
            elif self.alarm == 13: self.message = "Alarm Abort"; self.triggered = False
            elif self.alarm == 14: self.message = "Siren Tamper"
            elif self.alarm == 15: self.message = "Bypass, Zone "+str(self.parameter); self.triggered = False
            elif self.alarm == 17: self.message = "Dial Test, User "+str(self.parameter); self.triggered = False
            elif self.alarm == 19: self.message = "Entry Alert, Zone "+str(self.parameter); self.triggered = False
            elif self.alarm == 20: self.message = "Fire"
            elif self.alarm == 21: self.message = "Panic"
            elif self.alarm == 22: self.message = "GSM Trouble "+str(self.parameter)
            elif self.alarm == 23: self.message = "New Message, User "+str(self.parameter); self.triggered = False
            elif self.alarm == 24: self.message = "Doorbell "+str(self.parameter); self.triggered = False
            elif self.alarm == 25: self.message = "Comms Failure RS485 id "+str(self.parameter)
            elif self.alarm == 26: self.message = "Signin Tamper "+str(self.parameter)
            else: self.message = "Unknown("+str(self.alarm)+")"

class ComfortALSystemAlarmReport(object):
    def __init__(self, data={}):
  

        self.priority = settings.ALARMSTATE # Numerical value for state. 0=Idle, 1=Trouble, 2=Alert, 3=Alarm
        self.alarm = int(data[2:4],16)
        self.triggered = True               # For Comfort Alarm State Alert, Trouble, Alarm
        self.state = int(data[6:8],16)
        low_battery = ['','Slave 1','Slave 2','Slave 3','Slave 4','Slave 5','Slave 6','Slave 7']
        alarm_types = ['No Alarm','Intruder Alarm','Duress','Phone Line Trouble','Arm Fail','Zone Trouble','Zone Alert','Low Battery',
                       'Power Fail','Panic','Entry Alert','Tamper','Fire','Gas','Family Care','Perimeter Alert','Bypass Zone','System Disarmed',
                       'CMS Test','System Armed','Alarm Abort','Entry Warning','Siren Trouble','Unused','RS485 Comms Fail','Doorbell','Homesafe',
                       'Dial Test','SMS Trouble','New Message','Engineer Sign in','Sign-in Tamper']
        if self.state > self.priority:
            self.priority = self.state
            ALARMSTATE = self.state  # Save new state
        elif self.state == 0:
            settings.ALARMSTATE = 0


class Comfort_A_SecurityInformationReport(object):      #  For future development !!!
    #a?000000000000000000
    def __init__(self, data={}):
            

        self.AA = int(data[2:4],16)     #AA is the current Alarm Type 01 to 1FH (Defaults can be changed in Comfigurator)
        self.SS = int(data[4:6],16)     #SS is alarm state 0-3 (Idle, Trouble, Alert, Alarm)
        self.XX = int(data[6:8],16)     #XX is Trouble bits
        self.YY = int(data[8:10],16)    #YY is for Spare Trouble Bits, 0 if unused
        self.BB = int(data[10:12],16)   #BB = Low Battery ID = 1 for Comfort or none
        self.zz = int(data[12:14],16)   #zz = Zone Trouble number, =0 if none
        self.RR = int(data[14:16],16)   #RR = RS485 Trouble ID, = 0 if none
        self.TT = int(data[16:18],16)   #TT = Tamper ID = 0 if none
        self.GG = int(data[18:20],16)   #GG = GSM ID =0 if no trouble
        alarm_type = ['','Intruder','Duress','LineCut','ArmFail','ZoneTrouble','ZoneAlert','LowBattery', 'PowerFail', 'Panic', 'EntryAlert', \
                      'Tamper','Fire','Gas','FamilyCare','Perimeter', 'BypassZone','Disarm','CMSTest','SystemArmed', 'AlarmAbort', 'EntryWarning', \
                      'SirenTrouble','AlarmType23', 'RS485Comms','Doorbell','HomeSafe','DialTest','AlarmType28','NewMessage','Temperature','SigninTamper']
        alarm_state = ['Idle','Trouble','Alert','Alarm']
        low_battery = ['', 'Main','Slave 1','Slave 2','Slave 3','Slave 4','Slave 5','Slave 6','Slave 7']
        troublebits = ['AC Failure','Low Battery','Zone Trouble','RS485 Comms Fail','Tamper','Phone Trouble','GSM Trouble','Unknown']
        self.type = alarm_type[self.AA]
        self.state = alarm_state[self.SS]
        #self.battery = None
        self.acfail = (int(data[6:8],16) >> 0) & 1   #XX = AC Fail, bit 0. 0=AC OK, 1=AC Fail
        if self.acfail == 1: 
            ACFail = True
        elif self.acfail == 0: 
            ACFail = False
        if self.type == "LowBattery" and self.BB <= 1: self.battery = low_battery[1]
        #elif self.type == "LowBattery" and self.BB - 31 in low_battery:self.battery = low_battery[(self.BB - 31)]
        elif self.type == "LowBattery" and 0 <= (self.BB - 31) < len(low_battery):self.battery = low_battery[self.BB - 31]
        else:self.battery = "Unknown"

class ComfortARSystemAlarmReport(object):
    def __init__(self, data={}):

        self.alarm = int(data[2:4],16)
        self.triggered = True   #for comfort alarm state Alert, Trouble, Alarm
        self.parameter = int(data[4:6],16)
        low_battery = ['','Slave 1','Slave 2','Slave 3','Slave 4','Slave 5','Slave 6','Slave 7']
        if settings.ZONEMAPFILE:
            if self.alarm == 1: self.message = str(settings.input_properties[str(self.parameter)]['Name'])+" Trouble Restore"
            elif self.alarm == 2: self.message = "Low Battery - "+('Main' if self.parameter == 1 else low_battery[(self.parameter - 32)])+" Restore"
            elif self.alarm == 3: 
                self.message = "Power Failure - "+('Main' if self.parameter == 1 else low_battery[(self.parameter - 32)])+" Restore"
                ACFail = False
            elif self.alarm == 4: self.message = "Phone Trouble"+" Restore"
            elif self.alarm == 10: self.message = "Tamper "+str(self.parameter)+" Restore"
            elif self.alarm == 14: self.message = "Siren Tamper"+" Restore"
            elif self.alarm == 22: self.message = "GSM Trouble "+str(self.parameter)+" Restore"
            elif self.alarm == 25: self.message = "Comms Failure RS485 id"+str(self.parameter)+" Restore"
            else: self.message = "Unknown("+str(self.alarm)+")"
        else:
            if self.alarm == 1: self.message = "Zone "+str(self.parameter)+" Trouble"+" Restore"
            elif self.alarm == 2: self.message = "Low Battery - "+('Main' if self.parameter == 1 else low_battery[(self.parameter - 32)])+" Restore"
            elif self.alarm == 3: 
                self.message = "Power Failure - "+('Main' if self.parameter == 1 else low_battery[(self.parameter - 32)])+" Restore"
                ACFail = False
            elif self.alarm == 4: self.message = "Phone Trouble"+" Restore"
            elif self.alarm == 10: self.message = "Tamper "+str(self.parameter)+" Restore"
            elif self.alarm == 14: self.message = "Siren Tamper"+" Restore"
            elif self.alarm == 22: self.message = "GSM Trouble "+str(self.parameter)+" Restore"
            elif self.alarm == 25: self.message = "Comms Failure RS485 id"+str(self.parameter)+" Restore"
            else: self.message = "Unknown("+str(self.alarm)+")"


class ComfortV_SystemTypeReport(object):
    def __init__(self, data={}):
        self.filesystem = int(data[8:10],16)    # 34 for Ultra II
        self.version = int(data[4:6],16)        # 7.
        self.revision = int(data[6:8],16)       # .210
        self.firmware = int(data[2:4],16)       # 254

class Comfort_U_SystemCPUTypeReport(object):


    
    def __init__(self, data={}):
       
        self.cputype = "N/A"

        if len(data) < 14:
            self.cputype = "N/A"
        else:
            identifier = int(data[12:14],16)
            if identifier == 1:
                self.cputype = "ARM"
            elif identifier == 0:
                self.cputype = "Toshiba"


class Comfort_EL_HardwareModelReport(object):
    def __init__(self, data={}):


        self.hardwaremodel = "N/A"
        if len(data) < 14:
            self.hardwaremodel = "N/A"
        else:
            for i in range(4,len(data),2):
                if data[i:i+2] == 'FF':
                    settings.device_properties['sem_id'] = int(i/2-2)
                    logging.debug("%s Installed SEM(s) detected", str(settings.device_properties['sem_id']))
                    break
            identifier = int(data[3:4],16)
            if identifier == 1:
                if int(settings.device_properties['ComfortFileSystem']) == 34:
                    self.hardwaremodel = "CM9000-ULT"
                elif int(settings.device_properties['ComfortFileSystem']) == 31:
                    self.hardwaremodel = "CM9000-OPT"
                else:
                    self.hardwaremodel = settings.models[int(settings.device_properties['ComfortFileSystem'])]
            elif identifier == 0:
                if int(settings.device_properties['ComfortFileSystem']) == 34:
                    self.hardwaremodel = "CM9001-ULT"
                elif int(settings.device_properties['ComfortFileSystem']) == 31:
                    self.hardwaremodel = "CM9001-OPT"
                else:
                    self.hardwaremodel = settings.models[int(settings.device_properties['ComfortFileSystem'])]

class Comfort_D_SystemVoltageReport(object):
    def __init__(self, data={}):

        if len(data) < 6:
            return
        query_type = int(data[4:6],16)
        id = int(data[2:4],16)

        for x in range(6, len(data), 2):
            value = int(data[x:x+2],16)

            if query_type == 2 and value > 10:      # Set to a value larger than 0V to indicate AC Ok.
                settings.ACFail = False

            #voltage = str(format(round(((value/255)*15.5),2), ".2f")) if value < 255 else '-1'  # Old Formula used for Batteries.
            #voltage = str(format(round(((value/255)*(3.3/2.71)*15),2), ".2f")) if value < 255 else '-1'  # New Formula used for DC Supply voltage.
            if query_type == 1:
                #voltage = str(format(round(((value/255)*15.522),2), ".2f")) if value < 255 else '-1'  # Formula used for Batteries.
                if settings.ACFail == False:
                    voltage = str(format(round((value / 256) * 15.5, 2), ".2f")) if 0 <= value <= 255 else "-1"
                   # voltage =  str(format(round(((value/255)*(3.3/2.7)*12.7 - 0.75),2), ".2f")) if value < 255 else '-1'  # - testing.
                else:
                    voltage = str(format(round((value / 256) * 15.5, 2), ".2f")) if 0 <= value <= 255 else "-1"
                   # voltage =  str(format(round(((value/255)*(3.3/2.7)*12.7 + 0.35),2), ".2f")) if value < 255 else '-1'  # - testing.

                #voltage = str(format(round(((value/255)*15.5),2), ".2f")) if value < 255 else '-1'  # Formula used for Batteries.
                if id == 0:
                    settings.device_properties[settings.BatteryVoltageNameList[(x-6)/2]] = voltage
                    settings.BatteryVoltageList[(x-6)/2] = voltage
                elif (id == 1 or id > 32) and id <= 39:
                    settings.device_properties[settings.BatterySlaveIDs[id]] = voltage
                    id = (id - 32) if id > 1 else 0
                    settings.BatteryVoltageList[id] = voltage
                else:
                    return
            elif query_type == 2:
                #voltage = str(format(round(((value/255)*(3.3/2.71)*15),2), ".2f")) if value < 255 else '-1'  # New Formula used for DC Supply voltage.
                voltage = str(format(round((value / 256) * 15.5, 2), ".2f")) if 0 <= value <= 255 else "-1"
                # voltage =  str(format(round(((value/255)*(3.3/2.7)*14.9),2), ".2f")) if value < 255 else '-1'  # New Formula used for DC Supply voltage - testing.
                if id == 0:
                    settings.device_properties[settings.ChargerVoltageNameList[(x-6)/2]] = voltage
                    settings.ChargerVoltageList[(x-6)/2] = voltage
                elif (id == 1 or id > 32) and id <= 39:
                    settings.device_properties[settings.ChargerSlaveIDs[id]] = voltage
                    id = (id - 32) if id > 1 else 0
                    settings.ChargerVoltageList[id] = voltage
                else:
                    return

        if query_type == 1:
            self.BatteryStatus = self.Battery_Status(settings.BatteryVoltageList.values())
            settings.device_properties['BatteryStatus'] = self.BatteryStatus
        elif query_type == 2:
            self.ChargerStatus = self.Charger_Status(settings.ChargerVoltageList.values())
            settings.device_properties['ChargerStatus'] = self.ChargerStatus

    def Battery_Status(self, voltages):  # Tuple of all voltages.
        state = ["Ok","Warning","Critical"]
        index = []
        for voltage in voltages:
            if float(voltage) == -1:
                index.append(0)
            elif float(voltage) > 15:           # Critical Overcharge
                index.append(2)
            elif float(voltage) > 14.6:         # Overcharge
                index.append(1)
            elif float(voltage) <= 9.5:         # Discharged/Critical Low Charge or No Charge
                index.append(2)
            elif float(voltage) < 11.5:         # Severely Discharged/Low Charge
                index.append(1)
            else:
                index.append(0)
        return state[max(index)]

    def Charger_Status(self, voltages):  # Tuple of all voltages.
        state = ["Ok","Warning","Critical"]
        index = []
        for voltage in voltages:
            if float(voltage) == -1:
                index.append(0)
            elif float(voltage) > 18:           # Critical High Voltage
                index.append(2)
            elif float(voltage) > 17:           # High Voltage
                index.append(1)
            elif float(voltage) <= 7:           # Critical Low or No Voltage output
                index.append(2)
            elif float(voltage) < 12:           # Low Voltage
                index.append(1)
            else:
                index.append(0)
        return state[max(index)]
    
class ComfortSN_SerialNumberReport(object):     # Possible Comfort SN decode issue. Sometimes Comfort reports 'Illegal' serial number.
    def __init__(self, data={}):

        if len(data) < 12:
            self.serial_number = "Invalid"
            self.refreshkey = "00000000"
            return
        else:
            # Decoding if Comfort implements SN reliably. Some systems are Invalid or Unsupported.
            DD = data[4:6]
            CC = data[6:8]
            BB = data[8:10]
            AA = data[10:12]
    
            dec_string = str(int(AA+BB+CC+DD,16)).zfill(8)
            dec_len = len(str(dec_string))
            prefix = int(dec_string[0:dec_len-6])
            if 0 < prefix <= 26:
                self.serial_number = str(chr(prefix + 64)) + dec_string[(dec_len-6):dec_len]
            elif data[4:12] == 'FFFFFFFF':
                self.serial_number = "Unassigned"
            elif data[4:12] == '00000000':
                self.serial_number = "Not Supported"
            else:
                self.serial_number = "Invalid"

            self.refreshkey = data[4:12]

class ComfortEXEntryExitDelayStarted(object):
    def __init__(self, data={}):
        self.type = int(data[2:4],16)
        self.delay = int(data[4:6],16)