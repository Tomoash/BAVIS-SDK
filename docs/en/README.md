<img src="../logo.png" alt="Benešl Automation" width="180">

# BAVIS SDK guides

The guides are for integrators and developers who want to connect a device or protocol that the BAVIS core does not support.
You need to know Python; you do not need the source code of the BAVIS core.

| # | Guide | What it covers |
| --- | --- | --- |
| 1 | [Getting started](01-getting-started.md) | what the SDK does, what you need, your first package in five minutes |
| 2 | [Your first driver step by step](02-first-driver.md) | from the skeleton to your protocol: addresses, reading, writing, connection form, translations |
| 3 | [Driver patterns](03-patterns.md) | request/response, block reads, devices that push data, files, browsing, writing |
| 4 | [Testing](04-testing.md) | fake devices, the `bavis.sdk.testing` helpers, what to test every time |
| 5 | [Building and installing](05-building-and-installing.md) | `.bavispkg`, signing, installation, versions and compatibility |
| 6 | [CI and publishing](06-ci-and-publishing.md) | GitHub Actions with the Docker image, your own package repository, the catalogue, contributing here |

The API reference is [drivers.md](../drivers.md). Complete examples with tests are in [examples](../../examples/README.md).

Česká verze návodů: [docs/cs](../cs/README.md).
