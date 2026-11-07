# 3. Driver patterns

[Guides](README.md) · previous: [Your first driver](02-first-driver.md) · next: [Testing](04-testing.md)

Devices differ mainly in **who starts the communication** and **how much data comes at once**. Every pattern below has a complete
example in [examples](../../examples/README.md).

## Request/response – one request per cycle

The device returns all data in one answer (web API, JSON, XML). `poll()` makes one request and picks the tag values from the answer.

```python
def poll(self) -> dict:
    doc = fetch(self.conn)                                  # one HTTP request
    return {t.name: convert(resolve(doc, t.address), t.type) for t in self.tags}
```

Example: [`http_json`](../../examples/http_json). A binary protocol over UDP with `struct`, a check that the answer belongs to
the query and a query interval independent of the read cycle: [`ntp`](../../examples/ntp).

## Request/response – one request per tag

Text protocols of instruments (SCPI, ASCII protocols of scales and controllers): one line out, one line back. Keep the connection
open between cycles, limit reading the answer by the connection timeout (`conn.timeout_ms`) and close the connection on an error –
the engine opens it again.

Example: [`scpi`](../../examples/scpi) – a shared link with a lock, writes checked with `SYST:ERR?`.

## Block reads of registers

With register protocols (Modbus-like, PLC memory areas) one request per block is much faster than one per tag. `merge_ranges`
groups nearby addresses into blocks:

```python
from bavis.sdk import merge_ranges

def poll(self) -> dict:
    out = {}
    items = [(register(t.address), words(t.type), t) for t in self.tags]       # (start, size, anything)
    for start, count, block_tags in merge_ranges(items, max_gap=8, max_len=120):
        regs = self.link.read_registers(start, count)                          # one request per block
        for t in block_tags:
            out[t.name] = decode(regs, register(t.address) - start, t.type)
    return out
```

`max_gap` = how many unused registers may lie between tags of one block, `max_len` = the largest block the device reads in one
request (see the protocol documentation).

Tags may have their own read period (`Tag.poll_ms`). `self.every(tag)` returns every how many cycles of the connection the tag is
due, and `self.due(every)` whether it is due in this cycle – so slow tags can be read less often.

Example: [`modbus_ascii`](../../examples/modbus_ascii) – blocks per register table, LRC, protocol exceptions as operator messages.

## Serial lines (RS-232 / RS-485)

With `transport="serial"` the connection form uses the core fields `serial_port`, `baudrate`, `parity` and `stopbits`
(`conn.serial_port` …). Import pyserial inside a function, not at module level. Accept `socket://host:port` too – serial-to-Ethernet
converters in transparent mode are common, and the tests can then use a TCP fake device without hardware or pyserial.
Examples: [`modbus_ascii`](../../examples/modbus_ascii) (request/response), [`dsmr_p1`](../../examples/dsmr_p1) (the meter pushes).

## Devices that push data

ESP32 sensors, UDP telegrams, some energy meters: the device sends, BAVIS listens. The usual `open` / `close` / `poll` is enough:

* `open()` opens the listening socket,
* `poll()` waits a short time for messages and returns **only the tags that arrived** – the engine keeps the other values,
* a value that has not arrived for a long time is returned as `None`; when nothing arrives at all, `poll()` raises `DriverError`
  and the connection shows as disconnected until data comes again.

```python
def poll(self) -> dict:
    out, until = {}, time.monotonic() + min(1.0, self.conn.poll_ms / 1000)
    while time.monotonic() < until:
        try:
            data, _addr = self.sock.recvfrom(8192)
        except socket.timeout:
            continue
        ...                                         # parse the message, out[tag] = value
    if time.monotonic() - self.last_rx > self.max_age:
        raise DriverError(E_NO_DATA.format(...))
    return out
```

Example: [`udp_json`](../../examples/udp_json) – routing by device, a sender filter, value age. A byte stream with start and
end markers and a CRC (a smart meter on a serial line): [`dsmr_p1`](../../examples/dsmr_p1).

A listening port accepts data from anyone in the network. Offer a sender filter and say in the help text that the port belongs to
a trusted network only.

## Without a network: files and local sources

`transport="none"` hides the IP address and port. Join relative paths with the BAVIS data folder (`data_dir` from `make`,
`ctx.data_dir` in `test` and `browse`) and allow only the extensions you really read. Remember the modification time of the file
between cycles and read it only when it changed.

Example: [`csv_file`](../../examples/csv_file).

## Browsing variables

When the device can list its variables, add `browse` and `items_to_tags` to the description. The user then opens **Tag import**
in the tag editor, chooses the device browsing tab and the connection, clicks **Connect and load variables**, selects variables and
the tags are created.

```python
def browse(conn, ctx, node_id=None) -> dict:
    return {"flat": True, "items": [
        {"name": "temp_in", "address": "temp_in", "type": "float32", "datatype": "CSV", "writable": False,
         "comment": "temp_in = 21.5"},
    ]}


def items_to_tags(items, conn_id, prefix, group, opts=None) -> dict:
    tags = [{"name": prefix + it["name"], "conn": conn_id, "address": it["address"], "type": it.get("type") or "float32",
             "access": "rw" if it.get("writable") else "r", "group": group, "desc": it.get("comment", "")} for it in items]
    return {"tags": tags, "skipped": [], "info": "my driver"}
```

A list item: `name` and `comment` are shown, `datatype` is the type in the device, `type` the tag type (an item without it cannot
be selected), `writable` = writes are possible. `items_to_tags` gets the selected items and returns tag definitions.

Tag names must match `^[A-Za-z_][A-Za-z0-9_.\-\[\]]{0,99}$` and be unique within the import – the `csv_file` example shows the
conversion and numbering of duplicates. When the interface is used by a running connection with other settings, raise `Conflict`
(the user gets a clear message instead of an error).

## Writes without surprises

* Refuse writes to tags with `access="r"`.
* For devices where a wrong value can damage something, keep writes disabled by a connection field (`FieldSpec("allow_writes", …,
  "bool", default=False)`) until the user enables them on purpose.
* After a write check that the device accepted it (error queue, acknowledgement, read back) and raise `DriverError` otherwise – the
  user sees the error at the control.
* Never write cyclically to registers stored in flash or EEPROM (memory wear).

## Passwords and tokens

A password, API key or token belongs to a field `FieldSpec("token", "Token", "password", secret=True)`. BAVIS then masks it in the
API, CSV exports, revision diffs and backups. Never put it into code, logs or error texts. List the key in
`DriverSpec.secrets` too. Example: [`prometheus`](../../examples/prometheus) (bearer token).

## Simulation

`DriverSpec.sim="local"` (default) means that in simulation mode the connection may only connect to `127.0.0.1` – your simulator,
not the real device. `sim="free"` is for drivers without a physical link (calculations, generators – example
[`hello`](../../examples/hello)). The user can also switch on **Simulate** on a connection; its tags then run virtually without
the driver.

## Status and diagnostics

`status()` returns a dictionary that BAVIS shows in **Objects → Communication**. Add your own counters:

```python
def status(self) -> dict:
    return {**super().status(), "counters": dict(self.link.counters)}
```
