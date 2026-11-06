"""UDP JSON – a *push* driver: the device sends, BAVIS listens.

Small devices often send their measurements on their own instead of answering queries. Here every datagram is one JSON object
sent to the UDP port of the connection, for example from an ESP32 every 10 s:

    {"device": "greenhouse", "temp": 21.4, "hum": 55, "door": false}

Tag address = ``<key>`` (from any device) or ``<device>/<key>`` (only from the device with that ``"device"`` value).
Several devices can share one connection; tags only change when a datagram with their key arrives.

What the example shows – an event-driven driver built only from ``open`` / ``close`` / ``poll``:
- ``open()`` binds the UDP socket, ``poll()`` waits a short time for datagrams and returns **only the tags that arrived**
  (the engine keeps the other values), so no private parts of the ``Driver`` base class are needed,
- staleness: a tag without a new value for longer than *Max. age* becomes invalid (``None``); when nothing at all arrives for
  that long, ``poll()`` raises ``DriverError`` and the connection shows as disconnected until data comes again,
- a ``number`` field with limits, ``transport="udp"`` (the port of the connection is the listening port),
- a ``validate`` rule of its own and a ``test`` function that waits for one datagram.

Security: the port accepts data from anyone who can reach it. Use it only in a trusted network, or restrict the sender with the
field *Allowed sender*."""
from __future__ import annotations

import json
import re
import socket
import time

from bavis.sdk import Driver, DriverError, DriverSpec, FieldSpec

DEFAULT_PORT = 5005
MAX_DATAGRAM = 8192
ADDR_RE = re.compile(r"^(?:([A-Za-z0-9_\-.]{1,64})/)?([A-Za-z0-9_\-]{1,64})$")

E_ADDR = "adresa = klíč (temp) nebo zařízení/klíč (sklep/temp)"
E_BIND = "UDP port {0} nelze otevřít: {1}"
E_NO_DATA = "žádná data na UDP portu {0} za {1} s"
E_SENDER = "povolený odesílatel musí být IP adresa"
M_TEST_OK = "UDP {0}: přišla data od {1} ({2} hodnot)"


def check_address(address: str, typ: str) -> str | None:
    return None if ADDR_RE.match((address or "").strip()) else E_ADDR


def parse(data: bytes) -> tuple[str, dict] | None:
    """Datagram → (device, {key: value}); None for anything that is not a JSON object."""
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None
    device = str(doc.get("device") or "")
    return device, {str(k): v for k, v in doc.items() if k != "device"}


def convert(value, typ: str):
    """JSON value → raw tag value (None when it does not fit the tag type)."""
    if isinstance(value, bool):
        return value if typ == "bool" else float(value)
    if isinstance(value, (int, float)):
        return bool(value) if typ == "bool" else float(value)
    if isinstance(value, str) and typ == "string":
        return value
    return None


def _params(conn) -> dict:
    p = conn.params or {}
    return {"max_age_s": float(p.get("max_age_s") or 60), "sender": str(p.get("sender") or "").strip()}


def _bind(conn) -> socket.socket:
    port = conn.port or DEFAULT_PORT
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind((conn.host or "0.0.0.0", port))
    except OSError as e:
        s.close()
        raise DriverError(E_BIND.format(port, e)) from None
    return s


class UdpJsonDriver(Driver):
    kind = "udp_json"

    def __init__(self, conn, tags, sink, data_dir="data"):
        super().__init__(conn, tags, sink, data_dir)
        p = _params(conn)
        self.max_age, self.sender = p["max_age_s"], p["sender"]
        self.sock: socket.socket | None = None
        self.seen: dict[str, float] = {}           # tag name → time of its last value
        self.last_rx = 0.0
        self.routes: dict[tuple[str, str], list] = {}
        for t in tags:
            m = ADDR_RE.match(t.address.strip())
            if m:
                self.routes.setdefault((m.group(1) or "", m.group(2)), []).append(t)

    def open(self):
        self.sock = _bind(self.conn)
        self.sock.settimeout(0.2)
        self.last_rx = time.monotonic()           # waiting for the first datagram counts from (re)connecting

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def poll(self) -> dict:
        out: dict = {}
        wait_until = time.monotonic() + min(1.0, self.conn.poll_ms / 1000)
        while time.monotonic() < wait_until:            # collect everything that arrives in this cycle
            try:
                data, (addr, _port) = self.sock.recvfrom(MAX_DATAGRAM)
            except socket.timeout:
                continue
            if self.sender and addr != self.sender:
                continue
            msg = parse(data)
            if msg is None:
                continue
            self.last_rx = now = time.monotonic()
            device, values = msg
            for key, value in values.items():
                for t in self.routes.get(("", key), []) + (self.routes.get((device, key), []) if device else []):
                    out[t.name] = convert(value, t.type)
                    self.seen[t.name] = now
        now = time.monotonic()
        for name, t_last in list(self.seen.items()):     # too old → invalid, once
            if now - t_last > self.max_age and name not in out:
                out[name] = None
                del self.seen[name]
        if now - self.last_rx > self.max_age:
            raise DriverError(E_NO_DATA.format(self.conn.port or DEFAULT_PORT, round(self.max_age)))
        return out


def validate(conn, project=None) -> list[tuple[str, str]]:
    """Connection rule: the allowed sender (if any) must be an IPv4 address. Returns (field, message) pairs."""
    sender = _params(conn)["sender"]
    if sender:
        try:
            socket.inet_aton(sender)
        except OSError:
            return [("params.sender", E_SENDER)]
    return []


def test_once(conn, ctx) -> dict:
    """*Test connection*: wait for one datagram (at most the connection timeout, at least 3 s)."""
    s = _bind(conn)
    try:
        s.settimeout(max(3.0, conn.timeout_ms / 1000))
        try:
            data, (addr, _port) = s.recvfrom(MAX_DATAGRAM)
        except socket.timeout:
            raise DriverError(E_NO_DATA.format(conn.port or DEFAULT_PORT, round(s.gettimeout()))) from None
    finally:
        s.close()
    msg = parse(data)
    return {"msg": M_TEST_OK.format(conn.port or DEFAULT_PORT, addr, len(msg[1]) if msg else 0)}


SPECS = [DriverSpec(
    kind="udp_json", label="UDP JSON – příjem dat (příklad)", short="UDP JSON", category="it", order=900, transport="udp",
    default_port=DEFAULT_PORT, id_prefix="udp", make=lambda conn, tags, sink, data_dir: UdpJsonDriver(conn, tags, sink, data_dir),
    check_address=check_address, test=test_once, validate=validate, summary="UDP {port}",
    fields=(
        FieldSpec("max_age_s", "Max. stáří hodnoty [s]", "number", default=60, min=1, max=86400,
                  help="Hodnota bez nové zprávy po tuto dobu je neplatná"),
        FieldSpec("sender", "Povolený odesílatel", "text", default="", placeholder="192.168.0.50",
                  help="IP adresa zařízení; prázdné = data od kohokoli v síti"),
    ),
    addr_help="Klíč ve zprávě JSON: temp · nebo zařízení/klíč: sklep/temp (pole \"device\" ve zprávě)",
    addr_placeholder="temp", defaults={"host": "0.0.0.0"},
)]
