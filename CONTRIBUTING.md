# Contributing to the BAVIS SDK

Thank you for helping extend BAVIS. This guide explains how to propose a module and how it gets into the public catalogue.

> The SDK is being prepared for BAVIS 3.1. Until then, issues and ideas are welcome; pull requests with modules will be
> accepted once the templates and the test tools are published.

## Ways to contribute

- **Report a bug** in the SDK, a template or an example (use the *Bug report* issue template).
- **Ask for a driver or a device** you need (use the *Driver or device request* template).
- **Contribute a module**: a communication driver, symbol set, screen element, device type, project template or tool.
- **Improve documentation**, including translations.

## Before you start a module

1. Open an issue that describes the device or feature, so that work is not duplicated.
2. Check that the protocol or device is not already supported by the BAVIS core.
3. Start from the matching template in `templates/` (available with BAVIS 3.1).

## Requirements for a module

- **Tests.** Every module comes with automated tests that run without real hardware (a simulated device or recorded data).
- **No hidden network traffic.** A module talks only to the devices and services the user configures.
- **No secrets in code.** Passwords, keys and tokens come from the connection settings, never from the source.
- **Texts in English.** User-facing texts are in English; Czech, German, Slovak and Polish translations are welcome.
- **Licence.** Your contribution is licensed under Apache-2.0, the licence of this repository.

## Sign-off

Each commit must be signed off (`git commit -s`) to certify the
[Developer Certificate of Origin](https://developercertificate.org/): you wrote the code or have the right to submit it
under the Apache-2.0 licence.

## Review and signing

Pull requests are reviewed by Benešl Automation. Modules accepted into the public catalogue are packaged and signed with the
publisher key, so that BAVIS installations can trust them. A module code runs inside the BAVIS process with the same rights
as the core, which is why only reviewed and signed packages are offered in the catalogue.

## Code of conduct

Be respectful and constructive. Harassment or personal attacks are not tolerated; maintainers may remove comments, commits
or contributors that break this rule. Report problems to [benesl@benesl-automation.cz](mailto:benesl@benesl-automation.cz).
