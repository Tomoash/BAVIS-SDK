"""Hello BAVIS – the smallest complete driver. It talks to no device: values are generated in memory.

Read this one first. It has everything a driver needs and nothing else: ``check_address``, a ``Driver`` with ``poll`` and
``write`` and a ``DriverSpec``. The other examples add the real work – a network link, a protocol, a fake device in the tests.

Tag addresses:

    counter      number of read cycles since the connection started (read only)
    sine         sine wave between -1 and 1 with the period from the connection form (read only)
    setpoint     a value you can write (tag access ``rw``) – it is kept in memory and read back
    greeting     text "Hello from BAVIS" (tag type ``string``)

What the example shows:
- ``transport="none"`` (no host or port in the form) and ``sim="free"`` (the connection needs no physical device in simulation),
- ``poll()`` returning raw values for the tags of the connection, ``None`` for a value that is not valid,
- ``write()`` with the basic safety rule: only ``rw`` tags are written,
- a number field (``period_s``) stored in ``Connection.params``,
- operator texts in Czech (the source language of BAVIS) with translations in ``i18n/<lang>.json``."""
from __future__ import annotations

import math
import time

from bavis.sdk import Driver, DriverError, DriverSpec, FieldSpec

ADDRESSES = ("counter", "sine", "setpoint", "greeting")

# operator texts = translation keys (section "srv" of i18n/<lang>.json); placeholders {0}, {1} are filled by .format()
E_ADDR = "adresa = counter, sine, setpoint nebo greeting"
E_TEXT = "greeting je text – tag musí mít typ string"
E_READ_ONLY = "{0} jde jen číst – zapisovat lze do setpoint s přístupem rw"


def check_address(address: str, typ: str) -> str | None:
    """None = valid address, otherwise a message for the tag table and project validation."""
    address = (address or "").strip().lower()
    if address not in ADDRESSES:
        return E_ADDR
    if address == "greeting" and typ != "string":
        return E_TEXT
    return None


class HelloDriver(Driver):
    kind = "hello"

    def __init__(self, conn, tags, sink, data_dir="data"):
        super().__init__(conn, tags, sink, data_dir)
        self.period = max(float((conn.params or {}).get("period_s") or 60), 1.0)
        self.counter = 0
        self.setpoint = 0.0
        self.t0 = time.monotonic()

    def open(self):
        """Called before the first read and after every error. A real driver connects to its device here."""
        self.counter = 0

    def close(self):
        """Called after an error and when the connection stops. A real driver closes its link here."""

    def poll(self) -> dict:
        """One read cycle: {tag name: raw value}. Scaling, decimals, alarms and history are done by the BAVIS engine."""
        self.counter += 1
        now = {
            "counter": self.counter,
            "sine": math.sin(2 * math.pi * (time.monotonic() - self.t0) / self.period),
            "setpoint": self.setpoint,
            "greeting": "Hello from BAVIS",
        }
        return {t.name: now.get(t.address.strip().lower()) for t in self.tags}

    def write(self, tag, raw) -> None:
        """Called from another thread than ``poll()``; ``raw`` is already converted to the tag type by the engine."""
        if tag.address.strip().lower() != "setpoint" or tag.access != "rw":
            raise DriverError(E_READ_ONLY.format(tag.address))
        self.setpoint = float(raw)
        self.stats["writes"] += 1


SPECS = [DriverSpec(
    kind="hello", label="Hello BAVIS (příklad)", short="Hello", category="it", order=900, transport="none", sim="free",
    id_prefix="hello", make=lambda conn, tags, sink, data_dir: HelloDriver(conn, tags, sink, data_dir),
    check_address=check_address, summary="{period_s|60} s",
    fields=(FieldSpec("period_s", "Perioda sinusu [s]", "number", default=60, min=1, max=86400,
                      help="Za jak dlouho sine projde celou vlnu"),),
    addr_help="counter (počet cyklů) · sine (sinus −1 až 1) · setpoint (zápis, přístup rw) · greeting (text)",
    addr_placeholder="sine",
)]
