# BAVIS SDK

**Build drivers, symbols, screen elements and tools for BAVIS – the web SCADA you configure yourself.**

> **Status: coming with BAVIS 3.1.** This repository is being prepared. The first SDK release, examples and
> templates will be published together with BAVIS 3.1. Watch the repository to be notified.

[Česky níže](#česky)

## What is BAVIS

BAVIS is a web-based SCADA / HMI platform by [Benešl Automation](https://benesl-automation.cz). It runs as a service,
operators and engineers use it from any browser, and almost everything is set up in tables and wizards instead of code:
connections, tags, alarms, screens, trends, reports.

The core is closed source. This SDK is open (Apache-2.0) so that anyone can extend BAVIS without access to the core.

## What you will be able to build

BAVIS is modular. Every extension point is a small, self-describing module that the core discovers on its own.

| Module | What it adds |
| --- | --- |
| Communication driver | a new protocol or device: connection form, address help, connection test, browsing, device discovery, simulation |
| Server | BAVIS publishing data to other systems |
| Object template and faceplate | a reusable device (pump, valve, meter) with its tile and detail window |
| Screen element | a new element for the screen editor |
| Symbol | SVG symbols for P&ID, buildings and floor plans |
| Device type | a ready-made device with tags, alarms and an object, inserted in one step |
| Project template | a starting project for an industry or use case |
| Tool | scripts and utilities around BAVIS (import, export, migration, testing) |

Drivers can be shipped as a signed `.bavispkg` package of type `drivers` and installed in
**System → Projects and packages** without a new BAVIS release.

## Planned content

```
docs/        how modules work, step-by-step guides, API reference
templates/   starting skeletons for each module type
examples/    complete example modules with tests
tools/       helper tools for building, testing and packaging modules
```

## Contributing

Community drivers, symbols, device types and tools are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first.
Modules accepted into the public catalogue are reviewed and signed by Benešl Automation.

## Licence

The SDK, templates and examples are licensed under the [Apache License 2.0](LICENSE).
The BAVIS core application is proprietary and is not part of this repository.

## Contact

- Website: [benesl-automation.cz](https://benesl-automation.cz)
- E-mail: [benesl@benesl-automation.cz](mailto:benesl@benesl-automation.cz)
- Security issues: see [SECURITY.md](SECURITY.md)

---

## Česky

**BAVIS SDK** slouží k tvorbě driverů, symbolů, prvků obrazovek a nástrojů pro BAVIS, webovou SCADA, kterou si nastavíte sami.

> **Stav: připravujeme k vydání BAVIS 3.1.** První verze SDK, příklady a šablony vyjdou spolu s BAVIS 3.1.

Jádro BAVIS je uzavřené, SDK je otevřené (licence Apache-2.0). Kdokoli tak může BAVIS rozšířit bez přístupu k jádru:
o komunikační driver, server, šablonu objektu a faceplate, prvek obrazovky, symbol, typové zařízení, šablonu projektu
nebo nástroj. Drivery jde dodat jako podepsaný balíček `.bavispkg` a nainstalovat bez nové verze BAVIS.

Příspěvky komunity jsou vítané, postup je v [CONTRIBUTING.md](CONTRIBUTING.md). Kontakt:
[benesl@benesl-automation.cz](mailto:benesl@benesl-automation.cz), web [benesl-automation.cz](https://benesl-automation.cz).
