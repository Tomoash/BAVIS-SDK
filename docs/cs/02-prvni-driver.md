# 2. První driver krok za krokem

[Obsah návodů](README.md) · předchozí: [Začínáme](01-zaciname.md) · další: [Vzory driverů](03-vzory.md)

Tento návod prochází kostru z `bavis-sdk new` a ukazuje, co v ní změnit pro skutečné zařízení. Jako příklad bereme váhu, která
na TCP portu odpovídá na textové dotazy. Úplné hotové drivery jsou v [examples](../../examples/README.md).

## Jak driver v BAVIS žije

1. Uživatel v **Konfigurace → Spojení** založí spojení vašeho druhu a vyplní formulář (IP adresa, port a vaše vlastní pole).
2. V tabulce tagů zadá u každého tagu **adresu** ve vašem formátu (`R10`, `MEAS:VOLT?`, `boiler.flow.temp` …). Adresu kontroluje
   vaše funkce `check_address` – hned v tabulce i při ukládání projektu.
3. Po aktivaci projektu engine zavolá `make(conn, tags, sink, data_dir)` → instance vašeho driveru, a `start()`.
4. Základní třída `Driver` spustí vlastní vlákno: `open()`, pak cyklicky `poll()` s periodou `conn.poll_ms`. Výjimka v `open()`
   nebo `poll()` = spojení odpojeno (stav, počítadlo chyb, tagy bez hodnoty), za 2 s nový pokus.
5. Zápis z obrazovky, logiky nebo API volá `write(tag, raw)` – **z jiného vlákna** než `poll()`.

`poll()` vrací **surové** hodnoty `{název tagu: hodnota | None}`. Měřítko, desetinná místa, pásmo necitlivosti, historii a alarmy
dělá engine. `None` znamená neplatnou hodnotu.

## Krok 1: kostra

```
bavis-sdk new moje_vaha --label "Moje váha" --dir C:\vyvoj\vaha
```

Otevřete `bavis_drv_moje_vaha/drivers/moje_vaha.py`. Soubor má čtyři části: texty, kontrolu adresy, třídu driveru a popis
`SPECS`. Projdeme je odspodu, protože popis určuje, co uživatel uvidí.

## Krok 2: popis driveru (`DriverSpec`)

```python
SPECS = [DriverSpec(
    kind="moje_vaha",                 # druh = název balíčku za bavis_drv_; jedinečný v celé instalaci
    label="Moje váha",                # název v seznamu driverů (česky = zdrojový jazyk, překlady v i18n)
    category="it", order=900,         # skupina v nabídce (plc, building, energy, meter, maker, it) a pořadí
    transport="tcp",                  # tcp | udp | serial | url | none – jaká pole spojení formulář ukáže
    default_port=4001,
    id_prefix="vaha",                 # předpona ID nových spojení (vaha1, vaha2 …)
    make=_make,                       # (conn, tags, sink, data_dir) → instance driveru
    check_address=check_address,      # (adresa, typ) → None | text chyby
    test=test_once,                   # tlačítko Test spojení (nepovinné)
    validate=require_host,            # pravidla spojení (zde: IP adresa je povinná)
    summary="{host}:{port} stanice {station}",     # popis spojení v přehledu
    fields=(FieldSpec("station", "Stanice", "number", default=1, min=1, max=247,
                      help="Číslo stanice v dotazech"),),
    addr_help="W<číslo> – kanál hmotnosti, např. W1",
    addr_placeholder="W1",
    defaults={"host": "192.168.0.1"},
)]
```

Nejdůležitější pole:

| Pole | K čemu |
| --- | --- |
| `fields` | vlastní pole formuláře spojení. Hodnoty se ukládají do `conn.params` (`conn.params["station"]`). Typy `text`, `number`, `bool`, `select` (`options=(("hodnota", "popisek"), …)`), `password` (s `secret=True` se maskuje v API, exportech a zálohách), `serial_port`, `file`, `list`. Pole jde podmínit jiným polem: `show_if={"mode": ("tcp",)}`. |
| `validate` | `validate(conn, project=None) → [(pole, text), …]`. Pole je `host`, `port`, … nebo `params.<klíč>`. Prázdný seznam = v pořádku. |
| `test` | `test(conn, ctx) → {"msg": "…"}`; výjimka = test selhal a uživatel uvidí její text. `ctx.data_dir`, `ctx.simulate`. |
| `browse` + `items_to_tags` | import tagů procházením zařízení – seznam proměnných a vytvoření tagů z vybraných (viz [Vzory](03-vzory.md#procházení-proměnných)). |
| `license` | nechte výchozí `"comm"`: spojení potřebuje licenci komunikace jako drivery jádra. |

Úplný seznam je v referenci [drivers.md](../drivers.md#4-the-api).

## Krok 3: adresa tagu

Vymyslete adresu tak, aby ji uživatel přepsal z dokumentace zařízení. Kontrola má být přísná – co projde `check_address`, musí
umět `poll()`.

```python
ADDR_RE = re.compile(r"^W(\d{1,2})$")
E_ADRESA = "adresa W<číslo>, např. W1 (W1–W16)"


def check_address(address: str, typ: str) -> str | None:
    m = ADDR_RE.match((address or "").strip().upper())
    if not m or not 1 <= int(m.group(1)) <= 16:
        return E_ADRESA
    return None
```

`typ` je typ tagu (`bool`, `int8`, `uint8`, `int16`, `uint16`, `int32`, `uint32`, `int64`, `float32`, `float64`, `string`). Pokud zařízení některý typ
neumí, vraťte chybu i pro něj.

## Krok 4: třída driveru

```python
class VahaDriver(Driver):
    kind = "moje_vaha"

    def __init__(self, conn, tags, sink, data_dir="data"):
        super().__init__(conn, tags, sink, data_dir)
        self.station = int((conn.params or {}).get("station", 1))
        self.link = Link(conn.host, conn.port or 4001, conn.timeout_ms / 1000)

    def open(self):
        self.link.connect()                    # chyba → DriverError, engine to zkusí za 2 s znovu

    def close(self):
        self.link.close()

    def poll(self) -> dict:
        out = {}
        for t in self.tags:
            ok, text = self.link.ask(f"{self.station} GET {t.address.strip().upper()}")
            out[t.name] = float(text) if ok else None
        return out

    def write(self, tag, raw) -> None:
        ok, text = self.link.ask(f"{self.station} SET {tag.address} {raw}")
        if not ok:
            raise DriverError(E_ZAPIS.format(tag.address, text))
        self.stats["writes"] += 1
```

Co máte k dispozici: `self.conn` (`host`, `port`, `poll_ms`, `timeout_ms`, `params`), `self.tags` a `self.by_name` (tagy
spojení: `name`, `address`, `type`, `access`), `self.stats`, `self.last_error`, `self.connected`. Metodu `status()` můžete
rozšířit o vlastní údaje – zobrazí se v **Objekty → Komunikace**.

Pravidla, která se vyplatí dodržet od začátku:

* **Jedno spojení se zařízením sdílí `poll()` a `write()`** – chraňte ho zámkem (`threading.Lock`). Kostra to dělá ve třídě `Link`.
* **Chyba spojení = výjimka** (`DriverError` s textem pro obsluhu). Chyba jednoho tagu (zařízení adresu nezná) = `None` jen pro
  ten tag a případně `self.last_error`.
* **Knihovny zařízení importujte uvnitř funkcí**, ne nahoře v modulu. Jádro při startu importuje všechny moduly driverů.
* **Zápis jen tam, kde dává smysl**: odmítněte zápis do tagu jen pro čtení, u nebezpečných zařízení nechte zápis vypnutý, dokud ho
  uživatel nepovolí (viz [příklad SCPI](../../examples/scpi)), a nikdy nezapisujte cyklicky do flash/EEPROM.

## Krok 5: texty a překlady

Zdrojový jazyk BAVIS je čeština: popisky, nápovědy a hlášky pište česky a překlady dejte do
`bavis_drv_<název>/i18n/<jazyk>.json`:

```json
{
 "srv": {
  "Moje váha": "My scale",
  "adresa W<číslo>, např. W1 (W1–W16)": "address W<number>, e.g. W1 (W1–W16)",
  "zápis {0} odmítnut: {1}": "write {0} refused: {1}"
 }
}
```

* Klíč = přesně český text ze zdroje. Hlášky se zástupnými znaky (`{0}`, `{1}`) držte jako konstanty a doplňujte je až
  `.format()` – jádro přeloží šablonu i dosazené hodnoty.
* `check` hlásí chybějící soubory `en`, `de`, `sk`, `pl` a texty v `en.json`, které jsou stejné jako zdroj (nepřeložené).
* Když česky neumíte, napište texty anglicky a v pull requestu to uveďte – překlad doplníme.

## Krok 6: náhradní zařízení a testy

Upravte `tests/test_moje_vaha.py` tak, aby náhradní zařízení mluvilo stejným protokolem jako skutečné. Testy musí běžet bez
hardwaru a na portech, které vybere systém. Podrobně v návodu [Testování](04-testovani.md).

```
bavis-sdk test C:\vyvoj\vaha                   # všechny testy
bavis-sdk test C:\vyvoj\vaha -- -k zapis -x    # parametry pytest za --
```

## Krok 7: kontrola a sestavení

```
bavis-sdk check --strict C:\vyvoj\vaha
bavis-sdk build C:\vyvoj\vaha
```

Pokračujte návodem [Sestavení a instalace](05-sestaveni-a-instalace.md).
