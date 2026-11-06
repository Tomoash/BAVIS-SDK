"""CSV file – a driver without a network: read the newest row of a CSV file that another program keeps appending to.

The file has a header row with column names; every new measurement is a new row at the end:

    time;temp_in;temp_out;state
    2026-11-06 10:00:00;21,5;8,2;RUN
    2026-11-06 10:01:00;21,6;8,1;RUN

Tag address = column name (``temp_in``). Every read cycle looks at the time of the last change of the file and reads only the
end of it when it changed, so even a large log file costs almost nothing.

What the example shows:
- ``transport="none"`` (no host or port), a relative path resolved in the data folder of BAVIS (``data_dir``),
- ``browse`` + ``items_to_tags`` – tag import by browsing lists the columns of the file and creates tags from the selected ones,
- ``select`` fields (separator, decimal mark) and a file that is older than *Max. age* reported as an error,
- caching between cycles and a ``test`` function that reports what the file contains.

Security: the driver reads only files with the extension .csv or .txt. Anybody who can edit the project can choose the path, so
keep the BAVIS data folder for files like this and do not point it at system files."""
from __future__ import annotations

import os
import re
import time

from bavis.sdk import Driver, DriverError, DriverSpec, FieldSpec

TAIL_BYTES = 64 * 1024
COLUMN_RE = re.compile(r"^[^;,\t\r\n]{1,100}$")
SEPARATORS = {"semicolon": ";", "comma": ",", "tab": "\t"}

E_ADDR = "adresa = název sloupce z prvního řádku souboru"
E_PATH = "zadejte cestu k souboru .csv nebo .txt"
E_EXT = "číst jde jen soubory .csv nebo .txt"
E_MISSING = "soubor {0} neexistuje"
E_EMPTY = "soubor {0} nemá řádek s daty"
E_OLD = "soubor {0} se nezměnil {1} s"
E_COLUMNS = "soubor {0} nemá sloupce: {1}"
M_TEST_OK = "{0}: {1} sloupců, poslední řádek {2}"


def check_address(address: str, typ: str) -> str | None:
    return None if COLUMN_RE.match((address or "").strip()) else E_ADDR


def _params(conn, data_dir: str) -> dict:
    p = conn.params or {}
    path = str(p.get("path") or "").strip()
    return {"path": path if not path or os.path.isabs(path) else os.path.join(data_dir, path),
            "sep": SEPARATORS.get(str(p.get("separator") or "semicolon"), ";"),
            "decimal_comma": str(p.get("decimal") or "comma") == "comma",
            "max_age_s": float(p.get("max_age_s") or 0)}


def number(text: str, decimal_comma: bool):
    text = text.strip()
    if decimal_comma:
        text = text.replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def convert(text: str, typ: str, decimal_comma: bool):
    """Cell text → raw tag value (None when it does not fit the tag type)."""
    if typ == "string":
        return text.strip()
    if typ == "bool":
        t = text.strip().lower()
        if t in ("1", "true", "on", "yes", "ano"):
            return True
        if t in ("0", "false", "off", "no", "ne"):
            return False
        return None
    return number(text, decimal_comma)


def read_file(path: str, sep: str) -> tuple[list[str], list[str]]:
    """(header, last row) of the file; reads only the first line and the last 64 kB."""
    if not path:
        raise DriverError(E_PATH)
    if not path.lower().endswith((".csv", ".txt")):
        raise DriverError(E_EXT)
    try:
        with open(path, "rb") as f:
            header = f.readline().decode("utf-8-sig", "replace").rstrip("\r\n").split(sep)
            f.seek(0, os.SEEK_END)
            start = max(f.tell() - TAIL_BYTES, 0)
            f.seek(start)
            tail = f.read().decode("utf-8", "replace").splitlines()
    except FileNotFoundError:
        raise DriverError(E_MISSING.format(path)) from None
    except OSError as e:
        raise DriverError(f"{path}: {e}") from None
    rows = [ln for ln in (tail[1:] if start else tail) if ln.strip()]   # first tail line may be cut in half
    if start == 0 and rows:
        rows = rows[1:]                                                  # the header itself
    if not rows:
        raise DriverError(E_EMPTY.format(path))
    return [h.strip() for h in header], rows[-1].split(sep)


class CsvFileDriver(Driver):
    kind = "csv_file"

    def __init__(self, conn, tags, sink, data_dir="data"):
        super().__init__(conn, tags, sink, data_dir)
        self.p = _params(conn, data_dir)
        self.mtime = None
        self.values: dict = {}

    def open(self):
        self.mtime = None                       # read the file again after (re)connecting

    def poll(self) -> dict:
        path = self.p["path"]
        try:
            mtime = os.stat(path).st_mtime
        except FileNotFoundError:
            raise DriverError(E_MISSING.format(path)) from None
        except OSError as e:
            raise DriverError(f"{path}: {e}") from None
        if self.p["max_age_s"] and time.time() - mtime > self.p["max_age_s"]:
            raise DriverError(E_OLD.format(os.path.basename(path), round(time.time() - mtime)))
        if mtime != self.mtime:                 # unchanged file → the values of the previous cycle
            header, row = read_file(path, self.p["sep"])
            cells = dict(zip(header, row))
            missing = sorted({t.address.strip() for t in self.tags} - set(header))
            if missing and len(missing) == len(self.tags):
                raise DriverError(E_COLUMNS.format(os.path.basename(path), ", ".join(missing[:5])))
            self.values = {t.name: convert(cells[t.address.strip()], t.type, self.p["decimal_comma"])
                           if t.address.strip() in cells else None for t in self.tags}
            self.mtime = mtime
        return dict(self.values)


def test_once(conn, ctx) -> dict:
    p = _params(conn, ctx.data_dir)
    header, row = read_file(p["path"], p["sep"])
    return {"msg": M_TEST_OK.format(os.path.basename(p["path"]), len(header), p["sep"].join(row)[:80])}


def browse(conn, ctx, node_id=None) -> dict:
    """Browsing (Import tags → device browsing): one item per column with the last value as a hint. ``flat`` = a list, not
    a tree. Item keys: name, address, type (tag type – items without it cannot be selected), datatype and comment (shown in the
    list), writable."""
    p = _params(conn, ctx.data_dir)
    header, row = read_file(p["path"], p["sep"])
    items = []
    for i, col in enumerate(header):
        if not col:
            continue
        cell = row[i] if i < len(row) else ""
        typ = "float32" if number(cell, p["decimal_comma"]) is not None else "string"
        items.append({"name": col, "address": col, "type": typ, "datatype": "CSV", "writable": False,
                      "comment": f"{col} = {cell.strip()[:40]}"})
    return {"items": items, "flat": True}


def tag_name(text: str) -> str:
    """Column name → valid tag name (letters, digits, _ . - [ ]; starts with a letter or _)."""
    import unicodedata
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    name = re.sub(r"[^A-Za-z0-9_.\-\[\]]", "_", ascii_text.strip().replace(" ", "_"))
    return (name if re.match(r"^[A-Za-z_]", name) else "_" + name)[:100]


def items_to_tags(items, conn_id, prefix, group, opts=None) -> dict:
    """Selected items of ``browse`` → tag definitions for the tag table (names unique within the import)."""
    tags, used = [], set()
    for it in items:
        name = base = tag_name(prefix + str(it.get("name") or it["address"]))
        k = 2
        while name in used:
            name, k = f"{base[:96]}_{k}", k + 1
        used.add(name)
        tags.append({"name": name, "conn": conn_id, "address": it["address"], "type": it.get("type") or "float32",
                     "access": "r", "group": group, "desc": it.get("comment") or it["address"]})
    return {"tags": tags, "skipped": [], "info": "CSV"}


SPECS = [DriverSpec(
    kind="csv_file", label="CSV soubor – poslední řádek (příklad)", short="CSV soubor", category="it", order=900,
    transport="none", id_prefix="csv", make=lambda conn, tags, sink, data_dir: CsvFileDriver(conn, tags, sink, data_dir),
    check_address=check_address, test=test_once, browse=browse, items_to_tags=items_to_tags, summary="{path}",
    fields=(
        FieldSpec("path", "Soubor", "text", default="", placeholder="logger/mereni.csv", span=3, required=True,
                  help="Cesta k souboru .csv nebo .txt; relativní cesta je ve složce dat BAVIS"),
        FieldSpec("separator", "Oddělovač", "select", default="semicolon",
                  options=(("semicolon", "středník ;"), ("comma", "čárka ,"), ("tab", "tabulátor"))),
        FieldSpec("decimal", "Desetinná značka", "select", default="comma",
                  options=(("comma", "čárka 21,5"), ("dot", "tečka 21.5"))),
        FieldSpec("max_age_s", "Max. stáří souboru [s]", "number", default=0, min=0, max=86400,
                  help="Soubor nezměněný déle = chyba spojení; 0 = nehlídat"),
    ),
    addr_help="Název sloupce z prvního řádku souboru, např. temp_in",
    addr_placeholder="temp_in",
)]
