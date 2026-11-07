"""NTP – a binary request/response protocol over UDP: watch a time server and the clock of the BAVIS computer.

Correct time matters in SCADA: alarm and event time stamps, the audit trail and trend data are only as good as the clock.
This driver asks an NTP server (a PLC, a GPS clock, the plant time server, a public server) for the time and reports how far the
local clock is off. It does not set the clock – that is the job of the operating system. Reference: RFC 5905 *Network Time
Protocol Version 4* – packet format (section 7.3), on-wire calculation of offset and delay (section 8), kiss codes (7.4).

Tag addresses:

    offset_ms           offset of the server clock against the local clock – positive = the local clock is behind
    delay_ms            round-trip delay
    stratum             1 = server with a reference clock (GPS, DCF77), 2–15 = synchronised over the network
    leap                leap indicator 0–3 (3 = server not synchronised)
    synced              bool: the server is synchronised (leap ≠ 3 and stratum 1–15)
    root_delay_ms       delay to the reference clock of the server
    root_dispersion_ms  error estimate of the server
    refid               reference of the server (type ``string``): GPS, DCF, PPS … or the IP address of its own server
    server_time         time of the server in seconds since 1970 (type ``float64``)

What the example shows:
- a binary protocol with ``struct`` (fixed 48-byte packets, 64-bit fixed-point time stamps),
- UDP without a connection: every query is checked (version, mode, origin time stamp) so stray datagrams are ignored,
- a query interval independent of the read cycle (``min_interval_s``, at least 16 s – public servers block clients that ask
  too often); between queries ``poll()`` returns the last result,
- a protocol answer that must stop the queries (kiss-o'-death ``RATE`` / ``DENY``) turned into an operator message."""
from __future__ import annotations

import socket
import struct
import time

from bavis.sdk import Driver, DriverError, DriverSpec, FieldSpec, require_host

DEFAULT_PORT = 123
NTP_EPOCH = 2208988800                   # seconds from 1900-01-01 (NTP era 0) to 1970-01-01 (Unix)
PACKET = struct.Struct(">BBbbII4sQQQQ")  # RFC 5905 fig. 8, without extension fields and MAC
MIN_INTERVAL_S = 16.0
NUMBERS = ("offset_ms", "delay_ms", "stratum", "leap", "root_delay_ms", "root_dispersion_ms", "server_time")
ADDRESSES = NUMBERS + ("synced", "refid")

# operator texts = translation keys (section "srv" of i18n/<lang>.json); placeholders {0}, {1} are filled by .format()
E_ADDR = "adresa = offset_ms, delay_ms, stratum, leap, synced, root_delay_ms, root_dispersion_ms, refid nebo server_time"
E_TEXT = "refid je text – tag musí mít typ string"
E_NO_ANSWER = "server {0} neodpověděl"
E_KISS = "server odmítá dotazy ({0}) – prodlužte interval nebo použijte jiný server"
E_NOT_SERVER = "odpověď není od NTP serveru"
M_TEST_OK = "{0}: stratum {1}, posun {2} ms, zpoždění {3} ms"


def check_address(address: str, typ: str) -> str | None:
    address = (address or "").strip().lower()
    if address not in ADDRESSES:
        return E_ADDR
    if address == "refid" and typ != "string":
        return E_TEXT
    return None


def to_ntp(t: float) -> int:
    """Unix time → 64-bit NTP time stamp (32 bits of seconds, 32 bits of fraction)."""
    return int((t + NTP_EPOCH) * 2 ** 32) & 0xFFFFFFFFFFFFFFFF


def from_ntp(ts: int) -> float:
    return ts / 2 ** 32 - NTP_EPOCH


def short(v: int) -> float:
    """32-bit NTP short format (16.16 seconds) → milliseconds."""
    return v / 2 ** 16 * 1000


def request(t1: float) -> tuple[bytes, int]:
    """Client packet: leap 0, version 4, mode 3 (client), transmit time stamp = t1 → (packet, transmit time stamp)."""
    tx = to_ntp(t1)
    return PACKET.pack(0 << 6 | 4 << 3 | 3, 0, 0, 0, 0, 0, b"\0\0\0\0", 0, 0, 0, tx), tx


def refid_text(stratum: int, refid: bytes) -> str:
    if stratum <= 1:
        return refid.rstrip(b"\0").decode("ascii", "replace")
    return socket.inet_ntoa(refid)                           # IPv4 server: its address (IPv6: a hash, shown the same way)


def evaluate(answer: bytes, tx: int, t1: float, t4: float) -> dict | None:
    """Server answer → values of all addresses; None for a datagram that is not the answer to our query."""
    if len(answer) < PACKET.size:
        return None
    li_vn_mode, stratum, _poll, _prec, root_delay, root_disp, refid, _ref, origin, rx, txs = PACKET.unpack_from(answer)
    if li_vn_mode & 0x07 != 4 or origin != tx:               # mode 4 = server; origin must echo our transmit time stamp
        return None
    if stratum == 0:                                         # kiss-o'-death: the code is in refid (RATE, DENY, RSTR …)
        raise DriverError(E_KISS.format(refid.rstrip(b"\0").decode("ascii", "replace")))
    t2, t3 = from_ntp(rx), from_ntp(txs)
    leap = li_vn_mode >> 6
    return {
        "offset_ms": ((t2 - t1) + (t3 - t4)) / 2 * 1000,
        "delay_ms": max(0.0, (t4 - t1) - (t3 - t2)) * 1000,
        "stratum": stratum, "leap": leap, "synced": leap != 3 and 1 <= stratum <= 15,
        "root_delay_ms": short(root_delay), "root_dispersion_ms": short(root_disp),
        "refid": refid_text(stratum, refid), "server_time": t3,
    }


def query(host: str, port: int, timeout: float) -> dict:
    """One NTP query. Stray or late datagrams are skipped until the timeout."""
    try:
        addr = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM)[0][4]
    except OSError as e:
        raise DriverError(f"{host}: {e}") from None
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        deadline = time.monotonic() + timeout
        t1 = time.time()
        packet, tx = request(t1)
        try:
            s.sendto(packet, addr)
            while True:
                s.settimeout(max(deadline - time.monotonic(), 0.001))
                data, sender = s.recvfrom(1024)
                t4 = time.time()
                if sender[0] == addr[0]:
                    values = evaluate(data, tx, t1, t4)
                    if values is not None:
                        return values
        except socket.timeout:
            raise DriverError(E_NO_ANSWER.format(host)) from None
        except OSError as e:
            raise DriverError(f"{host}: {e}") from None


class NtpDriver(Driver):
    kind = "ntp"

    def __init__(self, conn, tags, sink, data_dir="data"):
        super().__init__(conn, tags, sink, data_dir)
        interval = float((conn.params or {}).get("min_interval_s") or 64)
        self.interval = max(interval, MIN_INTERVAL_S)
        self.last: dict | None = None
        self.last_t = 0.0
        self.queries = 0

    def open(self):
        self.last = None                     # after an error ask again (still at most once per interval – see poll)

    def close(self):
        pass

    def poll(self) -> dict:
        now = time.monotonic()
        if self.last is None or now - self.last_t >= self.interval:
            if self.queries and now - self.last_t < self.interval:      # reconnect after an error: wait for the interval
                raise DriverError(E_NO_ANSWER.format(self.conn.host))
            self.last_t = now
            self.queries += 1
            self.last = query(self.conn.host, self.conn.port or DEFAULT_PORT, max(self.conn.timeout_ms, 100) / 1000)
        return {t.name: self.last.get(t.address.strip().lower()) for t in self.tags}


def test_once(conn, ctx) -> dict:
    v = query(conn.host, conn.port or DEFAULT_PORT, max(conn.timeout_ms, 1000) / 1000)
    return {"msg": M_TEST_OK.format(conn.host, v["stratum"], round(v["offset_ms"], 1), round(v["delay_ms"], 1))}


SPECS = [DriverSpec(
    kind="ntp", label="NTP časový server (příklad)", short="NTP", category="it", order=900, transport="udp",
    default_port=DEFAULT_PORT, id_prefix="ntp", make=lambda conn, tags, sink, data_dir: NtpDriver(conn, tags, sink, data_dir),
    check_address=check_address, test=test_once, validate=require_host, summary="{host}:{port}",
    fields=(FieldSpec("min_interval_s", "Interval dotazů [s]", "number", default=64, min=16, max=86400,
                      help="Jak často se ptát serveru, nezávisle na periodě čtení; veřejné servery: aspoň 64 s"),),
    addr_help="offset_ms (posun hodin) · delay_ms · stratum · leap · synced (bool) · root_delay_ms · root_dispersion_ms · "
              "refid (text) · server_time",
    addr_placeholder="offset_ms", defaults={"host": "192.168.0.1", "port": DEFAULT_PORT, "poll_ms": 10000},
)]
