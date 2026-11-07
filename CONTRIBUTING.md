# Contributing to the BAVIS SDK

Thank you for helping extend BAVIS. This guide explains where to ask, how to propose a driver and how it gets into the public
catalogue. Česky: [CONTRIBUTING.cs.md](CONTRIBUTING.cs.md).

## Where to talk

| You want to … | Go to |
| --- | --- |
| ask how to do something, get help with your driver | [Discussions → Q&A](https://github.com/Tomoash/BAVIS-SDK/discussions/categories/q-a) |
| suggest a device or protocol, find others who need it too | [Discussions → Drivers](https://github.com/Tomoash/BAVIS-SDK/discussions/categories/drivers) |
| propose an improvement of the SDK or the guides | [Discussions → Ideas](https://github.com/Tomoash/BAVIS-SDK/discussions/categories/ideas) |
| show a driver or a project you built | [Discussions → Show and tell](https://github.com/Tomoash/BAVIS-SDK/discussions/categories/show-and-tell) |
| report a bug in the SDK, a guide or an example | an issue – template *Bug report* |
| start work on a driver that should go to the public catalogue | an issue – template *Driver or device request* |
| report a security vulnerability | privately by e-mail – see [SECURITY.md](SECURITY.md), never in public |

Questions about your BAVIS installation or licence that have nothing to do with drivers go to
[benesl@benesl-automation.cz](mailto:benesl@benesl-automation.cz).

## Ways to contribute

- **Answer questions** in Discussions – the fastest way to help other integrators.
- **Report a bug** in the SDK, a guide or an example.
- **Ask for a driver or a device** you need, or add your vote (👍) to an existing request – the most wanted drivers are done first.
- **Contribute a driver** for a device or protocol.
- **Test a driver with a real device** – drivers are tested against fake devices, a report "works with model X, firmware Y" is
  very valuable.
- **Improve the documentation**, including translations (English, Czech, German, Slovak, Polish).

Issues labelled [`good first issue`](https://github.com/Tomoash/BAVIS-SDK/labels/good%20first%20issue) are small and well
described; [`help wanted`](https://github.com/Tomoash/BAVIS-SDK/labels/help%20wanted) are requests nobody works on yet.

## Before you start a driver

1. Search Discussions and issues – maybe someone already works on the same device.
2. Check that the protocol or device is not already supported by the BAVIS core (Modbus TCP/RTU, S7, OPC UA, MQTT, REST, BACnet,
   KNX, M-Bus, SNMP, SQL and many more are built in – see *Objects → Communication → New connection* in BAVIS).
3. Open an issue with the template *Driver or device request* and write that you work on it, so that work is not duplicated.
4. Start with `bavis-sdk new <name> --dir drivers/<name>`, read the [guides](docs/en/README.md) and the closest
   [example](examples/README.md). [`hello`](examples/hello) is the smallest one.

## Requirements for a driver

- **SDK only.** Import BAVIS only from `bavis.sdk` and `bavis.sdk.testing` – then the driver keeps working with future versions.
- **Tests without hardware.** Every driver comes with automated tests against a fake device or recorded data, on ports chosen by
  the OS (`testing.free_port()`).
- **Checks pass.** `bavis-sdk check --strict drivers/<name>` and `bavis-sdk test drivers/<name>` are green.
- **Light imports.** Device libraries are imported inside functions, not at module level.
- **Libraries with a compatible licence** (MIT, BSD, Apache-2.0). GPL libraries are not accepted.
- **Sources cited.** Register maps and commands come from the manufacturer's documentation or a published standard – cite it in
  the module docstring (title, version, link). Do not copy register maps from other projects, and do not use reverse-engineered or
  unofficial cloud APIs without asking first in the issue.
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

## From a pull request to the catalogue

1. **Pull request** to `drivers/<name>/`, using the pull request template. Keep one driver per pull request.
2. **Automatic checks** – the workflow runs `bavis-sdk check --strict`, the tests and the build with the BAVIS Docker image (as soon as the image is public with BAVIS 4.0).
3. **Review** by Benešl Automation: the rules above, the code (it runs inside BAVIS with the same rights as the core), the cited
   documentation and the texts for the operator. We aim to answer every pull request within two weeks.
4. **Merge and signing.** After the merge we build the package, sign it with the publisher key of Benešl Automation and publish it
   in the public catalogue on BAVIS Central. BAVIS installations then offer it in *System → Projects and packages → From
   catalogue*. The driver is listed in [drivers/README.md](drivers/README.md) with you as the maintainer.
5. **New versions** go the same way: raise `__version__` in `bavis_drv_<name>/__init__.py` (`MAJOR.MINOR.PATCH`) and describe the
   change in the pull request.

Only reviewed and signed packages are offered in the public catalogue. You can always build and install your driver yourself –
unsigned, from your own catalogue (see [CI and publishing](docs/en/06-ci-and-publishing.md)) – without waiting for the review.

## Maintaining a driver

The author of a driver is its maintainer: we ask you to review issues and pull requests for it. If you can no longer maintain it,
say so in an issue – the driver stays in the catalogue and another maintainer can take over. A driver that stops passing the
checks with a new SDK version and has no maintainer may be removed from the catalogue (installed packages keep working).

## The examples

The `examples/` folder is maintained together with the BAVIS core and copied here on every SDK release; please report changes to
the examples as issues. Community drivers go to `drivers/<name>/`.

## Code of conduct

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md). Be respectful and constructive.
