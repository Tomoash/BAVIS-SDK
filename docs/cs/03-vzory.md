# 3. Vzory driverů

[Obsah návodů](README.md) · předchozí: [První driver](02-prvni-driver.md) · další: [Testování](04-testovani.md)

Zařízení se liší hlavně tím, **kdo začíná komunikaci** a **kolik dat přijde najednou**. Každý vzor níže má hotový příklad
v [examples](../../examples/README.md).

## Dotaz a odpověď – jeden dotaz na cyklus

Zařízení vrátí všechna data jednou odpovědí (webové API, JSON, XML). `poll()` udělá jeden dotaz a hodnoty tagů vybere z odpovědi.

```python
def poll(self) -> dict:
    doc = fetch(self.conn)                                  # jeden HTTP dotaz
    return {t.name: convert(resolve(doc, t.address), t.type) for t in self.tags}
```

Příklad: [`http_json`](../../examples/http_json).

## Dotaz a odpověď – dotaz na každý tag

Textové protokoly přístrojů (SCPI, ASCII protokoly vah a regulátorů): jeden řádek tam, jeden zpět. Spojení držte otevřené mezi
cykly, čtení odpovědi omezte timeoutem spojení (`conn.timeout_ms`) a při chybě spojení zavřete – engine ho otevře znovu.

Příklad: [`scpi`](../../examples/scpi) – sdílená linka se zámkem, zápis kontrolovaný dotazem `SYST:ERR?`.

## Blokové čtení registrů

U protokolů s registry (Modbus-like, paměťové oblasti PLC) je jeden dotaz na blok mnohem rychlejší než dotaz na každý tag.
`merge_ranges` spojí blízké adresy do bloků:

```python
from bavis.sdk import merge_ranges

def poll(self) -> dict:
    out = {}
    items = [(register(t.address), words(t.type), t) for t in self.tags]       # (začátek, velikost, cokoli)
    for start, count, block_tags in merge_ranges(items, max_gap=8, max_len=120):
        regs = self.link.read_registers(start, count)                          # jeden dotaz na blok
        for t in block_tags:
            out[t.name] = decode(regs, register(t.address) - start, t.type)
    return out
```

`max_gap` = kolik nepoužitých registrů smí být mezi tagy v jednom bloku, `max_len` = největší blok, který zařízení přečte
jedním dotazem (najdete v dokumentaci protokolu).

Tagy mohou mít vlastní periodu čtení (`Tag.poll_ms`). `self.every(tag)` vrátí, každý kolikátý cyklus spojení se má tag číst,
a `self.due(every)`, zda je to v tomto cyklu – tak jde pomalé tagy číst méně často.

## Zařízení, která posílají data sama

Senzory s ESP32, UDP telegramy, některé elektroměry: zařízení posílá, BAVIS poslouchá. Stačí běžné `open` / `close` / `poll`:

* `open()` otevře naslouchací socket,
* `poll()` chvíli čeká na zprávy a vrátí **jen tagy, které přišly** – ostatní hodnoty engine ponechá,
* hodnota, která dlouho nepřišla, se vrátí jako `None`; když nepřijde nic, `poll()` vyhodí `DriverError` a spojení se ukáže
  jako odpojené, dokud data nepřijdou znovu.

```python
def poll(self) -> dict:
    out, until = {}, time.monotonic() + min(1.0, self.conn.poll_ms / 1000)
    while time.monotonic() < until:
        try:
            data, _addr = self.sock.recvfrom(8192)
        except socket.timeout:
            continue
        ...                                         # rozebrat zprávu, out[tag] = hodnota
    if time.monotonic() - self.last_rx > self.max_age:
        raise DriverError(E_NO_DATA.format(...))
    return out
```

Příklad: [`udp_json`](../../examples/udp_json) – směrování podle zařízení, filtr odesílatele, stáří hodnot.

Naslouchající port přijme data od kohokoli v síti. Nabídněte filtr odesílatele a v nápovědě napište, že port patří jen do
důvěryhodné sítě.

## Bez sítě: soubory a místní zdroje

`transport="none"` skryje IP adresu a port. Relativní cesty skládejte se složkou dat BAVIS (`data_dir` z `make`, `ctx.data_dir`
v `test` a `browse`) a povolte jen přípony, které opravdu čtete. Mezi cykly si pamatujte čas změny souboru a čtěte ho jen tehdy,
když se změnil.

Příklad: [`csv_file`](../../examples/csv_file).

## Procházení proměnných

Když zařízení umí vypsat své proměnné, přidejte do popisu `browse` a `items_to_tags`. Uživatel pak v editoru tagů otevře
**Import tagů**, zvolí záložku procházení zařízení a spojení, klikne **Připojit a načíst proměnné**, vybere proměnné a tagy vzniknou
samy.

```python
def browse(conn, ctx, node_id=None) -> dict:
    return {"flat": True, "items": [
        {"name": "temp_in", "address": "temp_in", "type": "float32", "datatype": "CSV", "writable": False,
         "comment": "temp_in = 21,5"},
    ]}


def items_to_tags(items, conn_id, prefix, group, opts=None) -> dict:
    tags = [{"name": prefix + it["name"], "conn": conn_id, "address": it["address"], "type": it.get("type") or "float32",
             "access": "rw" if it.get("writable") else "r", "group": group, "desc": it.get("comment", "")} for it in items]
    return {"tags": tags, "skipped": [], "info": "můj driver"}
```

Položka seznamu: `name` a `comment` se zobrazí, `datatype` je typ v zařízení, `type` typ tagu (položku bez něj nejde vybrat),
`writable` = zápis možný. Vybrané položky dostane `items_to_tags` a vrátí definice tagů.

Názvy tagů musí odpovídat `^[A-Za-z_][A-Za-z0-9_.\-\[\]]{0,99}$` a být v importu jedinečné – příklad `csv_file` ukazuje
převod a číslování duplicit. Když rozhraní používá běžící spojení s jiným nastavením, vyhoďte `Conflict` (uživatel dostane
srozumitelnou hlášku místo chyby).

## Zápis bez překvapení

* Zápis do tagu s `access="r"` odmítněte.
* U zařízení, kde špatná hodnota může něco poškodit, nechte zápis vypnutý polem spojení (`FieldSpec("allow_writes", …, "bool",
  default=False)`), dokud ho uživatel vědomě nepovolí.
* Po zápisu ověřte, že ho zařízení přijalo (chybová fronta, potvrzení, zpětné čtení), a jinak vyhoďte `DriverError` – uživatel
  uvidí chybu u ovládacího prvku.
* Nikdy nezapisujte cyklicky do registrů ve flash nebo EEPROM (životnost paměti).

## Hesla a tokeny

Heslo, API klíč nebo token patří do pole `FieldSpec("token", "Token", "password", secret=True)`. BAVIS ho pak maskuje v API,
exportech CSV, porovnání revizí i zálohách. Nikdy ho nepište do kódu, logu ani do textu chyby.

## Simulace

`DriverSpec.sim="local"` (výchozí) znamená, že v režimu simulace se spojení smí připojit jen na `127.0.0.1` – tedy na váš
simulátor, ne na skutečné zařízení. Uživatel může u spojení zapnout i **Simulovat** a tagy pak běží virtuálně bez driveru.

## Stav a diagnostika

`status()` vrací slovník, který BAVIS ukazuje v **Objekty → Komunikace**. Přidejte vlastní počítadla:

```python
def status(self) -> dict:
    return {**super().status(), "counters": dict(self.link.counters)}
```
