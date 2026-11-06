# 5. Building and installing

[Guides](README.md) · previous: [Testing](04-testing.md) · next: [CI and publishing](06-ci-and-publishing.md)

## Building

```
bavis-sdk build <workspace> [--version 1.2.0] [--out file.bavispkg] [--key key.pem]
```

`build` runs `check` first and builds nothing when it finds an error. Without `--out` the file goes to
`<workspace>/dist/drv_<name>-<version>.bavispkg`. At the end it prints the manifest summary and the **SHA-256** of the file (useful
for a catalogue, see [CI and publishing](06-ci-and-publishing.md)):

```
bavis_drv_my_scale 1.0.0: drivers my_scale; SDK package (sdk_api 1.0)
  OK
  built /home/me/drivers/scale/dist/drv_my_scale-1.0.0.bavispkg
  drv_my_scale 1.0.0, drivers my_scale, core 4.0.0–4.99999, sdk_api 1.0, UNSIGNED (installs only with packages.allow_unsigned: true)
  SHA-256 3f2a…
```

The build imports the driver modules and refuses a package with a broken module, an invalid `DriverSpec` or a kind the core
already has. It writes the kinds, `core_min`, `core_max` and – for an SDK package – `sdk_api` into the manifest (`bavispkg.json`).

## Versions

* The package version is `__version__` in `bavis_drv_<name>/__init__.py` (`MAJOR.MINOR.PATCH`); `--version` overrides it.
* A released version never changes – a fix is a new version (`1.0.1`). Versions compare numerically (`1.10.0` > `1.9.0`).
* `core_min` = the BAVIS version you built with. A package built on BAVIS 4.1 does not load on 4.0 – build on the oldest version
  you want to support.
* `sdk_api` = the SDK API version. For an SDK package `core_max` is ignored while the core supports the SDK major version (1.x).
  A package built for SDK 1.1 does not load on a core that has only 1.0.

## Signing

A package contains code that runs inside BAVIS with the same rights as the core. That is why an installation accepts:

| Package | Where it installs |
| --- | --- |
| **signed with the Benešl Automation key** | anywhere – packages from the public catalogue are released like this |
| **unsigned, from your catalogue** (BAVIS 4.0+) | in an installation where the administrator allowed *Unsigned packages* for your catalogue source; the file must match the SHA-256 in `katalog.json` exactly, the administrator confirms the installation and it is recorded in the audit trail |
| **unsigned, uploaded by hand** | only in development mode (`packages: {allow_unsigned: true}` in `config.yaml`) – on your own development machine |

`--key` signs the package with an Ed25519 key that the core knows as a vendor key (update key). The build refuses any other key.
If you want your package in the public catalogue, send it as a pull request to this repository – after review we sign and publish
it (see [CI and publishing](06-ci-and-publishing.md)).

## Installing

1. **System → Projects and packages → Upload package…** (or **From catalogue…**).
2. The preview shows the name, version, drivers, core version, signature and – for an unsigned package from a catalogue – the
   source and the fingerprint.
3. **Install** (with the `pkg_install` e-signature when the installation requires it).

A new package loads immediately and its drivers are available for every project. A new version of a package that is already
loaded waits for a restart of the application. A package can be uninstalled only when no connection uses its drivers.

Load errors (a broken module, a duplicate kind) are shown in **System → About → Modules**; a core driver with the same kind always
stays.

## Docker

In the Docker image, installed packages live in the data volume (`/data/packages`). Installing through the user interface works the
same as elsewhere; the image is updated as a whole (a new image tag), not with a `.whu` file.
