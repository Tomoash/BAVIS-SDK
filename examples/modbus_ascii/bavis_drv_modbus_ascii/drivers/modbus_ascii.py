"""Modbus ASCII – a serial request/response protocol with block reads, a checksum and guarded writes.

Modbus ASCII sends every byte of a Modbus request as two hexadecimal characters: ``:`` + address + function + data + LRC +
CR LF. It is still used by older controllers, panel meters, drives and data loggers on RS-232 / RS-485. The BAVIS core speaks
Modbus TCP and Modbus RTU; this example adds the ASCII framing. References: *MODBUS over Serial Line – Specification and
Implementation Guide V1.02* (modbus.org, 2006), section 2.5.2 (ASCII mode, LRC) and *MODBUS Application Protocol
Specification V1.1b3* (modbus.org, 2012) – functions 03, 04, 06 and 16 and the exception codes.

Tag address (register number as sent in the protocol, 0–65535 – a "40001" register in a manual is usually HR0):

    HR100        holding register 100 (function 03, written with 06 / 16)
    IR5          input register 5 (function 04, read only)

Tag type ``int16`` / ``uint16`` / ``bool`` (register ≠ 0) uses one register, ``int32`` / ``uint32`` / ``float32`` two
(high word first, or low word first with *Swap words*).

What the example shows:
- ``transport="serial"``: the core's fields ``serial_port``, ``baudrate``, ``parity``, ``stopbits`` and ``unit_id`` of
  ``Connection`` plus an own field (``bytesize``) in ``params``,
- a serial library (pyserial) imported only inside a function, and ``socket://host:port`` for a serial-to-Ethernet converter in
  transparent mode – also what the tests use, so they need neither hardware nor pyserial,
- ``merge_ranges`` – neighbouring registers are read in one request,
- a checksum (LRC), protocol exceptions turned into operator messages, a lock around the shared line,
- writes disabled by default and verified by the echo of the device."""
from __future__ import annotations

import re
import socket
import struct
import threading
import time

from bavis.sdk import Driver, DriverError, DriverSpec, FieldSpec, merge_ranges

ADDR_RE = re.compile(r"^(HR|IR)(\d{1,5})$", re.I)
WORDS = {"bool": 1, "int16": 1, "uint16": 1, "int32": 2, "uint32": 2, "float32": 2}
READ_FC = {"HR": 0x03, "IR": 0x04}
MAX_REGS = 100                  # registers per request (the protocol allows 125, the ASCII frame then has 511 characters)
MAX_GAP = 10                    # read unused registers in between rather than send another request
EXCEPTIONS = {1: "nepodporovaná funkce", 2: "neplatná adresa registru", 3: "neplatná hodnota", 4: "chyba zařízení",
              6: "zařízení je zaneprázdněné"}

# operator texts = translation keys (section "srv" of i18n/<lang>.json); placeholders {0}, {1} are filled by .format()
E_ADDR = "adresa = HR<číslo> (holding registr) nebo IR<číslo> (vstupní registr), např. HR100"
E_RANGE = "číslo registru 0–65535 (u dvouregistrového typu nejvýš 65534)"
E_TYPE = "typ tagu: bool, int16, uint16, int32, uint32 nebo float32"
E_PORT = "chybí COM port (nebo socket://adresa:port převodníku)"
E_NO_ANSWER = "stanice {0} neodpověděla"
E_FRAME = "neplatná odpověď (rámec, LRC nebo stanice)"
E_EXCEPTION = "zařízení odmítlo funkci {0}: {1}"
E_WRITES_OFF = "zápis je u spojení vypnutý (pole Povolit zápis)"
E_READ_ONLY = "{0} nejde zapsat – zapisovat lze jen holding registry (HR) s přístupem rw"
E_SERIAL_LIB = "chybí knihovna pyserial pro COM port"
E_CLOSED = "převodník ukončil spojení"
M_TEST_OK = "stanice {0} odpovídá"


def parse_address(address: str, typ: str = "uint16") -> tuple[str, int, int]:
    """→ (table HR / IR, register, number of registers). Raises ValueError with an operator text for an invalid address."""
    m = ADDR_RE.match((address or "").strip())
    if not m:
        raise ValueError(E_ADDR)
    if typ not in WORDS:
        raise ValueError(E_TYPE)
    reg, size = int(m.group(2)), WORDS[typ]
    if reg + size > 65536:
        raise ValueError(E_RANGE)
    return m.group(1).upper(), reg, size


def check_address(address: str, typ: str) -> str | None:
    try:
        parse_address(address, typ)
    except ValueError as e:
        return str(e)
    return None


def lrc(data: bytes) -> int:
    """Longitudinal redundancy check: two's complement of the 8-bit sum of the bytes (spec. 2.5.2.2)."""
    return -sum(data) & 0xFF


def frame(unit: int, pdu: bytes) -> bytes:
    """Request bytes → ASCII frame ``:<HEX>\\r\\n``."""
    body = bytes([unit]) + pdu
    return b":" + (body + bytes([lrc(body)])).hex().upper().encode("ascii") + b"\r\n"


def unframe(line: bytes) -> bytes:
    """ASCII frame → address + PDU (without LRC); DriverError for a broken frame or checksum."""
    line = line.strip()
    try:
        if not line.startswith(b":") or len(line) % 2 == 0:
            raise ValueError
        raw = bytes.fromhex(line[1:].decode("ascii"))
    except ValueError:
        raise DriverError(E_FRAME) from None
    if len(raw) < 3 or lrc(raw[:-1]) != raw[-1]:
        raise DriverError(E_FRAME)
    return raw[:-1]


def decode(words: list[int], typ: str, swap: bool):
    if typ in ("bool", "int16", "uint16"):
        w = words[0]
        return bool(w) if typ == "bool" else (w - 0x10000 if typ == "int16" and w >= 0x8000 else w)
    hi, lo = (words[1], words[0]) if swap else (words[0], words[1])
    raw = struct.pack(">HH", hi, lo)
    return struct.unpack({"int32": ">i", "uint32": ">I", "float32": ">f"}[typ], raw)[0]


def encode(raw, typ: str, swap: bool) -> list[int]:
    if typ == "bool":
        return [1 if raw else 0]
    if typ in ("int16", "uint16"):
        return [int(raw) & 0xFFFF]
    data = struct.pack({"int32": ">i", "uint32": ">I", "float32": ">f"}[typ], float(raw) if typ == "float32" else int(raw))
    hi, lo = struct.unpack(">HH", data)
    return [lo, hi] if swap else [hi, lo]


class Line:
    """The serial line: a COM port through pyserial, or ``socket://host:port`` of a converter (plain TCP, no library)."""

    def __init__(self, conn):
        self.port = (conn.serial_port or "").strip()
        self.baudrate, self.parity, self.stopbits = conn.baudrate, conn.parity, conn.stopbits
        self.bytesize = int((conn.params or {}).get("bytesize") or 7)
        self.timeout = max(conn.timeout_ms, 100) / 1000
        self.dev = None
        self.buf = b""
        self.lock = threading.Lock()

    def open(self) -> None:
        if not self.port:
            raise DriverError(E_PORT)
        self.close()
        if self.port.lower().startswith("socket://"):
            host, _, port = self.port[9:].rpartition(":")
            try:
                self.dev = socket.create_connection((host, int(port)), timeout=self.timeout)
            except (OSError, ValueError) as e:
                raise DriverError(f"{self.port}: {e}") from None
            return
        try:
            import serial                      # heavy / optional library: only inside a function (SDK rule 2)
        except ImportError:
            raise DriverError(E_SERIAL_LIB) from None
        try:
            self.dev = serial.Serial(self.port, self.baudrate, bytesize=self.bytesize, parity=self.parity,
                                     stopbits=self.stopbits, timeout=self.timeout)
        except (serial.SerialException, ValueError) as e:
            raise DriverError(f"{self.port}: {e}") from None

    def close(self) -> None:
        dev, self.dev, self.buf = self.dev, None, b""
        if dev is not None:
            try:
                dev.close()
            except OSError:
                pass

    def transact(self, unit: int, pdu: bytes) -> bytes:
        """Send one request, return the PDU of the answer. Callers hold ``self.lock`` (one request on the line at a time)."""
        if self.dev is None:
            self.open()
        self.buf = b""
        try:
            if isinstance(self.dev, socket.socket):
                self.dev.sendall(frame(unit, pdu))
            else:
                self.dev.reset_input_buffer()
                self.dev.write(frame(unit, pdu))
            line = self._readline()
        except DriverError:
            self.close()
            raise
        except OSError as e:
            self.close()
            raise DriverError(str(e) or type(e).__name__) from None
        if line is None:
            self.close()
            raise DriverError(E_NO_ANSWER.format(unit))
        answer = unframe(line)
        if answer[0] != unit or answer[1] & 0x7F != pdu[0]:
            raise DriverError(E_FRAME)
        if answer[1] & 0x80:
            code = answer[2]
            raise DriverError(E_EXCEPTION.format(f"{pdu[0]:02d}", EXCEPTIONS.get(code, str(code))))
        return answer[1:]

    def _readline(self) -> bytes | None:
        deadline = time.monotonic() + self.timeout
        while b"\n" not in self.buf:
            if time.monotonic() > deadline:
                return None
            if isinstance(self.dev, socket.socket):
                try:
                    chunk = self.dev.recv(1024)
                except socket.timeout:
                    return None
                if not chunk:
                    raise DriverError(E_CLOSED)
            else:
                chunk = self.dev.read_until(b"\n")
            self.buf += chunk
        line, _, self.buf = self.buf.partition(b"\n")
        return line


def _blocks(tags) -> list[tuple[str, int, int, list]]:
    """Tags → read requests (table, first register, count, tags), neighbouring registers merged."""
    out = []
    for table in ("HR", "IR"):
        items = []
        for t in tags:
            try:
                tab, reg, size = parse_address(t.address, t.type)
            except ValueError:
                continue
            if tab == table:
                items.append((reg, size, t))
        out += [(table, start, size, lst) for start, size, lst in merge_ranges(items, MAX_GAP, MAX_REGS)]
    return out


class ModbusAsciiDriver(Driver):
    kind = "modbus_ascii"

    def __init__(self, conn, tags, sink, data_dir="data"):
        super().__init__(conn, tags, sink, data_dir)
        self.line = Line(conn)
        self.unit = conn.unit_id
        self.swap = bool(conn.word_swap)
        self.allow_writes = bool((conn.params or {}).get("allow_writes", False))
        self.blocks = _blocks(tags)

    def open(self):
        with self.line.lock:
            self.line.open()

    def close(self):
        with self.line.lock:
            self.line.close()

    def poll(self) -> dict:
        out = {}
        for table, start, count, tags in self.blocks:
            with self.line.lock:
                answer = self.line.transact(self.unit, struct.pack(">BHH", READ_FC[table], start, count))
            if len(answer) != 2 + 2 * count or answer[1] != 2 * count:
                raise DriverError(E_FRAME)
            words = list(struct.unpack(f">{count}H", answer[2:]))
            for t in tags:
                _tab, reg, size = parse_address(t.address, t.type)
                out[t.name] = decode(words[reg - start:reg - start + size], t.type, self.swap)
        return out

    def write(self, tag, raw) -> None:
        if not self.allow_writes:
            raise DriverError(E_WRITES_OFF)
        table, reg, size = parse_address(tag.address, tag.type)
        if table != "HR" or tag.access != "rw":
            raise DriverError(E_READ_ONLY.format(tag.address))
        words = encode(raw, tag.type, self.swap)
        if size == 1:
            pdu = struct.pack(">BHH", 0x06, reg, words[0])
            expect = pdu                                           # function 06 answers with an echo of the request
        else:
            pdu = struct.pack(f">BHHB{size}H", 0x10, reg, size, 2 * size, *words)
            expect = pdu[:5]                                       # function 16 answers with address and count
        with self.line.lock:
            answer = self.line.transact(self.unit, pdu)
        if answer != expect:
            raise DriverError(E_FRAME)
        self.stats["writes"] += 1


def validate(conn, project=None) -> list[tuple[str, str]]:
    return [] if (conn.serial_port or "").strip() else [("serial_port", E_PORT)]


def test_once(conn, ctx) -> dict:
    """*Test connection*: read holding register 0. An exception answer (e.g. invalid address) also proves the device answers."""
    line = Line(conn)
    with line.lock:
        try:
            line.open()
            line.transact(conn.unit_id, struct.pack(">BHH", 0x03, 0, 1))
        except DriverError as e:
            if "odmítlo" not in str(e):
                raise
        finally:
            line.close()
    return {"msg": M_TEST_OK.format(conn.unit_id)}


SPECS = [DriverSpec(
    kind="modbus_ascii", label="Modbus ASCII (sériová linka, příklad)", short="Modbus ASCII", category="plc", order=900,
    transport="serial", id_prefix="mba", make=lambda conn, tags, sink, data_dir: ModbusAsciiDriver(conn, tags, sink, data_dir),
    check_address=check_address, test=test_once, validate=validate, summary="{serial_port|?} {baudrate|9600} st. {unit_id}",
    fields=(
        FieldSpec("serial_port", "COM port (nebo socket://adresa:port převodníku)", "serial_port", span=3),
        FieldSpec("baudrate", "Rychlost [Bd]", "select", default=9600,
                  options=(("1200", "1 200"), ("2400", "2 400"), ("4800", "4 800"), ("9600", "9 600"), ("19200", "19 200"),
                           ("38400", "38 400"))),
        FieldSpec("bytesize", "Datové bity", "select", default="7", options=(("7", "7 (podle normy)"), ("8", "8"))),
        FieldSpec("parity", "Parita", "select", default="E", options=(("E", "E – sudá"), ("O", "O – lichá"), ("N", "N – žádná"))),
        FieldSpec("stopbits", "Stop bity", "select", default=1, options=(("1", "1"), ("2", "2"))),
        FieldSpec("unit_id", "Stanice", "number", default=1, min=1, max=247),
        FieldSpec("word_swap", "Prohodit slova (32 bitů)", "bool", default=False,
                  help="Zapnuto = nižší slovo první (CDAB)"),
        FieldSpec("allow_writes", "Povolit zápis", "bool", default=False,
                  help="Zápis holding registrů (HR) s přístupem rw. Vypnuto = jen čtení."),
    ),
    addr_help="HR100 holding registr (čtení 03, zápis 06/16) · IR5 vstupní registr (04, jen čtení); číslo jako v protokolu od 0",
    addr_placeholder="HR0", defaults={"baudrate": 9600, "parity": "E"},
)]
