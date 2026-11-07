# Jak přispět do BAVIS SDK

Děkujeme, že pomáháte BAVIS rozšiřovat. Tady najdete, kde se ptát, jak navrhnout driver a jak se dostane do veřejného
katalogu. English: [CONTRIBUTING.md](CONTRIBUTING.md).

## Kde se domluvit

| Chcete … | Kam |
| --- | --- |
| zeptat se, jak něco udělat, poradit se s driverem | [Discussions → Q&A](https://github.com/Tomoash/BAVIS-SDK/discussions/categories/q-a) |
| navrhnout zařízení nebo protokol, najít další, kdo ho potřebují | [Discussions → Drivers](https://github.com/Tomoash/BAVIS-SDK/discussions/categories/drivers) |
| navrhnout vylepšení SDK nebo návodů | [Discussions → Ideas](https://github.com/Tomoash/BAVIS-SDK/discussions/categories/ideas) |
| ukázat driver nebo projekt, který jste postavili | [Discussions → Show and tell](https://github.com/Tomoash/BAVIS-SDK/discussions/categories/show-and-tell) |
| nahlásit chybu v SDK, návodu nebo příkladu | issue – šablona *Bug report* |
| začít driver, který má jít do veřejného katalogu | issue – šablona *Driver or device request* |
| nahlásit bezpečnostní chybu | soukromě e-mailem – viz [SECURITY.md](SECURITY.md), nikdy veřejně |

Dotazy k vaší instalaci BAVIS nebo licenci, které se netýkají driverů, pište na
[benesl@benesl-automation.cz](mailto:benesl@benesl-automation.cz). Diskutovat můžete česky i anglicky.

## Jak můžete pomoct

- **Odpovídat na dotazy** v Discussions – nejrychlejší pomoc ostatním integrátorům.
- **Nahlásit chybu** v SDK, návodu nebo příkladu.
- **Požádat o driver** nebo dát hlas (👍) existující žádosti – nejžádanější drivery přijdou na řadu dřív.
- **Napsat driver** pro zařízení nebo protokol.
- **Vyzkoušet driver se skutečným zařízením** – drivery se testují proti náhradním zařízením, zpráva „funguje s modelem X,
  firmware Y“ má velkou cenu.
- **Vylepšit dokumentaci** včetně překladů (angličtina, čeština, němčina, slovenština, polština).

Issue se štítkem [`good first issue`](https://github.com/Tomoash/BAVIS-SDK/labels/good%20first%20issue) jsou malé a dobře
popsané, [`help wanted`](https://github.com/Tomoash/BAVIS-SDK/labels/help%20wanted) jsou žádosti, na kterých zatím nikdo nepracuje.

## Než začnete driver

1. Prohledejte Discussions a issue – možná na stejném zařízení už někdo pracuje.
2. Ověřte, že protokol nebo zařízení už neumí jádro BAVIS (Modbus TCP/RTU, S7, OPC UA, MQTT, REST, BACnet, KNX, M-Bus, SNMP, SQL
   a mnoho dalších – viz *Objekty → Komunikace → Nové spojení* v BAVIS).
3. Založte issue se šablonou *Driver or device request* a napište, že na něm pracujete – nikdo nebude dělat totéž.
4. Začněte příkazem `bavis-sdk new <název> --dir drivers/<název>`, přečtěte si [návody](docs/cs/README.md) a nejbližší
   [příklad](examples/README.md). Nejmenší je [`hello`](examples/hello).

## Požadavky na driver

- **Jen SDK.** BAVIS importujte jen z `bavis.sdk` a `bavis.sdk.testing` – driver pak funguje i s dalšími verzemi.
- **Testy bez hardwaru.** Každý driver má automatické testy proti náhradnímu zařízení nebo nahraným datům, na portech, které
  vybere systém (`testing.free_port()`).
- **Kontroly projdou.** `bavis-sdk check --strict drivers/<název>` a `bavis-sdk test drivers/<název>` jsou zelené.
- **Lehké importy.** Knihovny zařízení se importují uvnitř funkcí, ne na úrovni modulu.
- **Knihovny s kompatibilní licencí** (MIT, BSD, Apache-2.0). Knihovny pod GPL nepřijímáme.
- **Uvedené zdroje.** Mapy registrů a příkazy pocházejí z dokumentace výrobce nebo ze zveřejněné normy – uveďte je v docstringu
  modulu (název, verze, odkaz). Nekopírujte mapy registrů z jiných projektů a nepoužívejte zpětně vyčtená ani neoficiální cloudová
  API, dokud se nezeptáte v issue.
- **Bezpečný zápis.** Zápis do tagů jen pro čtení odmítněte, kde může špatná hodnota poškodit zařízení, nechte zápis ve výchozím
  stavu vypnutý, nikdy nezapisujte cyklicky do flash nebo EEPROM.
- **Žádný skrytý síťový provoz.** Driver komunikuje jen se zařízeními a službami, které nastaví uživatel.
- **Žádná tajemství v kódu.** Hesla, klíče a tokeny patří do polí spojení (`"password"`, `secret=True`).
- **Texty pro obsluhu.** Zdrojový jazyk BAVIS je čeština: popisky, nápovědy a hlášky jsou české klíče s překlady
  v `i18n/en.json` (povinně), `de`, `sk` a `pl`. Pokud česky nepíšete, napište texty anglicky a uveďte to v pull requestu –
  český zdroj a překlady doplníme. Komentáře a docstringy v kódu jsou anglicky.
- **Licence.** Váš příspěvek je pod licencí Apache-2.0 jako celý repozitář.

## Podpis commitů (sign-off)

Každý commit musí mít sign-off (`git commit -s`) podle [Developer Certificate of Origin](https://developercertificate.org/):
potvrzujete, že kód je váš nebo máte právo ho pod licencí Apache-2.0 poskytnout.

## Od pull requestu do katalogu

1. **Pull request** do `drivers/<název>/` podle šablony pull requestu. Jeden driver = jeden pull request.
2. **Automatické kontroly** – workflow spustí `bavis-sdk check --strict`, testy a sestavení s Docker obrazem BAVIS (jakmile bude s BAVIS 4.0 obraz veřejný).
3. **Posouzení** v Benešl Automation: pravidla výše, kód (běží uvnitř BAVIS se stejnými právy jako jádro), uvedená dokumentace
   a texty pro obsluhu. Snažíme se odpovědět na každý pull request do dvou týdnů.
4. **Sloučení a podpis.** Po sloučení balíček sestavíme, podepíšeme klíčem vydavatele Benešl Automation a zveřejníme ve veřejném
   katalogu na BAVIS Central. Instalace BAVIS ho pak nabídnou v *Systém → Projekty a balíčky → Z katalogu*. Driver se objeví
   v [drivers/README.md](drivers/README.md) s vámi jako správcem.
5. **Nové verze** stejnou cestou: zvyšte `__version__` v `bavis_drv_<název>/__init__.py` (`MAJOR.MINOR.PATCH`) a popište změnu
   v pull requestu.

Ve veřejném katalogu jsou jen posouzené a podepsané balíčky. Svůj driver si ale můžete kdykoli sestavit a nainstalovat sami –
nepodepsaný z vlastního katalogu (viz [CI a zveřejnění](docs/cs/06-ci-a-zverejneni.md)) – bez čekání na posouzení.

## Správa driveru

Autor driveru je jeho správce: prosíme ho o reakci na issue a pull requesty k jeho driveru. Když už ho spravovat nemůžete, napište
to do issue – driver v katalogu zůstane a správu může převzít někdo jiný. Driver, který s novou verzí SDK přestane procházet
kontrolami a nemá správce, může být z katalogu odebrán (nainstalované balíčky dál fungují).

## Příklady

Složka `examples/` se udržuje spolu s jádrem BAVIS a kopíruje se sem s každým vydáním SDK; změny příkladů prosím hlaste jako
issue. Drivery komunity patří do `drivers/<název>/`.

## Pravidla chování

Všichni účastníci dodržují [pravidla chování](CODE_OF_CONDUCT.md). Buďte ohleduplní a věcní.
