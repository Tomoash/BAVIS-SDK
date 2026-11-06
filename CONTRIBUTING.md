# Contributing to the BAVIS SDK

Thank you for helping extend BAVIS. This guide explains how to propose a driver and how it gets into the public catalogue.
A Czech version of the publishing steps is in [docs/cs/06-ci-a-zverejneni.md](docs/cs/06-ci-a-zverejneni.md).

## Ways to contribute

- **Report a bug** in the SDK, a guide or an example (use the *Bug report* issue template).
- **Ask for a driver or a device** you need (use the *Driver or device request* template).
- **Contribute a driver** for a device or protocol.
- **Improve the documentation**, including translations.

## Before you start a driver

1. Open an issue that describes the device or protocol, so that work is not duplicated.
2. Check that the protocol or device is not already supported by the BAVIS core (Modbus, S7, OPC UA, MQTT, REST, BACnet, KNX and
   many more are built in).
3. Start with `bavis-sdk new <name> --dir drivers/<name>` and read the [guides](docs/en/README.md).

## Requirements for a driver

- **SDK only.** Import BAVIS only from `bavis.sdk` and `bavis.sdk.testing` – then the driver keeps working with future versions.
- **Tests without hardware.** Every driver comes with automated tests against a fake device or recorded data, on ports chosen by
  the OS (`testing.free_port()`).
- **Checks pass.** `bavis-sdk check --strict drivers/<name>` and `bavis-sdk test drivers/<name>` are green.
- **Light imports.** Device libraries are imported inside functions, not at module level.
- **Libraries with a compatible licence** (MIT, BSD, Apache-2.0). GPL libraries are not accepted.
- **Sources cited.** Register maps and commands come from the manufacturer's documentation – cite it in the module docstring.
- **Safe writes.** Refuse writes to read-only tags, keep writes off by default where a wrong value can damage equipment, never
  write cyclically to flash or EEPROM.
- **No hidden network traffic.** A driver talks only to the devices and services the user configures.
- **No secrets in code.** Passwords, keys and tokens come from connection fields (`"password"`, `secret=True`).
- **Texts for the operator.** Czech is the source language of BAVIS: labels, help and messages are Czech keys with translations in
  `i18n/en.json` (required), `de`, `sk` and `pl`. If you do not speak Czech, write English texts and say so in the pull request –
  the maintainers will add the Czech source and translations. Code comments and docstrings are in English.
- **Licence.** Your contribution is licensed under Apache-2.0, the licence of this repository.

## Sign-off

Each commit must be signed off (`git commit -s`) to certify the
[Developer Certificate of Origin](https://developercertificate.org/): you wrote the code or have the right to submit it
under the Apache-2.0 licence.

## Review and signing

Pull requests are reviewed by Benešl Automation. Drivers accepted into the public catalogue are packaged and signed with the
publisher key, so that BAVIS installations can trust them. Driver code runs inside the BAVIS process with the same rights as the
core, which is why only reviewed and signed packages are offered in the public catalogue.

The `examples/` folder is maintained together with the BAVIS core and copied here on every SDK release; please report changes to
the examples as issues. Community drivers go to `drivers/<name>/`.

## Code of conduct

Be respectful and constructive. Harassment or personal attacks are not tolerated; maintainers may remove comments, commits
or contributors that break this rule. Report problems to [benesl@benesl-automation.cz](mailto:benesl@benesl-automation.cz).
