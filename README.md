<p align="center"><img alt="ha-hearth - A Home Assistant integration for Hearth" src="https://raw.githubusercontent.com/alexdlaird/ha-hearth/main/custom_components/hearth/brand/logo@2x.png" width="160" /></p>

[![Version](https://img.shields.io/github/v/release/alexdlaird/ha-hearth)](https://github.com/alexdlaird/ha-hearth/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5)](https://hacs.xyz)
[![Coverage](https://img.shields.io/codecov/c/github/alexdlaird/ha-hearth)](https://codecov.io/gh/alexdlaird/ha-hearth)
[![Build](https://img.shields.io/github/actions/workflow/status/alexdlaird/ha-hearth/build.yml)](https://github.com/alexdlaird/ha-hearth/actions/workflows/build.yml)
[![GitHub License](https://img.shields.io/github/license/alexdlaird/ha-hearth)](https://github.com/alexdlaird/ha-hearth/blob/main/LICENSE)

`ha-hearth` is a Home Assistant integration for [Hearth](https://www.meethearth.app). It sends Hearth the room sensors
(and, optionally, the thermostat) that Home Assistant already has, and applies any thermostat settings Hearth
answers with using Home Assistant's own climate actions. Home Assistant only ever calls out to Hearth.

## Installation

`ha-hearth` requires Home Assistant 2025.12 or newer, and can be installed with [HACS](https://hacs.xyz):

1. In HACS, open the menu, choose "Custom repositories", and add `https://github.com/alexdlaird/ha-hearth` as an
   Integration.
2. Find Hearth in HACS and download it.
3. Restart Home Assistant.

That's it! Hearth is now available to add in Home Assistant.

To install manually instead, copy `custom_components/hearth` into Home Assistant's `config/custom_components/`
directory and restart.

## Basic Usage

In the Hearth app, set up your home with Home Assistant, which shows the home's key. (For room sensors only, create
the key in Settings, then Manage home, then Sensors, then "Other sensors (Hearth API)".) Then, in Home Assistant, go to
Settings, then Devices & services, then Add integration, and choose Hearth. Paste the key, then choose your thermostat
and room sensors.

To change the thermostat or sensors later, use the integration's Configure button; to change the key, use Reconfigure.

## Documentation

For more advanced usage, `ha-hearth`'s official documentation is available
on [Hearth's website](https://www.meethearth.app/sensors/home-assistant), including its
[status sensor](https://www.meethearth.app/sensors/home-assistant#good-to-know) and the
[Hearth API](https://www.meethearth.app/support#hearth-api) it uses.

For more detail when troubleshooting, turn on debug logging:

```yaml
logger:
  logs:
    custom_components.hearth: debug
```

## Contributing

If you would like to get involved, be sure to review
the [Contribution Guide](https://github.com/alexdlaird/ha-hearth/blob/main/CONTRIBUTING.rst).

Want to contribute financially? If you've found `ha-hearth` useful, [sponsorship](https://github.com/sponsors/alexdlaird)
would also be greatly appreciated!
