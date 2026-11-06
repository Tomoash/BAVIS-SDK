# 1. Getting started

[Guides](README.md) · next: [Your first driver step by step](02-first-driver.md)

## What the BAVIS SDK is

BAVIS is a web-based SCADA / HMI. Its core is closed source, but communication drivers can be written outside of it: a driver is
a small Python package (`bavis_drv_<name>`) built into a `.bavispkg` file and installed in **System → Projects and packages**.
No new BAVIS release is needed.

The **BAVIS SDK** is the stable public API for such drivers (`bavis.sdk`, API version **1.0**) plus tools around it:

* a skeleton of a new driver with a fake device and tests,
* a check of the package (what the core would refuse),
* running the tests against the installed core,
* building the `.bavispkg`.

A package that imports BAVIS **only through `bavis.sdk`** is an *SDK package*: every core that supports SDK API 1.x loads it, also
after the next major version of BAVIS (3.x → 4.x). A package that reaches into the core (`bavis.core…`) is tied to one major
version and stops loading after it.

## What the SDK does not do yet

SDK 1.0 is for **communication drivers** only. Symbols, device types, screens, report templates and other parts of a project are
shared as catalogue *parts* (exported from the project configuration, no programming). Servers (BAVIS publishing data elsewhere)
and custom screen elements are not supported by the SDK yet.

## What you need

| What | Why |
| --- | --- |
| An installation of BAVIS **4.0 or newer** (Windows, Linux or the Docker image) | it contains the `bavis sdk` command, the core and pytest. The free edition is enough. |
| An editor (VS Code, PyCharm …) | writing code |
| The protocol documentation of the device | register map, commands, answer format |

You do not need to install Python separately: `bavis sdk` uses the Python that comes with BAVIS.

> **BAVIS 3.1** already loads SDK 1.0 packages, but the `bavis sdk` command (skeleton, check, tests) comes with 4.0.
> Updating an older installation with a `.whu` file does not add the command or pytest – a full 4.0 installation is needed.

Where to find the command:

| Installation | Command |
| --- | --- |
| Windows | `C:\BAVIS\bavis-sdk.cmd` (installation folder, default `C:\BAVIS`) |
| Linux | `/opt/bavis/bavis-sdk` (as the service user or root – the core folder is not readable for other users) |
| Docker | `docker run --rm -v "$PWD:/work" -w /work --user "$(id -u):$(id -g)" <image> sdk …` |

The guides write `bavis-sdk` for short.

## Your first package in five minutes

```
bavis-sdk info                                         # core version, SDK API, Python, pytest
bavis-sdk new my_scale --label "Moje váha" --dir ~/drivers/scale
bavis-sdk test ~/drivers/scale                         # 5 tests against a fake device
bavis-sdk check ~/drivers/scale                        # what the build or the core would refuse
bavis-sdk build ~/drivers/scale                        # ~/drivers/scale/dist/drv_my_scale-1.0.0.bavispkg
```

`new` creates a *workspace*:

```
~/drivers/scale/
  bavis_drv_my_scale/
    __init__.py            NAME = "Moje váha", __version__ = "1.0.0"
    drivers/__init__.py
    drivers/my_scale.py    the driver + its DriverSpec (SPECS)
    i18n/en.json …         translations of operator texts (en, de, sk, pl)
  tests/
    conftest.py            puts the workspace on sys.path
    test_my_scale.py       tests against a fake device (TCP server on 127.0.0.1)
```

The skeleton is a working driver for a simple line protocol (`1 GET R10` → `OK 12.5`). Replace it with the protocol of your device
and change the fake device in the tests the same way – see the [next guide](02-first-driver.md).

`<name>` matches `^[a-z][a-z0-9_]{1,30}$` and is also the driver kind (`DriverSpec.kind`). It must not collide with a driver of
the core (`modbus_tcp`, `s7`, `mqtt`, `rest` …) or of another package – the build refuses such a package.

## How `check` reports problems

* **Errors** (the build stops): an invalid folder or file name, a module that does not import, an invalid `DriverSpec`, a kind the
  core already has, a missing or malformed `__version__` (`MAJOR.MINOR.PATCH`), a broken `i18n/<lang>.json`.
* **Warnings**: imports of BAVIS outside `bavis.sdk` (the package will not be an SDK package), device libraries imported at module
  level, missing or untranslated texts, no tests, fixed ports in tests.

`bavis-sdk check --strict` treats warnings as errors – use it in CI.

## Where next

* [Your first driver step by step](02-first-driver.md)
* Complete examples: [examples](../../examples/README.md)
* API reference: [drivers.md](../drivers.md)
