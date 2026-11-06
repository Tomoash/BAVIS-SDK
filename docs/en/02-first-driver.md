# 2. Your first driver step by step

[Guides](README.md) · previous: [Getting started](01-getting-started.md) · next: [Driver patterns](03-patterns.md)

This guide walks through the skeleton made by `bavis-sdk new` and shows what to change for a real device. The example is a scale
that answers text queries on a TCP port. Complete drivers are in [examples](../../examples/README.md).

## How a driver lives in BAVIS

1. In **Configuration → Connections** the user creates a connection of your kind and fills in the form (IP address, port and your
   own fields).
2. In the tag table every tag gets an **address** in your format (`R10`, `MEAS:VOLT?`, `boiler.flow.temp` …). The address is
   checked by your `check_address` function – right in the table and when the project is saved.
3. When the project is activated, the engine calls `make(conn, tags, sink, data_dir)` → an instance of your driver, and `start()`.
4. The `Driver` base class runs its own thread: `open()`, then `poll()` every `conn.poll_ms`. An exception in `open()` or `poll()`
   = the connection is down (state, error counter, tags without values) and it is tried again after 2 s.
5. Writes from screens, logic or the API call `write(tag, raw)` – **from another thread** than `poll()`.

`poll()` returns **raw** values `{tag name: value | None}`. Scaling, decimals, dead band, history and alarms are done by the
engine. `None` means an invalid value.

## Step 1: the skeleton

```
bavis-sdk new my_scale --label "Moje váha" --dir ~/drivers/scale
```

Open `bavis_drv_my_scale/drivers/my_scale.py`. It has four parts: texts, the address check, the driver class and the `SPECS`
description. We go from the bottom, because the description decides what the user sees.

## Step 2: the driver description (`DriverSpec`)

```python
SPECS = [DriverSpec(
    kind="my_scale",                  # kind = package name after bavis_drv_; unique in the whole installation
    label="Moje váha",                # name in the driver list (Czech = source language, translations in i18n)
    category="it", order=900,         # group in the menu (plc, building, energy, meter, maker, it) and order
    transport="tcp",                  # tcp | udp | serial | url | none – which connection fields the form shows
    default_port=4001,
    id_prefix="scale",                # prefix of new connection IDs (scale1, scale2 …)
    make=_make,                       # (conn, tags, sink, data_dir) → driver instance
    check_address=check_address,      # (address, type) → None | error text
    test=test_once,                   # the Test connection button (optional)
    validate=require_host,            # connection rules (here: the IP address is required)
    summary="{host}:{port} stanice {station}",     # connection summary in the overview
    fields=(FieldSpec("station", "Stanice", "number", default=1, min=1, max=247,
                      help="Číslo stanice v dotazech"),),
    addr_help="W<číslo> – kanál hmotnosti, např. W1",
    addr_placeholder="W1",
    defaults={"host": "192.168.0.1"},
)]
```

The most important fields:

| Field | Purpose |
| --- | --- |
| `fields` | your own fields of the connection form. Values are stored in `conn.params` (`conn.params["station"]`). Types `text`, `number`, `bool`, `select` (`options=(("value", "label"), …)`), `password` (with `secret=True` it is masked in the API, exports and backups), `serial_port`, `file`, `list`. A field can depend on another one: `show_if={"mode": ("tcp",)}`. |
| `validate` | `validate(conn, project=None) → [(field, text), …]`. The field is `host`, `port`, … or `params.<key>`. An empty list = valid. |
| `test` | `test(conn, ctx) → {"msg": "…"}`; an exception = the test failed and the user sees its text. `ctx.data_dir`, `ctx.simulate`. |
| `browse` + `items_to_tags` | tag import by browsing the device – list its variables and create tags from the selected ones (see [Patterns](03-patterns.md#browsing-variables)). |
| `license` | keep the default `"comm"`: the connection needs the communication licence like the drivers of the core. |

The full list is in the reference [drivers.md](../drivers.md#4-the-api).

## Step 3: the tag address

Design the address so that the user can copy it from the device documentation. Make the check strict – whatever passes
`check_address` must work in `poll()`.

```python
ADDR_RE = re.compile(r"^W(\d{1,2})$")
E_ADDR = "adresa W<číslo>, např. W1 (W1–W16)"


def check_address(address: str, typ: str) -> str | None:
    m = ADDR_RE.match((address or "").strip().upper())
    if not m or not 1 <= int(m.group(1)) <= 16:
        return E_ADDR
    return None
```

`typ` is the tag type (`bool`, `int8`, `uint8`, `int16`, `uint16`, `int32`, `uint32`, `int64`, `float32`, `float64`, `string`).
If the device does not support a type, return an error for it as well.

## Step 4: the driver class

```python
class ScaleDriver(Driver):
    kind = "my_scale"

    def __init__(self, conn, tags, sink, data_dir="data"):
        super().__init__(conn, tags, sink, data_dir)
        self.station = int((conn.params or {}).get("station", 1))
        self.link = Link(conn.host, conn.port or 4001, conn.timeout_ms / 1000)

    def open(self):
        self.link.connect()                    # error → DriverError, the engine tries again after 2 s

    def close(self):
        self.link.close()

    def poll(self) -> dict:
        out = {}
        for t in self.tags:
            ok, text = self.link.ask(f"{self.station} GET {t.address.strip().upper()}")
            out[t.name] = float(text) if ok else None
        return out

    def write(self, tag, raw) -> None:
        ok, text = self.link.ask(f"{self.station} SET {tag.address} {raw}")
        if not ok:
            raise DriverError(E_WRITE.format(tag.address, text))
        self.stats["writes"] += 1
```

What you have: `self.conn` (`host`, `port`, `poll_ms`, `timeout_ms`, `params`), `self.tags` and `self.by_name` (tags of the
connection: `name`, `address`, `type`, `access`), `self.stats`, `self.last_error`, `self.connected`. You can extend `status()`
with your own data – it is shown in **Objects → Communication**.

Rules worth following from the start:

* **One link to the device is shared by `poll()` and `write()`** – protect it with a lock (`threading.Lock`). The skeleton does
  that in its `Link` class.
* **A connection error = an exception** (`DriverError` with a text for the operator). An error of one tag (the device does not know
  the address) = `None` for that tag only, and optionally `self.last_error`.
* **Import device libraries inside functions**, not at the top of the module. The core imports every driver module at start-up.
* **Write only where it makes sense**: refuse writes to read-only tags, keep writes disabled for dangerous devices until the user
  enables them (see the [SCPI example](../../examples/scpi)) and never write cyclically to flash or EEPROM.

## Step 5: texts and translations

The source language of BAVIS is Czech: labels, help texts and messages are written in Czech and the translations go to
`bavis_drv_<name>/i18n/<lang>.json`:

```json
{
 "srv": {
  "Moje váha": "My scale",
  "adresa W<číslo>, např. W1 (W1–W16)": "address W<number>, e.g. W1 (W1–W16)",
  "zápis {0} odmítnut: {1}": "write {0} refused: {1}"
 }
}
```

* The key is exactly the Czech source text. Keep messages with placeholders (`{0}`, `{1}`) as constants and fill them with
  `.format()` only when raising – the core translates the template and the inserted values.
* `check` reports missing `en`, `de`, `sk`, `pl` files and texts in `en.json` that equal the source (not translated).
* If you do not speak Czech, write the texts in English and say so in the pull request – we will add the translation.

## Step 6: the fake device and tests

Change `tests/test_my_scale.py` so that the fake device speaks the same protocol as the real one. Tests must run without hardware
and on ports chosen by the OS. Details in [Testing](04-testing.md).

```
bavis-sdk test ~/drivers/scale                     # all tests
bavis-sdk test ~/drivers/scale -- -k write -x      # pytest options after --
```

## Step 7: check and build

```
bavis-sdk check --strict ~/drivers/scale
bavis-sdk build ~/drivers/scale
```

Continue with [Building and installing](05-building-and-installing.md).
