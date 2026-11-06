# 6. CI and publishing

[Guides](README.md) · previous: [Building and installing](05-building-and-installing.md)

## Checks in GitHub Actions

The BAVIS Docker image contains the whole SDK, so the check, the tests and the build run on a plain `ubuntu-latest` runner without
installing BAVIS. This repository offers an action that does it in one step:

```yaml
# .github/workflows/drivers.yml in your repository
name: drivers
on: [push, pull_request]
jobs:
  sdk:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Tomoash/BAVIS-SDK@main
        with:
          image: ghcr.io/tomoash/bavis:4        # BAVIS 4.x image
          workspace: .                          # folder with bavis_drv_<name>/ and tests/
          build: true                           # build .bavispkg into <workspace>/dist/
      - uses: actions/upload-artifact@v4
        with:
          name: bavispkg
          path: dist/*.bavispkg
```

The action runs `bavis-sdk check --strict`, `bavis-sdk test` and, with `build: true`, `bavis-sdk build` inside the image. All
inputs are described in [action.yml](../../action.yml).

> **Status:** the BAVIS 4 Docker image is published together with BAVIS 4.0. Until then the workflow of this repository runs only
> where the repository variable `BAVIS_SDK_IMAGE` is set (see the [examples workflow](../../.github/workflows/examples.yml)).

Without Docker the same runs on a self-hosted runner with BAVIS installed: `C:\BAVIS\bavis-sdk.cmd check --strict .` etc.

## Your own package repository

For drivers you do not want to or cannot publish (customer devices, internal protocols), create your own repository:

```
my-drivers/
  scale/                     workspace: bavis_drv_my_scale/ + tests/
  mass_flow_meter/           another driver
  .github/workflows/drivers.yml
```

CI checks, tests and builds every driver. Installations then take the packages from **your own catalogue**:

1. Put the built `.bavispkg` files into one folder and create the list:

   ```
   C:\BAVIS\python\python.exe -X utf8 -m bavis catalog build dist --name "Company drivers"
   ```

   (Linux: `PYTHONPATH=/opt/bavis/backend /opt/bavis/venv/bin/python -X utf8 -m bavis catalog build dist …`.)
   It writes `dist/katalog.json` with the version and SHA-256 fingerprint of every package.
2. Publish the folder at an `https://…` address (your website, intranet) or put it on a shared network folder.
3. In a BAVIS 4.0+ installation the administrator adds the address `https://…/katalog.json` or the folder in
   **Configuration → Parts catalogue → Sources** and ticks **Unsigned packages** for that source.
4. **System → Projects and packages → From catalogue…** then offers the packages. The installation checks the SHA-256 fingerprint,
   the administrator confirms it and it is recorded in the audit trail.

Allow unsigned packages only for a source that you manage or fully trust – the package code runs with the same rights as BAVIS.
An `http://` source (without TLS) does not have this option.

## Contributing to the public catalogue

Send a driver that is useful to others to this repository:

1. Open an issue that describes the device or protocol (template *Driver or device request*), so that work is not duplicated.
2. Add the driver as a workspace in `drivers/<name>/` (`bavis_drv_<name>/` + `tests/`) with tests and translations. The
   `examples/` folder is reserved for the examples copied here from the BAVIS development.
3. The pull request must pass `bavis-sdk check --strict` and `bavis-sdk test`. Sign off your commits (`git commit -s`).
4. After review we build the driver, sign it with the Benešl Automation key and publish it in the catalogue on BAVIS Central.

The rules are in [CONTRIBUTING.md](../../CONTRIBUTING.md). Report security issues privately as described in
[SECURITY.md](../../SECURITY.md) to [benesl@benesl-automation.cz](mailto:benesl@benesl-automation.cz).
