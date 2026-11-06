"""SCPI over TCP – a request/response driver with optional, guarded writes.

Many laboratory instruments (power supplies, multimeters, electronic loads, counters) accept SCPI commands as text lines on
TCP port 5025 ("raw socket", IEEE 488.2 / SCPI-1999). One line = one command, a query ends with ``?`` and the instrument answers
with one line. Reference: SCPI-1999 Volume 1 (syntax), IEEE 488.2 (common commands ``*IDN?``, ``*RST``) and the programming
manual of the instrument (which headers it supports).

Tag address = SCPI header, optionally with a parameter for queries:

    MEAS:VOLT?            query → read-only tag (measured voltage)
    MEAS:VOLT? (@2)       query with a channel list
    VOLT                  setting → read as ``VOLT?``, written as ``VOLT <value>``
    OUTP                  output on/off (bool tag) → ``OUTP?`` / ``OUTP 1``

What the example shows:
- one TCP link shared by ``poll()`` (driver thread) and ``write()`` (another thread) – protected by a lock,
- ``write()`` with safety rules: writes are disabled until the user enables them on the connection, only ``rw`` tags of
  settings (no ``?``) are written, and every write is checked with ``SYST:ERR?``,
- a bool field and a select field in the connection form, a ``test`` function (``*IDN?``) and ``check_address``,
- operator texts in Czech (the source language of BAVIS) with translations in ``i18n/<lang>.json``."""
from __future__ import annotations

import re
import socket
import threading

from bavis.sdk import Driver, DriverError, DriverSpec, FieldSpec, require_host

DEFAULT_PORT = 5025
ADDR_RE = re.compile(r"^(\*?[A-Za-z][A-Za-z0-9:]*)(\?)?(?:\s+([A-Za-z0-9@(),.:+\-]+))?$")
TERMINATORS = {"lf": b"\n", "crlf": b"\r\n"}

# operator texts = translation keys (section "srv" of i18n/<lang>.json); placeholders {0}, {1} are filled by .format()
E_ADDR = "adresa = příkaz SCPI, např. MEAS:VOLT? nebo VOLT"
E_PARAM = "parametr je jen u dotazu (MEAS:VOLT? (@1))"
E_NOT_CONNECTED = "přístroj není připojen"
E_CLOSED = "přístroj ukončil spojení"
E_TIMEOUT = "přístroj neodpověděl na {0}"
E_WRITES_OFF = "zápis je u spojení vypnutý (pole Povolit zápis)"
E_READ_ONLY = "{0} je dotaz – zapisovat jde jen do nastavení bez otazníku"
E_INSTRUMENT = "přístroj hlásí chybu po {0}: {1}"


def parse_address(address: str) -> tuple[str, bool, str]:
    """→ (header, is_query, parameter). Raises ValueError with an operator text for an invalid address."""
    m = ADDR_RE.match((address or "").strip())
    if not m:
        raise ValueError(E_ADDR)
    header, query, param = m.group(1).upper(), bool(m.group(2)), m.group(3) or ""
    if param and not query:
        raise ValueError(E_PARAM)
    return header, query, param


def check_address(address: str, typ: str) -> str | None:
    """None = valid address, otherwise a message for the tag table and project validation."""
    try:
        parse_address(address)
    except ValueError as e:
        return str(e)
    return None


def read_command(address: str) -> str:
    """Query that reads the tag: the address itself for a query, ``<header>?`` for a setting."""
    header, _query, param = parse_address(address)
    return f"{header}?" + (f" {param}" if param else "")


def decode(text: str, typ: str):
    """Instrument answer → raw tag value. SCPI numbers look like ``+1.23400000E+01``; booleans are 0/1 or OFF/ON."""
    text = text.strip()
    if typ == "string":
        return text.strip('"')
    if typ == "bool":
        if text.upper() in ("1", "ON"):
            return True
        if text.upper() in ("0", "OFF"):
            return False
        return None
    try:
        value = float(text.split(",")[0])
    except ValueError:
        return None
    if value >= 9.9e37:                       # SCPI "not a number" / overload (9.91E+37)
        return None
    return value if typ in ("float32", "float64") else int(value)


def encode(raw, typ: str) -> str:
    """Value to write (already converted to the tag type by the engine) → SCPI parameter."""
    if typ == "bool":
        return "1" if raw else "0"
    if typ == "string":
        return '"' + str(raw).replace('"', "") + '"'
    return repr(float(raw)) if typ in ("float32", "float64") else str(int(raw))


class Link:
    """One TCP connection to the instrument. ``ask()`` is used from the driver thread and from writes – hence the lock."""

    def __init__(self, host: str, port: int, timeout: float, eol: bytes):
        self.host, self.port, self.timeout, self.eol = host, port, timeout, eol
        self.sock: socket.socket | None = None
        self.buf = b""
        self.lock = threading.Lock()

    def connect(self) -> None:
        with self.lock:
            self._close()
            try:
                self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            except OSError as e:
                raise DriverError(f"{self.host}:{self.port}: {e}") from None

    def close(self) -> None:
        with self.lock:
            self._close()

    def _close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock, self.buf = None, b""

    def send(self, line: str) -> None:
        """Command without an answer (a setting)."""
        with self.lock:
            self._send(line)

    def ask(self, line: str) -> str:
        """Query → one line of answer. A broken link or a timeout raises DriverError (the driver reconnects)."""
        with self.lock:
            self._send(line)
            try:
                while b"\n" not in self.buf:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        self._close()
                        raise DriverError(E_CLOSED)
                    self.buf += chunk
            except socket.timeout:
                self._close()
                raise DriverError(E_TIMEOUT.format(line)) from None
            except OSError as e:
                self._close()
                raise DriverError(str(e) or type(e).__name__) from None
            raw, _, self.buf = self.buf.partition(b"\n")
            return raw.decode("ascii", "replace").strip()

    def _send(self, line: str) -> None:
        if self.sock is None:
            raise DriverError(E_NOT_CONNECTED)
        try:
            self.sock.sendall(line.encode("ascii") + self.eol)
        except OSError as e:
            self._close()
            raise DriverError(str(e) or type(e).__name__) from None


def _params(conn) -> dict:
    p = conn.params or {}
    return {"allow_writes": bool(p.get("allow_writes", False)), "eol": TERMINATORS.get(str(p.get("eol") or "lf"), b"\n")}


def _link(conn) -> Link:
    return Link(conn.host, conn.port or DEFAULT_PORT, max(conn.timeout_ms, 100) / 1000, _params(conn)["eol"])


class ScpiDriver(Driver):
    kind = "scpi"

    def __init__(self, conn, tags, sink, data_dir="data"):
        super().__init__(conn, tags, sink, data_dir)
        self.link = _link(conn)
        self.allow_writes = _params(conn)["allow_writes"]

    def open(self):
        self.link.connect()

    def close(self):
        self.link.close()

    def poll(self) -> dict:
        """One query per tag. Raw values only – scaling, decimals and alarms are done by the BAVIS engine."""
        return {t.name: decode(self.link.ask(read_command(t.address)), t.type) for t in self.tags}

    def write(self, tag, raw) -> None:
        if not self.allow_writes:
            raise DriverError(E_WRITES_OFF)
        header, query, _param = parse_address(tag.address)
        if query or tag.access != "rw":
            raise DriverError(E_READ_ONLY.format(tag.address))
        self.link.send(f"{header} {encode(raw, tag.type)}")
        err = self.link.ask("SYST:ERR?")                       # "+0,\"No error\"" when the command was accepted
        if not err.lstrip("+").startswith("0"):
            raise DriverError(E_INSTRUMENT.format(header, err))
        self.stats["writes"] += 1


def test_once(conn, ctx) -> dict:
    """The *Test connection* button: identification of the instrument (IEEE 488.2 ``*IDN?``)."""
    link = _link(conn)
    link.connect()
    try:
        idn = link.ask("*IDN?")
    finally:
        link.close()
    return {"msg": f"{link.host}:{link.port}: {idn}"}


SPECS = [DriverSpec(
    kind="scpi", label="SCPI přístroj (TCP, příklad)", short="SCPI", category="it", order=900, transport="tcp",
    default_port=DEFAULT_PORT, id_prefix="scpi", make=lambda conn, tags, sink, data_dir: ScpiDriver(conn, tags, sink, data_dir),
    check_address=check_address, test=test_once, validate=require_host, summary="{host}:{port}",
    fields=(
        FieldSpec("allow_writes", "Povolit zápis", "bool", default=False,
                  help="Zápis nastavení do přístroje (napětí, proud, výstup). Vypnuto = jen čtení."),
        FieldSpec("eol", "Konec řádku", "select", default="lf", options=(("lf", "LF (\\n)"), ("crlf", "CR LF (\\r\\n)")),
                  help="Ukončení příkazu – většina přístrojů přijímá LF"),
    ),
    addr_help="Příkaz SCPI: MEAS:VOLT? (dotaz, jen čtení) · VOLT (nastavení – čte VOLT?, zapisuje VOLT <hodnota>) · OUTP (výstup)",
    addr_placeholder="MEAS:VOLT?", defaults={"host": "192.168.0.20"},
)]
