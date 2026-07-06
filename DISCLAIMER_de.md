<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025  mpc2emu contributors
-->

# Haftungsausschluss

## KI-Unterstützung & menschliche Autorenschaft

Im Sinne der Transparenz: mpc2emu wurde von seinem **menschlichen Autor**
gemeinsam mit **Claude** von Anthropic, einem KI-Programmierassistenten,
entwickelt.

**Die Ideen und die Richtung sind menschlich.** Das Konzept des Werkzeugs, die
Projektvision, jedes Feature (die Multi-Format-Konvertierung, das
Vintage-Resampling, die ZuluSCSI-CD/HDD-Ausgabe, das Anhängen an vorhandene
Images, das Ziel einer reinen Python-/Windows-Lösung …), die Prioritäten und die
Design-Entscheidungen stammen allesamt vom menschlichen Autor.

**Claude unterstützte bei der Umsetzung:**
- Schreiben und Refactoring des Implementierungscodes (Parser, Writer, die
  EMU3-/EMU-fs- und FAT16-Dateisystem-Builder, Resampling, das CLI);
- Analyse binärer Datei- und Disk-Formate aus bereitgestellten Referenzdaten und
  Hex-Dumps sowie Abgleich mit Open-Source-Dokumentation;
- Erstellen und Pflegen der Dokumentation.

**Das Reverse Engineering beruht auf umfangreicher praktischer menschlicher
Arbeit** — dem Teil, den keine KI leisten kann:
- alle Tests und Verifikation auf **echter E-mu-E4XT-Hardware** (per ZuluSCSI);
  jedes „hardware-bestätigte" Ergebnis stammt daher, dass der Autor Bänke auf dem
  echten Instrument geladen und das Funktionieren der Presets geprüft hat;
- Erstellen der **maßgeblichen RE-Referenzen** durch Formatieren von Disks auf
  der echten Hardware und Bereitstellung der Images zur Analyse;
- **akustischer A/B-Vergleich** konvertierter Presets mit den Originalen auf
  echter Hardware und Bereitstellung der Messwerte, die die Klangtreue-Arbeit
  antrieben (LFO-Raten, Filterverhalten, Tuning, Hüllkurven …);
- tiefes **Fachwissen** über die Instrumente und Formate sowie das Aufspüren von
  Fehlern im praktischen Einsatz.

Kurz gesagt: Die KI beschleunigte das Programmieren und die Formatanalyse, doch
die Ideen, das Hardware-Reverse-Engineering, die Hörtests und die Korrektheit des
Ergebnisses sind das Produkt erheblicher menschlicher Arbeit.

## Proprietäre Dateiformate

mpc2emu liest und schreibt Dateiformate, die proprietär von den
jeweiligen Herstellern sind und nie offiziell dokumentiert wurden.
Die Implementierungen in diesem Projekt basieren ausschließlich auf
Community-Reverse-Engineering, veröffentlichten Forschungsergebnissen
und Open-Source-Referenzprojekten (vollständige Quellenangaben siehe
`LICENSE`).

Die Autoren von mpc2emu stehen in keiner Verbindung zu folgenden
Unternehmen und werden von diesen nicht unterstützt:

- **E-mu Systems / Creative Technology Ltd.** (E4B, EOS)
- **Kurzweil / Young Chang Co. Ltd.** (KRZ)
- **Apple Inc.** (EXS24)
- **TEAC Corporation / Tascam** (GigaSampler / GigaStudio)
- **inMusic Brands Inc. / Akai Professional** (MPC XPM)
- **TAL Software GmbH** (TAL-Sampler)

## Keine Gewährleistung

Diese Software wird **wie sie ist** bereitgestellt, ohne jegliche
ausdrückliche oder stillschweigende Gewährleistung, einschließlich,
aber nicht beschränkt auf die Gewährleistung der Marktgängigkeit,
der Eignung für einen bestimmten Zweck und der Nichtverletzung von
Rechten Dritter.

In keinem Fall haften die Autoren oder Urheberrechtsinhaber für
Ansprüche, Schäden oder sonstige Verbindlichkeiten, ob aus Vertrag,
unerlaubter Handlung oder anderweitig, die aus der Software oder
ihrer Nutzung entstehen.

## Hardware-Risiken

Das Laden ungetesteter Dateien auf Vintage-Sampling-Hardware birgt
ein inhärentes Risiko. Vor der Nutzung von mit mpc2emu erzeugten
Dateien auf echter Hardware:

1. **Zuerst auf ZuluSCSI oder SCSI2SD testen**, bevor unersetzliche
   Hardware verbunden wird.
2. **Gute, aktuelle Backups aller deiner Dateien** anlegen — sowie
   jeder vorhandenen Bank auf dem Zielgerät/-medium. mpc2emu schreibt
   rohe Disk-Images und kann **vorhandene Images direkt verändern**
   (`--add-to`), sodass ein Fehler oder Bug Daten überschreiben oder
   beschädigen könnte.
3. **Ausgabe mit `--info` prüfen** und alle Warnungen vor dem
   Schreiben auf Hardware beachten.

Die Autoren übernehmen **keine Verantwortung** für Datenverlust,
Hardwareschäden oder sonstige Nachteile, die aus der Nutzung dieser
Software entstehen.

## SCSI-Disk-Images (.hda)

Das in `.hda`-Images verwendete EMU4-Dateisystem ist proprietär und
wurde von E-mu Systems nie offiziell dokumentiert. Die hier
implementierte Datenstruktur ist aus dem Open-Source-Kernelmodul
`emu3fs` (GPL-2.0-or-later, David García Goñi,
<https://github.com/dagargo/emu3fs>) abgeleitet.

Obwohl Superblock-Magic, Versions-Flags und Directory-Layout anhand
echter Hardware-Images verifiziert wurden, **kann die Kompatibilität
nicht für alle Firmware-Versionen der EIV-Serie garantiert werden**.

`.hda`-Images immer zuerst auf einem nicht produktiven
ZuluSCSI-Setup testen.

## Markenzeichen

Alle genannten Produktnamen, Marken und eingetragenen Markenzeichen
sind Eigentum ihrer jeweiligen Inhaber. Ihre Nennung dient
ausschließlich der Identifikation und impliziert keine Billigung.
