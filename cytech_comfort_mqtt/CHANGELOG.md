## [1.0.9] - 2026-09-09

### Changed
- Added configurable MQTT security levels
- Responses now available through CCLX discovery
- Fixed issue with Alarm Log being reset when open zones are present
- Fixed # key being ignored when incomplete data received.

## [1.0.8] - 2026-07-02

### Changed
- Modified MQTT message clear code

## [1.0.7] - 2026-06-20

### Changed
- Test version

## [1.0.6] - 2026-05-28

### Changed
- Test version

## [1.0.5] - 2026-05-28

### Changed
- Changed restart to read cclx file

## [1.0.4] - 2026-05-27

### Changed
- Small bug fixes

## [1.0.3] - 2026-05-27

### Added
- TCP to Serial bridge to allow Comfigurator access to Comfort through HA
- RAM based logging to reduce SD Card writes

## [1.0.2] - 2026-04-21

### Added
- Added Config option for UCMA/Pi CM4Pi on CM9001 - this sets the baudrate


## [1.0.1] - 2026-04-13

### Changed
- Reduced INFO-level logging to improve readability in normal operation
- Moved discovery topic clearing logs from INFO to DEBUG
- Moved per-output discovery logs from WARNING to DEBUG
- Reduced verbosity of battery status and metadata publishing logs

### Added
- Added logging for ignored messages when CacheState=False (e.g. sr, IP, OP)
- Added handling for DT (date/time) messages from Comfort
- Added logging for AL message type (alarm event reporting)

### Fixed
- Prevented misleading "Unhandled line" logs for valid but gated messages
- Improved startup behaviour visibility through clearer logging


## [1.0.0] - 2026-04-08
initial release

