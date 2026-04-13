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

