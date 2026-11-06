# Examples / Příklady

Complete driver packages with tests. Each folder is a *workspace*: `bavis_drv_<name>/` (the package) and `tests/` (pytest against a
fake device). They use only the Python standard library and `bavis.sdk`, and pass `bavis-sdk check --strict`.

Kompletní balíčky driverů s testy. Každá složka je *pracovní složka*: `bavis_drv_<název>/` (balíček) a `tests/` (pytest proti
náhradnímu zařízení). Používají jen standardní knihovnu Pythonu a `bavis.sdk` a projdou `bavis-sdk check --strict`.

| Example | Device | What it shows |
| --- | --- | --- |
| [http_json](http_json) | web API / device answering JSON over HTTP | one request per cycle, address = dotted path, custom field, connection test |
| [scpi](scpi) | laboratory instruments (power supplies, multimeters) on TCP port 5025 | one query per tag, a link shared by `poll()` and `write()` with a lock, writes off by default and checked with `SYST:ERR?`, `bool` and `select` fields |
| [udp_json](udp_json) | ESP32 / scripts sending JSON datagrams | a push device with only `open` / `close` / `poll`, partial updates, value age, sender filter, own `validate` |
| [csv_file](csv_file) | a CSV log written by another program | `transport="none"`, paths in the data folder, `browse` + `items_to_tags`, cache by modification time |

```
bavis-sdk check --strict examples/scpi
bavis-sdk test examples/scpi
bavis-sdk build examples/scpi          # examples/scpi/dist/drv_scpi-1.0.0.bavispkg (unsigned)
```

Code comments are in English; texts for the operator are in Czech (the source language of BAVIS) with translations in
`i18n/en|de|sk|pl.json`.

The examples are maintained together with the BAVIS core and copied here on every SDK release – please send changes to them as an
issue; new community drivers go to [drivers](../drivers/README.md).
