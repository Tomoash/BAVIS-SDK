<img src="logo.png" alt="Benešl Automation" width="180">

# BAVIS SDK – writing communication drivers

The BAVIS SDK is the stable public API for drivers written outside the BAVIS core: by the community, by integrators or by
Benešl Automation for a single customer. A driver is shipped as a **driver package** (`bavis_drv_<name>`, file `.bavispkg`)
and installed in **System → Projects and packages** – no new BAVIS release is needed.

* SDK API version: **1.0** (`bavis.sdk.API`), supported by BAVIS 3.1 and later.
* Public repository with examples and contribution rules: [Tomoash/BAVIS-SDK](https://github.com/Tomoash/BAVIS-SDK)
  (Apache-2.0). This file is the reference; it is copied there with every release.
* Step-by-step guides in English and Czech (getting started, first driver, patterns, testing, building, CI and publishing) are
  in the public repository: `docs/en`, `docs/cs`.

BAVIS and Siemens product names are used only to describe compatibility. Siemens, SIMATIC and S7 are trademarks of Siemens AG.

## Contents

1. [Why the SDK](#1-why-the-sdk)
2. [Quick start](#2-quick-start)
3. [Package layout](#3-package-layout)
4. [The API](#4-the-api)
5. [Testing](#5-testing)
6. [Building, signing and installing](#6-building-signing-and-installing)
7. [Versioning and compatibility](#7-versioning-and-compatibility)
8. [Rules](#8-rules)

## 1. Why the SDK

A package that imports BAVIS **only through `bavis.sdk`** is an *SDK package*. When it is built, the manifest gets
`"sdk_api": "1.0"` and every BAVIS core that supports SDK major version 1 loads it – also after the next major release of the
core (3.x → 4.x). A package that imports `bavis.core…` directly is tied to one core major version (`core_max`, e.g. `3.99999`)
and stops loading after the next major release.

The build decides automatically: it parses every `.py` file of the package and sets `sdk_api` only when no file imports
`bavis` outside `bavis.sdk`. Imports inside functions count too.

## 2. Quick start

You need an installed BAVIS 4.0 or newer – the free Lite or Maker edition on Windows or Linux, or the Docker image. The source
code of the core is not needed: every installation has the command `bavis sdk` with the core and pytest already on its path.
The command and pytest come with a full installation of 4.0 (an update package `.whu` of an older installation does not add
them).

| Installation | Command |
| --- | --- |
| Windows | `C:\BAVIS\bavis-sdk.cmd` (in the installation folder, default `C:\BAVIS`) |
| Linux | `/opt/bavis/bavis-sdk` (as the service user or root – the core folder is not readable for other users) |
| Docker | `docker run --rm -v "$PWD:/work" -w /work --user "$(id -u):$(id -g)" <image> sdk …` |
| Core checkout (developers of BAVIS) | `python -m bavis sdk …` with `jadro/backend` on `PYTHONPATH` |

```
bavis-sdk new my_scale --label "My scale" --dir ~/drivers     # skeleton: driver, fake device, tests, translations
bavis-sdk test ~/drivers                                       # pytest against this core (pytest options after --)
bavis-sdk check ~/drivers                                      # what the build or the core would refuse; --strict for CI
bavis-sdk build ~/drivers                                      # ~/drivers/dist/drv_my_scale-1.0.0.bavispkg
bavis-sdk info                                                 # SDK API, core version, Python, pytest
```

The generator writes a working skeleton: a driver for a simple line-based TCP protocol, a fake device for the tests
(`socketserver` on 127.0.0.1) and translation files. Replace the protocol with the one of your device and keep the fake device in
step with it. Labels and help texts in the skeleton are Czech because Czech is the source language of BAVIS; English and other
languages go to `i18n/<lang>.json`.

The folder given to the commands is the *workspace*: it holds `bavis_drv_<name>/` (one or more packages) and `tests/`. The
package folder itself works too. `check` reports:

* errors (the build stops): invalid folder or file names, a module that does not import, an invalid `DriverSpec`, a kind the
  core already has, a missing or malformed `__version__` (`MAJOR.MINOR.PATCH`), broken `i18n/<lang>.json`;
* warnings: imports of `bavis` outside `bavis.sdk` (the package gets no `sdk_api` and is tied to one core major version),
  device libraries imported at module level of a driver, missing translations, texts in `en.json` not translated yet, no tests,
  fixed ports in the tests.

## 3. Package layout

```
bavis_drv_<name>/
  __init__.py          NAME = "Package name", __version__ = "1.0.0"
  drivers/__init__.py  (sub-package with the drivers)
  drivers/<module>.py  SPECS = [DriverSpec(...)] – one module may describe several kinds
  i18n/<lang>.json     {"srv": {"source text": "translation"}} – labels, help and messages (en, de, sk, pl)
tests/
  conftest.py          puts the folder with bavis_drv_<name> on sys.path
  test_<name>.py       tests against a fake device
```

`<name>` matches `^[a-z][a-z0-9_]{1,30}$`. The package ID is `drv_<name>`. A driver kind (`DriverSpec.kind`) must not collide
with a kind of the core or of another package – a duplicate kind is reported in **System → About → Modules** and the core driver
stays.

## 4. The API

Everything below is imported from `bavis.sdk`.

| Name | What it is |
| --- | --- |
| `Driver` | Base class. Override `open()`, `close()`, `poll() → {tag name: raw value \| None}` and optionally `write(tag, raw)`. The base runs the read loop in its own thread, reconnects after an error (2 s) and reports state. Event-driven drivers (MQTT-like) override `start()` / `_run()` and call `self.sink.on_values(self.conn.id, {...})` themselves. |
| `DriverError` | Exception with a message for the operator (shown in Objects → Communication). |
| `merge_ranges(items, max_gap, max_len)` | Groups `(start, size, payload)` into blocks for block reads (registers, DB areas). |
| `DriverSpec` | Description of a driver kind: `kind`, `label`, `make(conn, tags, sink, data_dir)`, `check_address(address, type) → error \| None`, `transport` (`tcp`, `udp`, `serial`, `url`, `none`), optional `fields`, `test`, `browse`, `validate`, `default_port`, `addr_help`, `summary`, `sim`, `license` … |
| `FieldSpec` | One field of the connection form (`key`, `label`, `type` = `text` / `number` / `bool` / `select` / `password` / `serial_port` / `file` / `list`, `default`, `min`, `max`, `options`, `help`, `show_if`, `secret`). Values are stored in `Connection.params`. |
| `TestCtx` | Context passed to `DriverSpec.test` (the **Test connection** button): `data_dir`, `simulate`. |
| `Conflict` | Raise from `test` / `browse` when the interface is used by a running connection with other settings (HTTP 409). |
| `UnknownDriver` | Raised by `lookup_driver` for an unknown kind. |
| `require_host` | Ready-made `validate` rule: the connection needs an IP address. |
| `Connection`, `Tag` | The project model of a connection and a tag (pydantic). Read `conn.host`, `conn.port`, `conn.poll_ms`, `conn.timeout_ms`, `conn.params`; `tag.name`, `tag.address`, `tag.type`, `tag.access`. |
| `validate_project(data)` | Validate a project dictionary → `(project, errors)`; useful to test `check_address` and field rules end to end. |
| `lookup_driver(kind)` | The registered `DriverSpec` of a kind (core, active project or installed package). |
| `check_spec(spec)` | Validate a `DriverSpec` exactly as the registry does at load time; `None` = valid. |
| `API`, `API_MAJOR`, `SUPPORTED_MAJORS`, `supports(api)` | SDK version of this core and the check the core uses for package manifests. |

Minimal driver:

```python
from bavis.sdk import Driver, DriverError, DriverSpec, FieldSpec, require_host


class ScaleDriver(Driver):
    def open(self):
        self.link = connect(self.conn.host, self.conn.port or 4001, self.conn.timeout_ms / 1000)

    def close(self):
        link, self.link = getattr(self, "link", None), None
        if link:
            link.close()

    def poll(self):
        return {t.name: self.link.read(t.address) for t in self.tags}


def check_address(address, typ):
    return None if address.startswith("W") else "address must start with W (W1, W2 …)"


SPECS = [DriverSpec(
    kind="my_scale", label="My scale", transport="tcp", default_port=4001, category="it", order=900,
    make=lambda conn, tags, sink, data_dir: ScaleDriver(conn, tags, sink, data_dir),
    check_address=check_address, validate=require_host,
    fields=(FieldSpec("station", "Station", "number", default=1, min=1, max=247),),
    addr_help="W<n> – weight channel, e.g. W1", addr_placeholder="W1",
)]
```

Values are **raw**: scaling, decimals, dead band, history and alarms are done by the engine. Return `None` for a value that is
not valid. `write()` is called from another thread than `poll()` – protect a shared link with a `threading.Lock`.

## 5. Testing

`bavis.sdk.testing` runs a driver without a BAVIS server:

```python
from bavis.sdk import testing


def test_reads_and_writes(fake_device):
    conn = testing.connection("my_scale", port=fake_device.port, params={"station": 1})
    tags = testing.tags(conn, [("W1", "W1"), ("W2", "W2", "float32", "rw")])
    assert testing.poll_once(conn, tags) == {"W1": 12.5, "W2": 0.0}
    with testing.run_driver(conn, tags) as run:                   # like the engine: own thread, reconnects, status
        assert testing.wait_for(lambda: run.sink.connected and run.sink.values.get("W1") == 12.5)
        run.driver.write(tags[1], 3.0)
```

| Helper | Purpose |
| --- | --- |
| `connection(driver, port=…, params=…)` | Connection with short test timings (poll 50 ms, timeout 1 s). |
| `tags(conn, [(name, address[, type[, access]])…])` | Tags of the connection (type `float32`, access `r` by default). |
| `poll_once(conn, tags, spec=None)` | One read cycle: `open()`, `poll()`, `close()`. `spec` defaults to the registered kind. |
| `run_driver(conn, tags, spec=None)` | Context manager running the driver thread; `.sink` records values and statuses. |
| `RecordingSink` | The engine stand-in used by both (`values`, `batches`, `statuses`, `connected`). |
| `wait_for(cond, timeout=5)` | Wait until a condition holds. |
| `free_port()` | A port chosen by the OS for a fake device. **Never use fixed ports** – tests run in parallel. |

## 6. Building, signing and installing

```
bavis-sdk build <workspace> [--key key.pem] [--version 1.2.0] [--out file.bavispkg]
```

`bavis-sdk build` runs `check` first and builds nothing when it finds an error; it prints the manifest summary and the SHA-256
of the file (for a catalogue entry). Without `--out` the file goes to `<workspace>/dist/drv_<name>-<version>.bavispkg`. It is
the same build as `python -m bavis package build <folder>/bavis_drv_<name> --out … --key …` of the core.

The build imports the driver modules and refuses a package with a broken module, an invalid `DriverSpec` or a kind the core
already has. It writes the kinds, `core_min`, `core_max` and – for SDK packages – `sdk_api` into the signed manifest
(`bavispkg.json`). Without `--key` the package is unsigned and installs only with `packages.allow_unsigned: true`
(development) or from a catalogue source for which the administrator allowed unsigned packages (since 4.0: the file must match
the SHA-256 listed in that source's `katalog.json`, the administrator confirms the installation and it is recorded in the audit
trail – see the guide *CI and publishing* in the public repository).

Installation: **System → Projects and packages → Upload package…**. A new package loads immediately and works for every project;
a new version of a loaded package waits for a restart of the application. A package can be uninstalled only when no connection
uses its drivers.

Package code runs inside the BAVIS process with the same rights as the core. Install only packages signed with a key you trust.
The catalogue of community packages (planned for BAVIS 4.0) accepts packages after review and signs them.

## 7. Versioning and compatibility

* `API = "1.0"`. Within major version 1, names in `bavis.sdk.__all__` keep their meaning. A minor version (1.1) may add optional
  fields and functions; a package built for 1.1 does not load on a core that has only 1.0.
* A new SDK major version (2.0) is introduced only with a new core major version. The core keeps supporting the previous SDK
  major for at least one LTS release (`SUPPORTED_MAJORS`).
* `core_min` still applies to every package: a package built with BAVIS 3.2 does not load on 3.1.
* For SDK packages `core_max` is ignored while `sdk.supports(manifest["sdk_api"])` is true. For other packages `core_max`
  (default: same core major version) applies as before.

## 8. Rules

1. Import BAVIS only from `bavis.sdk` and `bavis.sdk.testing`.
2. Do not import heavy libraries (pymodbus, asyncua, pyserial …) at module level – only inside functions. The registry imports
   every driver module when BAVIS starts.
3. Use libraries with a licence compatible with Apache-2.0 (MIT, BSD, Apache). GPL libraries are not accepted.
4. Register maps and addresses come from the manufacturer's documentation – cite it in the module docstring.
5. Writing to devices: refuse writes to read-only tags, keep writes disabled by default where a wrong value can damage
   equipment, and never write cyclically to flash or EEPROM registers.
6. Tests with a fake device and ports from `free_port()`; no test may need real hardware.
7. Texts for the operator go through `i18n/<lang>.json` (section `srv`).
