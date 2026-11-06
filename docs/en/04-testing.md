# 4. Testing

[Guides](README.md) · previous: [Driver patterns](03-patterns.md) · next: [Building and installing](05-building-and-installing.md)

Every driver has tests that run **without the real device**: a *fake device* answers instead – a small server in the same process
that speaks the same protocol. The tests then run on a laptop, in CI and in the review of a contribution.

## Running

```
bavis-sdk test <workspace>                         # pytest against the core of this installation
bavis-sdk test <workspace> -- -k write -x -v       # pytest options after --
```

`test` puts the BAVIS core and the workspace on the import path; `tests/conftest.py` from the skeleton adds the package folder, so
the core finds your driver the same way as after installation (`sdk.lookup_driver("my_scale")`, `validate_project` …).

## The `bavis.sdk.testing` helpers

```python
from bavis.sdk import testing

def test_reads_and_writes(dev):
    conn = testing.connection("my_scale", port=dev.port, params={"station": 1})
    tags = testing.tags(conn, [("W1", "W1"), ("W2", "W2", "float32", "rw")])
    assert testing.poll_once(conn, tags) == {"W1": 12.5, "W2": 0.0}
    with testing.run_driver(conn, tags) as run:                  # like the engine: own thread, reconnects, status
        assert testing.wait_for(lambda: run.sink.connected and run.sink.values.get("W1") == 12.5)
        run.driver.write(tags[1], 3.0)
```

| Helper | Purpose |
| --- | --- |
| `connection(driver, port=…, params=…)` | a connection with short test timings (period 50 ms, timeout 1 s) |
| `tags(conn, [(name, address[, type[, access]]) …])` | tags of the connection (type `float32`, access `r` by default) |
| `poll_once(conn, tags, spec=None, data_dir=".")` | one cycle: `open()`, `poll()`, `close()` → dictionary of values |
| `run_driver(conn, tags, spec=None, data_dir=".")` | the driver in its own thread like in the engine; `.sink` records values and statuses, `.driver` is the instance |
| `RecordingSink` | the engine stand-in: `values` (last values), `batches` (every call), `statuses`, `connected` |
| `wait_for(condition, timeout=5)` | wait for a condition instead of a fixed `sleep` |
| `free_port()` / `free_port(socket.SOCK_DGRAM)` | a free TCP / UDP port chosen by the OS |

Pass `spec` to test one particular description (`spec=my_scale.SPECS[0]`); without it the registered kind is used.

## Fake devices

A TCP device – `socketserver` on `127.0.0.1` and port `0` (chosen by the OS):

```python
class FakeDevice(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.port = self.server_address[1]
        self.regs = {"W1": "12.5"}
        threading.Thread(target=self.serve_forever, daemon=True).start()
```

An HTTP device – `http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)` (example `http_json`). UDP – the test itself sends
datagrams to a port from `free_port(socket.SOCK_DGRAM)` (example `udp_json`). Files – pytest's `tmp_path` (example `csv_file`).

To test an outage, let the fake device remember its open connections and close them (`stop()` in the skeleton and in the `scpi`
example) – `shutdown()` of the server alone does not close connections that are already open.

## What to test every time

1. **The description is valid**: `assert sdk.check_spec(SPECS[0]) is None`.
2. **Addresses**: valid and invalid examples for `check_address` (a parametrized test).
3. **Reading**: `poll_once` returns the expected values of all types, an unknown address = `None` for that tag only.
4. **Life cycle**: in `run_driver` the connection comes up, after the device disappears it shows as disconnected and the tags lose
   their values (`None`), and when the device returns it reconnects.
5. **Writing**: the write reaches the device, a refused write raises `DriverError`, a write to a read-only tag is refused.
6. **Connection test**: success and failure (unreachable device – a port from `free_port()` where nothing listens).
7. **Connection fields**: `validate_project` with default and wrong field values (the skeleton shows it in
   `test_spec_registered_with_params_field`).

## Rules

* **No fixed ports** – tests run in parallel and on shared CI machines. `check` reports a fixed port in tests.
* **No guessed `sleep`** – `testing.wait_for(...)` with a sensible timeout.
* **No hardware and no internet** – a test that needs a real device does not belong in the repository (describe it in the
  driver's README as a manual test).
* Import driver functions whose name starts with `test` (e.g. `test_once`) under another name
  (`from … import test_once as connection_test`), otherwise pytest would run them as tests.
