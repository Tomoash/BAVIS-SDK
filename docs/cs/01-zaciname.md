# 1. Začínáme

[Obsah návodů](README.md) · další: [První driver krok za krokem](02-prvni-driver.md)

## Co je BAVIS SDK

BAVIS je webová SCADA / HMI. Jádro je uzavřené, ale komunikační drivery jde psát mimo něj: driver je malý balíček v Pythonu
(`bavis_drv_<název>`), který se sestaví do souboru `.bavispkg` a nainstaluje v **Systém → Projekty a balíčky**. Žádná nová verze
BAVIS k tomu není potřeba.

**BAVIS SDK** je stabilní veřejné API pro takové drivery (`bavis.sdk`, verze API **1.0**) a sada nástrojů kolem nich:

* kostra nového driveru s náhradním zařízením a testy,
* kontrola balíčku (co by jádro odmítlo),
* spuštění testů proti nainstalovanému jádru,
* sestavení `.bavispkg`.

Balíček, který importuje BAVIS **jen přes `bavis.sdk`**, je *balíček SDK*: načte ho každé jádro, které podporuje SDK API 1.x,
i po další hlavní verzi BAVIS (3.x → 4.x). Balíček, který sahá do vnitřku jádra (`bavis.core…`), je svázaný s jednou hlavní
verzí a po ní se přestane načítat.

## Co SDK zatím neumí

SDK 1.0 je jen pro **komunikační drivery**. Symboly, typová zařízení, obrazovky, šablony reportů a další části projektu se
sdílejí jako *díly* katalogu (export části projektu v Konfiguraci, bez programování). Servery (BAVIS publikuje data jinam) a vlastní
prvky obrazovek SDK zatím nepodporuje.

## Co potřebujete

| Co | Proč |
| --- | --- |
| Nainstalovaný BAVIS **4.0 nebo novější** (Windows, Linux nebo obraz Docker) | obsahuje příkaz `bavis sdk`, jádro a pytest. Stačí bezplatná edice. |
| Editor (VS Code, PyCharm …) | psaní kódu |
| Dokumentaci protokolu zařízení | mapa registrů, příkazy, formát odpovědí |

Python zvlášť instalovat nemusíte: `bavis sdk` používá Python, který je součástí instalace BAVIS.

> **BAVIS 3.1:** balíčky SDK 1.0 už načítá, příkaz `bavis sdk` (kostra, kontrola, testy) ale přichází až s verzí 4.0.
> Aktualizace přes soubor `.whu` ze starší verze příkaz ani pytest nepřidá – je potřeba plná instalace 4.0.

Kde příkaz najdete:

| Instalace | Příkaz |
| --- | --- |
| Windows | `C:\BAVIS\bavis-sdk.cmd` (složka instalace, výchozí `C:\BAVIS`) |
| Linux | `/opt/bavis/bavis-sdk` (jako uživatel služby nebo root – složka jádra není čitelná pro ostatní) |
| Docker | `docker run --rm -v "$PWD:/work" -w /work --user "$(id -u):$(id -g)" <obraz> sdk …` |

V návodech dál píšeme zkráceně `bavis-sdk`.

## První balíček za pět minut

```
bavis-sdk info                                         # verze jádra, SDK API, Python, pytest
bavis-sdk new moje_vaha --label "Moje váha" --dir C:\vyvoj\vaha
bavis-sdk test C:\vyvoj\vaha                           # 5 testů proti náhradnímu zařízení
bavis-sdk check C:\vyvoj\vaha                          # co by sestavení nebo jádro odmítlo
bavis-sdk build C:\vyvoj\vaha                          # C:\vyvoj\vaha\dist\drv_moje_vaha-1.0.0.bavispkg
```

`new` vytvoří *pracovní složku* (workspace):

```
C:\vyvoj\vaha\
  bavis_drv_moje_vaha\
    __init__.py            NAME = "Moje váha", __version__ = "1.0.0"
    drivers\__init__.py
    drivers\moje_vaha.py   driver + popis DriverSpec (SPECS)
    i18n\en.json …         překlady textů pro obsluhu (en, de, sk, pl)
  tests\
    conftest.py            přidá pracovní složku na sys.path
    test_moje_vaha.py      testy proti náhradnímu zařízení (TCP server na 127.0.0.1)
```

Kostra je funkční driver jednoduchého řádkového protokolu (`1 GET R10` → `OK 12.5`). Nahraďte ho protokolem svého zařízení
a náhradní zařízení v testech upravujte stejně – postup je v [dalším návodu](02-prvni-driver.md).

Název `<název>` odpovídá `^[a-z][a-z0-9_]{1,30}$` a je zároveň druhem driveru (`DriverSpec.kind`). Nesmí se shodovat
s driverem jádra (`modbus_tcp`, `s7`, `mqtt`, `rest` …) ani jiného balíčku – sestavení takový balíček odmítne.

## Jak `check` hlásí problémy

* **Chyba** (sestavení se zastaví): špatný název složky nebo souboru, modul, který nejde importovat, neplatný `DriverSpec`, druh,
  který už jádro má, chybějící nebo špatná `__version__` (`MAJOR.MINOR.PATCH`), rozbitý `i18n/<jazyk>.json`.
* **Varování**: import BAVIS mimo `bavis.sdk` (balíček nebude balíček SDK), knihovna zařízení importovaná na úrovni modulu,
  chybějící nebo nepřeložené texty, chybějící testy, pevné porty v testech.

`bavis-sdk check --strict` bere varování jako chyby – použijte ho v CI.

## Kam dál

* [První driver krok za krokem](02-prvni-driver.md)
* Hotové příklady: [examples](../../examples/README.md)
* Reference API (anglicky): [drivers.md](../drivers.md)
