"""P1 port (DSMR) – a meter that pushes text telegrams on a serial line: framing, CRC-16 and value age.

Smart electricity meters in the Netherlands, Belgium, Luxembourg and Sweden have a read-only *P1 port* (RJ12). Every 1 s
(DSMR 5) or 10 s (DSMR 4) the meter sends a telegram: a header line ``/XXX5…``, data lines ``<OBIS code>(<value>*<unit>)``
and an end line ``!<CRC>``. Gas, water and heat meters connected to the electricity meter over M-Bus appear in the same
telegram (``0-1:24.2.1``). The port is a serial line (DSMR 4/5: 115 200 Bd 8N1, DSMR 2.2/3: 9 600 Bd 7E1) with an inverted
data signal – use a P1 cable with an inverter, or a P1-to-Wi-Fi/Ethernet bridge that forwards the raw telegrams on a TCP port
(``socket://address:port``). Reference: *P1 Companion Standard, Dutch Smart Meter Requirements (DSMR) 5.0.2* (Netbeheer
Nederland) – telegram format, CRC (CRC-16, polynomial x¹⁶ + x¹⁵ + x² + 1, LSB first, from ``/`` to ``!``), OBIS codes.

Tag address = OBIS code of a data line, the value is the last value in parentheses:

    1-0:1.8.1      energy delivered to the client, tariff 1 [kWh]   1-0:2.8.1   energy delivered by the client [kWh]
    1-0:1.7.0      power delivered [kW]                             1-0:2.7.0   power received [kW]
    1-0:32.7.0     voltage L1 [V]                                   1-0:31.7.0  current L1 [A]
    0-0:96.14.0    tariff indicator                                 0-1:24.2.1  gas meter reading [m³]

What the example shows:
- a *push* device on a byte stream: ``poll()`` only collects what arrived, cuts complete telegrams out of the buffer and keeps
  the last values – the driver never sends anything (the P1 port is read only),
- a checksum (CRC-16/ARC) over a frame with start and end markers, and recovery from a broken telegram,
- value age: no valid telegram for ``max_age_s`` = error of the connection,
- the same serial line abstraction as the Modbus ASCII example (COM port through pyserial, or ``socket://``)."""
from __future__ import annotations

import re
import socket
import time

from bavis.sdk import Driver, DriverError, DriverSpec, FieldSpec

OBIS_RE = re.compile(r"^\d{1,3}-\d{1,3}:\d{1,3}\.\d{1,3}\.\d{1,3}$")
LINE_RE = re.compile(r"^(\d{1,3}-\d{1,3}:\d{1,3}\.\d{1,3}\.\d{1,3})((?:\([^()]*\))+)\s*$")
END_RE = re.compile(rb"!([0-9A-Fa-f]{4})?\r?\n")
MAX_BUFFER = 64 * 1024

# operator texts = translation keys (section "srv" of i18n/<lang>.json); placeholders {0}, {1} are filled by .format()
E_ADDR = "adresa = kód OBIS, např. 1-0:1.8.1 (energie tarif 1) nebo 1-0:1.7.0 (příkon)"
E_PORT = "chybí COM port (nebo socket://adresa:port převodníku P1)"
E_NO_DATA = "žádný platný telegram za {0} s"
E_SERIAL_LIB = "chybí knihovna pyserial pro COM port"
E_CLOSED = "převodník P1 ukončil spojení"
E_READ_ONLY = "port P1 jde jen číst"
M_TEST_OK = "{0}: telegram {1}, {2} hodnot"


def check_address(address: str, typ: str) -> str | None:
    return None if OBIS_RE.match((address or "").strip()) else E_ADDR


def crc16(data: bytes) -> int:
    """CRC-16/ARC: polynomial 0x8005 processed LSB first (0xA001), initial value 0, no final XOR."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def extract(buf: bytes) -> tuple[list[bytes], list[bytes], bytes]:
    """Byte buffer → (valid telegrams, rejected telegrams, rest of the buffer that may still grow into a telegram).

    A telegram runs from ``/`` to ``!`` followed by four hex digits of the CRC (DSMR 4/5) or nothing (DSMR 2.2/3, no CRC)."""
    good, bad = [], []
    while True:
        start = buf.find(b"/")
        if start < 0:
            return good, bad, b""
        buf = buf[start:]
        end = END_RE.search(buf)
        if not end:
            return good, bad, buf[-MAX_BUFFER:]
        body = buf[:end.start() + 1]                       # '/' … '!' – the part covered by the CRC
        nxt = buf.find(b"/", 1)
        if 0 < nxt < end.start():                          # a new header before the end: the previous telegram was cut
            bad.append(buf[:nxt])
            buf = buf[nxt:]
            continue
        crc = end.group(1)
        if crc is None or int(crc, 16) == crc16(body):
            good.append(body)
        else:
            bad.append(body)
        buf = buf[end.end():]


def parse(telegram: bytes) -> tuple[str, dict[str, list[str]]]:
    """Telegram → (meter identification from the header, {OBIS code: [values in parentheses]})."""
    lines = telegram.decode("ascii", "replace").splitlines()
    ident = lines[0][1:].strip() if lines else ""
    data = {}
    for line in lines[1:]:
        m = LINE_RE.match(line.strip())
        if m:
            data[m.group(1)] = re.findall(r"\(([^()]*)\)", m.group(2))
    return ident, data


def convert(groups: list[str] | None, typ: str):
    """Values of one line → raw tag value: the last group, unit after ``*`` removed (``001234.567*kWh`` → 1234.567)."""
    if not groups:
        return None
    text = groups[-1]
    if typ == "string":
        return text
    number = text.split("*", 1)[0]
    try:
        value = float(number)
    except ValueError:
        return None
    if typ == "bool":
        return value != 0
    return value if typ in ("float32", "float64") else int(value)


class Line:
    """Receiving side of the P1 port: a COM port through pyserial, or ``socket://host:port`` of a P1 bridge."""

    def __init__(self, conn):
        self.port = (conn.serial_port or "").strip()
        self.baudrate, self.parity, self.stopbits = conn.baudrate, conn.parity, conn.stopbits
        self.bytesize = int((conn.params or {}).get("bytesize") or 8)
        self.dev = None

    def open(self) -> None:
        if not self.port:
            raise DriverError(E_PORT)
        self.close()
        if self.port.lower().startswith("socket://"):
            host, _, port = self.port[9:].rpartition(":")
            try:
                self.dev = socket.create_connection((host, int(port)), timeout=5)
            except (OSError, ValueError) as e:
                raise DriverError(f"{self.port}: {e}") from None
            return
        try:
            import serial                      # heavy / optional library: only inside a function (SDK rule 2)
        except ImportError:
            raise DriverError(E_SERIAL_LIB) from None
        try:
            self.dev = serial.Serial(self.port, self.baudrate, bytesize=self.bytesize, parity=self.parity,
                                     stopbits=self.stopbits, timeout=0)
        except (serial.SerialException, ValueError) as e:
            raise DriverError(f"{self.port}: {e}") from None

    def close(self) -> None:
        dev, self.dev = self.dev, None
        if dev is not None:
            try:
                dev.close()
            except OSError:
                pass

    def read(self, wait: float) -> bytes:
        """Whatever arrived within ``wait`` seconds (b"" when nothing). A closed bridge raises DriverError."""
        if isinstance(self.dev, socket.socket):
            self.dev.settimeout(wait)
            try:
                chunk = self.dev.recv(8192)
            except socket.timeout:
                return b""
            except OSError as e:
                raise DriverError(f"{self.port}: {e}") from None
            if not chunk:
                raise DriverError(E_CLOSED)
            return chunk
        time.sleep(wait)
        return self.dev.read(self.dev.in_waiting or 0)


def _params(conn) -> dict:
    p = conn.params or {}
    return {"max_age_s": max(float(p.get("max_age_s") or 30), 1.0)}


class P1Driver(Driver):
    kind = "dsmr_p1"

    def __init__(self, conn, tags, sink, data_dir="data"):
        super().__init__(conn, tags, sink, data_dir)
        self.line = Line(conn)
        self.max_age = _params(conn)["max_age_s"]
        self.buf = b""
        self.values: dict = {}
        self.last_rx = 0.0
        self.ident = ""

    def open(self):
        self.line.open()
        self.buf, self.last_rx = b"", time.monotonic()      # give the meter max_age_s for its first telegram

    def close(self):
        self.line.close()

    def poll(self) -> dict:
        self.buf += self.line.read(min(0.2, self.conn.poll_ms / 1000))
        good, bad, self.buf = extract(self.buf)
        self.stats["errors"] += len(bad)                    # broken telegrams are only counted, the next one comes soon
        if good:
            self.ident, data = parse(good[-1])
            self.values = {t.name: convert(data.get(t.address.strip()), t.type) for t in self.tags}
            self.last_rx = time.monotonic()
        if time.monotonic() - self.last_rx > self.max_age:
            raise DriverError(E_NO_DATA.format(round(self.max_age)))
        return dict(self.values)

    def write(self, tag, raw) -> None:
        raise DriverError(E_READ_ONLY)


def validate(conn, project=None) -> list[tuple[str, str]]:
    return [] if (conn.serial_port or "").strip() else [("serial_port", E_PORT)]


def test_once(conn, ctx) -> dict:
    """*Test connection*: wait for one valid telegram (at most max_age_s)."""
    line, buf = Line(conn), b""
    line.open()
    try:
        deadline = time.monotonic() + _params(conn)["max_age_s"]
        while time.monotonic() < deadline:
            buf += line.read(0.2)
            good, _bad, buf = extract(buf)
            if good:
                ident, data = parse(good[-1])
                return {"msg": M_TEST_OK.format(line.port, ident, len(data))}
    finally:
        line.close()
    raise DriverError(E_NO_DATA.format(round(_params(conn)["max_age_s"])))


SPECS = [DriverSpec(
    kind="dsmr_p1", label="Elektroměr s portem P1 / DSMR (příklad)", short="P1 DSMR", category="meter", order=900,
    transport="serial", id_prefix="p1", make=lambda conn, tags, sink, data_dir: P1Driver(conn, tags, sink, data_dir),
    check_address=check_address, test=test_once, validate=validate, summary="{serial_port|?} {baudrate|115200}",
    fields=(
        FieldSpec("serial_port", "COM port (nebo socket://adresa:port převodníku P1)", "serial_port", span=3),
        FieldSpec("baudrate", "Rychlost [Bd]", "select", default=115200,
                  options=(("115200", "115 200 (DSMR 4 a 5)"), ("9600", "9 600 (DSMR 2.2 a 3)"))),
        FieldSpec("bytesize", "Datové bity", "select", default="8", options=(("8", "8 (DSMR 4 a 5)"), ("7", "7 (DSMR 2.2 a 3)"))),
        FieldSpec("parity", "Parita", "select", default="N", options=(("N", "N – žádná"), ("E", "E – sudá"))),
        FieldSpec("max_age_s", "Max. stáří telegramu [s]", "number", default=30, min=2, max=3600,
                  help="Bez platného telegramu po tuto dobu = chyba spojení (elektroměr posílá každou 1 s nebo 10 s)"),
    ),
    addr_help="Kód OBIS: 1-0:1.8.1 energie odebraná T1 · 1-0:1.7.0 příkon · 1-0:32.7.0 napětí L1 · 0-1:24.2.1 plyn",
    addr_placeholder="1-0:1.7.0", defaults={"baudrate": 115200, "parity": "N"},
)]
