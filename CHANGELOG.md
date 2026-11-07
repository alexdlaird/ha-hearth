# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/alexdlaird/ha-hearth/compare/1.1.3...HEAD)

### Changed

- Reconfiguring with a different home's key, when the home Hearth was set up with no longer exists, says to remove
  Hearth and add it again, rather than that the key belongs to another home.

## [1.1.3](https://github.com/alexdlaird/ha-hearth/compare/1.1.2...1.1.3) - 2026-11-07

### Fixed

- Stability and bug fixes.

## [1.1.2](https://github.com/alexdlaird/ha-hearth/compare/1.1.1...1.1.2) - 2026-11-05

### Fixed

- Stability and bug fixes.

## [1.1.1](https://github.com/alexdlaird/ha-hearth/compare/1.1.0...1.1.1) - 2026-10-31

### Fixed

- Stability and bug fixes.

## [1.1.0](https://github.com/alexdlaird/ha-hearth/compare/1.0.2...1.1.0) - 2026-10-26

### Added

- A repair in Settings, then Repairs, once the chosen thermostat has been missing from Home Assistant for 6 hours.
- The integration is keyed on the Hearth home: reauthenticating or reconfiguring with another home's key is refused.

### Changed

- Setup is retried while Hearth can't be reached, instead of starting with the bridge unreachable.
- Posts name Home Assistant's and the integration's versions, so Hearth's logs say what posted.
- Requires `pyhearth` 1.1.0.

### Fixed

- The Bridge status icons for a missing or unavailable thermostat.

## [1.0.2](https://github.com/alexdlaird/ha-hearth/compare/1.0.1...1.0.2) - 2026-10-26

### Changed

- Listed as "Hearth: Room Thermostat", the app's full name.

## [1.0.1](https://github.com/alexdlaird/ha-hearth/compare/1.0.0...1.0.1) - 2026-10-26

### Changed

- Documentation improvements.

## [1.0.0](https://github.com/alexdlaird/ha-hearth/compare/0.1.0...1.0.0) - 2026-10-26

### Changed

- Hearth's API client is now its own package, [`pyhearth`](https://github.com/alexdlaird/pyhearth).

## [0.1.0](https://github.com/alexdlaird/ha-hearth/releases/tag/0.1.0) - 2026-10-25

- First release of `ha-hearth`.
