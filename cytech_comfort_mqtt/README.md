# Home Assistant App: Comfort to MQTT
Connect your Cytech Comfort alarm and Home Control Menu to Home Assistant over MQTT.

**Target architectures** are `aarch64` and `amd64`.

[mosquitto]: https://mosquitto.org

For more information about Cytech Comfort systems, please see the [Cytech Technology Pte Ltd.](http://cytech.biz) website.


## About

This App is used to bridge a Cytech Comfort II ULTRA system to MQTT for use in Home Assistant. 

## Comfort Alarm 

This is a customised version of the original comfort2mqtt project by 'koochyrat' and the derivative code from 
'Ingo de Jager'. More information about the original source projects is available [here](https://github.com/koochyrat/comfort2) and [here](https://github.com/djagerif/comfort2mqtt)


The following objects are supported:

* Zone Inputs [1-96]
* Zone Outputs [1-96]
* Counters [0-254]
* Flags [1-254]
* Sensors [0-31]
* Responses [1-1024]

## Comfort Home Control

The app reads the Home Control Menu from your Comfort CCLX configuration. Home Assistant discovers buttons for the configured actions and sensors for controls that report status.


⚠️ This Add-on was specifically developed for Home Assistant OS. Home Assistant Container and Core have not been tested and is not supported at present.

Copyright 2026 Cytech Technology Pte Ltd. Licensed under Apache-2.0. For more details see the [LICENSE](LICENSE) file.

