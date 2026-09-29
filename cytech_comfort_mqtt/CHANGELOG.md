## 1.0.10-dev7

- Query all zone bypass states after zone discovery so startup/reload cleanup does not leave statuses unknown. No bypass settings are changed.

## 1.0.10-dev6

- Add per-zone Set bypass and Clear bypass MQTT buttons and panel-confirmed status.
- Handle individual B? replies and nonzero BY states; ignore retained bypass commands and commands while disconnected.

## [1.0.10-dev5] - 2026-09-29

### Fixed
- Clear retained Response button discovery during MQTT startup/reconnection, alongside the other Comfort entities, so old Response buttons do not remain after a failed login.
- Reset the Response discovery flag when clearing, allowing discovery to be recreated after a successful connection.
- Preserve the RAM-only logging and login diagnostics from dev4.

## [1.0.10-dev4] - 2026-09-29

### Changed
- Remove the stdout log mirror introduced in dev3 to avoid additional host-persisted diagnostic logging. Keep the rotating RAM log at `/dev/shm/cytech_comfort_mqtt.log`.
- Preserve login-rejection messages in both the RAM log and the MQTT Alarm Message Log, along with the other dev3 fixes.
- Verify logging verbosity, duplicate-handler prevention and absence of stdout/stderr output in regression tests.

## [1.0.10-dev3] - 2026-09-29

### Fixed
- Report rejected Comfort logins in the alarm message/event log and at ERROR level in the RAM and Supervisor logs; distinguish rejection during login from a later session logout.
- Keep the bridge disconnected until login acknowledgement, and clear its connected flag on LU00.
- Ignore retained alarm command replays and remove the retained synthetic `comm test` command after login.
- Throttle startup-readiness warnings and include the login failure reason when known.

### Changed
- Mirror RAM logging to stdout at the configured verbosity, without duplicate handlers.
- Mask PINs in login/arming serial TX logs and omit disarm PINs from command debug output.

## [1.0.10-dev2] - 2026-09-22

### Changed
- AM codes 1, 2, 3, 4, 7, 22, 25 and 26 preserve their event messages without publishing `triggered`.

### Added
- Live AM/AR status publisher with per-device observations, current trouble bits, and offline handling.
- HA image YAML for an Alarm & Trouble Status button and live table within the existing Comfort Alarm dashboard.
- Regression tests for alarm policy, restores, status updates and dashboard templates.

## [1.0.10] - 2026-09-09

### Changed
- Recovery for tls certificates left over from previous installations

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

