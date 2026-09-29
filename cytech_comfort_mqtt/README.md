# Home Assistant Add-on: Comfort to MQTT
Cytech Comfort to MQTT bridge for Home Assistant.

![Supports aarch64 Architecture][aarch64-shield] ![Supports amd64 Architecture][amd64-shield] ![Supports armhf Architecture][armhf-shield] ![Supports armv7 Architecture][armv7-shield] ![Supports i386 Architecture][i386-shield]

[mosquitto]: https://mosquitto.org
[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[armv7-shield]: https://img.shields.io/badge/armv7-yes-green.svg
[i386-shield]: https://img.shields.io/badge/i386-yes-green.svg

For more information about Cytech Comfort systems, please see the [Cytech Technology Pte Ltd.](http://cytech.biz) website.


## About
This Addon is used to bridge a Cytech Comfort II ULTRA Alarm system to MQTT for use in Home Assistant. Other Comfort systems are partially supported.

This is a customised version of the original comfort2mqtt project by 'koochyrat' and the derivative code from 
'Ingo de Jager'. More information about the original source projects is available [here](https://github.com/koochyrat/comfort2) and [here](https://github.com/djagerif/comfort2mqtt)


The following objects are supported:

* Zone Inputs [1-96]
* Zone Outputs [1-96]
* Counters [0-254]
* Flags [1-254]
* Sensors [0-31]
* Responses [1-1024]


⚠️ This Add-on was specifically developed for Home Assistant OS. Home Assistant Container and Core have not been tested and is not supported at present.

Copyright 2026 Cytech Technology Pte Ltd. Licensed under Apache-2.0. For more details see the [LICENSE](LICENSE) file.

## Live alarm status dashboard

The AM alarm status publisher and Home Assistant image YAML are available for testing.
See [HA image integration](home_assistant/README.md) for the MQTT sensor and the button/table within the existing Comfort Alarm dashboard.
