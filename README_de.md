<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# mpc2emu

Multi-Format-Sampler-Konverter mit Vintage-Resampling und ZuluSCSI-Ausgabe.
Wandelt Sample-Bibliotheken zwischen gängigen Sampler-Formaten um und erzeugt
ZuluSCSI-fähige CD-ISO-Images oder native SCSI-Festplatten-Images für
den EMU Emulator 4 / E4XT und Kurzweil K2000.

> **See also:** [README.md](README.md) — English version  
> **Rechtliches:** [DISCLAIMER_de.md](DISCLAIMER_de.md) · [LICENSE](LICENSE)

---

## ⚠️ Nutzung auf eigene Gefahr — vorher Backups anlegen

mpc2emu wird **ohne jede Gewährleistung und ohne Haftung** bereitgestellt — für
Datenverlust, Hardware-Schäden, beschädigte Medien oder sonstige Folgen der
Nutzung. Das gesamte Risiko liegt bei dir. (Vollständige Bedingungen:
[DISCLAIMER_de.md](DISCLAIMER_de.md).)

**Lege vor der Nutzung gute, aktuelle Backups all deiner Dateien an** — sowie
vorhandener Bänke auf deinem Sampler und den SCSI-Medien. mpc2emu schreibt rohe
Disk-Images und kann **vorhandene Images direkt verändern** (`--add-to`); ein
Fehler, ein Bug oder ungetestete Ausgaben können Daten überschreiben/beschädigen
oder von der Hardware abgelehnt werden. Teste Images immer zuerst auf einem
ZuluSCSI / SCSI2SD / Emulator, **bevor** du unersetzliche Geräte anschließt.

---

## KI-Unterstützung & menschliche Autorenschaft

mpc2emu wurde von seinem menschlichen Autor gemeinsam mit **Claude** von
Anthropic entwickelt. Die **Ideen, die Projektvision und jedes Feature** stammen
vom menschlichen Autor; Claude unterstützte beim **Schreiben des Codes und der
Analyse der Binärformate**. Entscheidend ist: Das **Reverse Engineering beruht
auf praktischer menschlicher Arbeit** — alle Tests und die Verifikation auf
echter E-mu-E4XT-Hardware, das Erstellen der RE-Referenz-Images auf dieser
Hardware und der akustische A/B-Vergleich der Presets — was die Ergebnisse
korrekt macht. Vollständige Darstellung in [DISCLAIMER_de.md](DISCLAIMER_de.md).

---

## Unterstützte Formate

### Eingabe

| Format | Endung | Beschreibung |
|---|---|---|
| EMU E4B | `.e4b` / `.E4B` | EMU Emulator 4 / E4XT Bank — Import zum Resampling / Re-Export |
| Akai MPC Keygroup | `.xpm` | MPC 2.x / MPC X / Live / One (XML) |
| Akai MPC Drum-Programm | `.pgm` | MPC 500/1000/2500, **MPC 2000/2000XL** (`.WAV`) und MPC 60 (12-Bit `.SND`) |
| Akai MPC60 SET / Floppy | `.set` / `.img` | MPC-60-RAM-Set; `.img` = FAT12-Floppy (SET automatisch extrahiert) |
| TAL-Sampler | `.talsmpl` | TAL Software GmbH (XML + WAV) |
| SFZ v1/v2 | `.sfz` | Offener Standard, `#include` unterstützt |
| SoundFont 2 | `.sf2` | RIFF-basiert, E-mu / Creative |
| Logic EXS24 | `.exs` | Logic Pro / MainStage — Little-Endian klassisch und v1.1 (Logic 10.4+) |
| GigaSampler / GigaStudio | `.gig` | DLS2-basiert, nur unkomprimiert |
| Zampler | — | Nutzt SFZ nativ → über SFZ-Parser |
| **WAV-Sample-Ordner** | _Verzeichnis_ | Auf ein Verzeichnis mit grundton-benannten `.wav`s zeigen (z. B. `Piano C3.wav`, `Pad_60.wav`) → baut automatisch ein Multisample-Preset (`--from-samples`; auch automatisch erkannt bei reinem WAV-Verzeichnis; `--middle-c` legt die Oktavkonvention fest) |

> `.pgm` umfasst drei **binäre** Drum-Programm-Formate, per Magic erkannt:
> MPC500/1000/2500 (`MPC1000 PGM 1.00` — 64 Pads, 4 Samples/Pad → Velocity-Layer);
> MPC2000/2000XL (`0x07 0x04` — 64 Pads mit externen `.WAV`); und MPC 60
> (`0x07 0x00` — externe 12-Bit-`.SND`, auf 40 kHz dekodiert). Sample-Dateien
> liegen neben der `.pgm`; eine MPC2000-**ISO9660-CD** zuerst entpacken
> (z. B. `7z x disc.iso`) und den Ordner konvertieren. Andere `.pgm`-Varianten
> (z. B. Akai `BD12`) und das XML-`.xpm` werden separat behandelt.  
> `.talwav`-Dateien (TAL-verschlüsselt) können nicht gelesen werden.  
> Giga-komprimierte Samples werden nicht unterstützt; unkomprimierte `.gig`-Dateien funktionieren.  
> EXS24 v1.1 (Logic 10.4+, Magic `0x00000101`): Zonen-Sample-Zuordnung ist positionsbasiert; Mehrschicht-Velocity-Instrumente laden nur die erste Schicht.

### Ausgabe

| Format | Endung | Zielgerät |
|---|---|---|
| EMU E4B | `.E4B` | EMU Emulator 4 / E4XT / E4K (EOS 4.x) |
| Kurzweil KRZ | `.KRZ` | Kurzweil K2000 / K2500 / K2600 |
| TAL-Sampler | `.talsmpl` | TAL-Sampler VST/AU |

---

## Anforderungen

- Python 3.8 oder neuer
- Keine Pflicht-Abhängigkeiten (nur Standardbibliothek)

---

## Installation

```bash
git clone https://github.com/youruser/mpc2emu.git
cd mpc2emu
```

---

## Schnellstart

```bash
# HINWEIS: Die Ausgabe ist standardmäßig --format e4b (EMU E4B). Die Beispiele
# unten geben es explizit an; mit --format krz (Kurzweil K2000) oder
# --format talsmpl (TAL-Sampler) änderst du das. --hda gibt es für e4b + krz,
# --floppy nur für krz.

# Datei prüfen ohne Konvertierung
python convert.py Piano.sf2 --info
python convert.py DrumKit.sfz --info --verbose

# XPM → E4B + ZuluSCSI CD-ISO
python convert.py MyDrums.xpm --format e4b --iso

# XPM → E4B + ZuluSCSI SCSI-Festplatten-Image
python convert.py MyDrums.xpm --format e4b --hda

# Ganzen Ordner konvertieren, 64 MB Bänke, B.NNN-Präfix-Benennung, ISO
python convert.py /mpc/programs/ --format e4b --bank-size 64 --bank-start 100 --iso

# TAL-Sampler-Preset → E4B
python convert.py MyPreset.talsmpl --format e4b

# SFZ-Bibliothek → Kurzweil KRZ
python convert.py /sfz/pianos/ --format krz

# GIG-Datei → E4B (max. 16 Instrumente)
python convert.py Orchestra.gig --format e4b --max-presets 16 --hda

# Vintage-Resampling: EMU Emulator II Sound
python convert.py /mpc/programs/ --format e4b --resample emulator2 --iso

# Vintage-Resampling: EMU Emax I Sound, ohne Bandpass-Coloring
python convert.py /sfz/ --format e4b --resample emax1 --no-bandpass

# Vintage-Resampling: alle CPU-Kerne nutzen (Standard ist cpu_count-1)
python convert.py /sfz/ --format e4b --resample emulator2 --jobs 8 --iso

# Dicht gesampelte Library auf Vintage-Speichergrenzen ausdünnen:
# alle Velocity-Layer behalten, aber 30% der Key-Zonen entfernen
python convert.py /sfz/pianos/ --format e4b --reduce-key-zones 30 --iso
```

---

## Alle Optionen

```
python convert.py <eingabe> [optionen]

Eingabe:
  input               Datei oder Verzeichnis
                      (.e4b .xpm .pgm .set .img .talsmpl .sfz .sf2 .exs .gig)

Info-Modus:
  --info              Datei(en) analysieren ohne zu konvertieren
  --verbose           Zonen-Details mit --info anzeigen

Ausgabe:
  --format FORMAT     e4b | krz | talsmpl  (Standard: e4b)
  --output-dir DIR    Ausgabeverzeichnis  (Standard: aktuelles Verzeichnis)
                      (Alias: --out-dir)
  --overwrite         Vorhandene Ausgabedateien ohne Nachfrage überschreiben
                      (Standard: vor dem Überschreiben nachfragen; nicht-
                       interaktive Shells brechen ohne --overwrite ab)
  --bank-size MB      Maximale Bankgröße  (Standard: 32; Alias: --max-bank-size)
                      Akzeptiert die Suffixe K/KB/M/MB/G/GB; eine reine Zahl = MB
                      (z. B. --max-bank-size 64MB).
  --max-preset-size SIZE  Jedes einzelne Preset/Programm begrenzen (z. B. 8192K),
                      damit kein Preset eine ganze Bank füllt; zu große Presets
                      werden zum Einpassen ausgedünnt.  (Standard: keine Grenze)
  --auto-fit          Wenn ein einzelnes Preset zu groß für eine Bank ist (oder
                      über --max-preset-size), automatisch die verlustärmste
                      Einpass-Reduktion anwenden statt abzubrechen (für Batch-Läufe).
  --bank-name NAME    Basisname der Ausgabebanken  (Standard: EMU_BANK)
  --bank-start N      Banknummerierung B.NNN-NAME… ab N, damit die Bankdateien
                      direkt auf ein vorhandenes E4XT-Volume kopiert werden
                      können — kein --iso nötig (z. B. 100 → B.100-NAME_01.E4B …)

ZuluSCSI-Images:
  --iso               CD-Image(s) für ZuluSCSI erzeugen  (e4b → EMU3, krz → K2000 FAT16)
  --hda               SCSI-Festplatten-Image (.hda) erzeugen  (e4b + krz)
                      e4b → E4XT EMU-fs/FAT-Disk; krz → K2000-FAT16-Disk
                      (HW-bestätigt — lädt von einem ZuluSCSI-HDx-Gerät)
  --hda-size MB       Größe des HDA-Images in MB
                      e4b-Standard: auto — kleinste 128-MB-Stufe, die passt; max 14336
                      krz-Standard: Inhalt + ~50% Reserve zum Speichern (FAT16 max ~2047)
  --hda-fs FS         E4B-HDA-Dateisystem: fat | emu  (Standard: fat; für krz ignoriert)
                      fat — FAT16-Image im nativen EOS-Layout (MBR-Partition bei
                            LBA 63, 32-KB-Cluster), von EOS 4.7+ lesbar (benötigt
                            'mtools'); Bänke B.NNN-NAME.E4B im Stammverzeichnis.
                            Mind. 512 MB verwenden.
                      emu — natives EMU-fs (EMU3), von allen EOS-Versionen
                            lesbar (auch <=4.62 ohne FAT).  Voll dimensioniertes
                            Image (gemäß --hda-size) mit freiem Speicher;
                            Clustergröße skaliert mit der Disk (512 MB..~16 GB).
                      Beide Dateisysteme sind auf E4XT-Hardware bestätigt.

Floppy-Image (nur KRZ):
  --floppy [KB]       Jede Bank in ein DOS-FAT12-Floppy-Image (.img) für ein
                      Gotek / FlashFloppy am K2000R schreiben  (Standard: 1440 =
                      1,44 MB)

Zu vorhandenem Image hinzufügen (statt neues zu bauen):
  --add-to IMAGE      Konvertierte Bank(s) an ein vorhandenes .hda anhängen (FAT
                      oder EMU-fs, automatisch erkannt).  Überschreibt nie
                      vorhandene Bänke.
  --folder NAME       Zielordner im Image, wird bei Bedarf erstellt
                      (Standard: Root / Default Folder; EMU-fs: <=100 Bänke/Ordner).
  --on-duplicate WAS  prompt (Standard) | add-new (nächste freie Nummer/Slot) |
                      skip | overwrite — Verhalten bei vorhandenem Namen.

Samples:
  --wav-dir DIR       Zusätzliches Verzeichnis für WAV-Samples
  --max-presets N     Max. Presets aus SF2/GIG  (Standard: 64)
  --max-sample-rate HZ  Jedes Sample über HZ sauber auf HZ heruntersampeln
                      (Standard 24000 Hz für --format krz — Headroom fürs
                       Hochpitchen + kleinere Bänke; 0 = deaktivieren; kein
                       Standard für e4b)
  --from-samples      Das Eingabeverzeichnis als Ordner von WAVs behandeln
                      (Grundton im Dateinamen) → ein automatisch gebautes
                      Multisample-Preset (auch automatisch erkannt bei reinem
                      WAV-Verzeichnis)
  --middle-c {auto,C3,C4,C5}  Oktavbenennung für Grundtöne aus Dateinamen:
                      welches C = MIDI 60  (Standard: auto)

Vintage-Resampling:
  --resample PROFILE  emulator2  (8-bit / 27,5 kHz, EMU Emulator II)
                      emax1      (12-bit / 27,5 kHz, EMU Emax I)
  --no-bandpass       Bandpass-Coloring deaktivieren
  --resample-keep-gain Den gain-gestageten ("lauten") Pegel beibehalten statt
                      jedes Sample danach auf seinen Originalpegel
                      zurückzuskalieren (Standard: zurückskalieren)
  --jobs N            Parallele Worker für Resampling  (Standard: cpu_count-1)

Modulation:
  --lfo-sync-bpm BPM  Referenztempo, um tempo-synchrone MPC-LFOs als feste Rate
                      zu reproduzieren  (Standard: 120; siehe docs/lfo_sync_rates.md)

Sample-Anzahl reduzieren (moderne Libraries an Vintage-Speichergrenzen anpassen):
  --reduce-key-zones PCT        PCT% der Key-Zonen-Samples pro Voice entfernen
  --reduce-velocity-layers PCT  PCT% der Velocity-Layer-Voices pro Preset entfernen
                      Beide stehen standardmäßig auf 0 (aus) und sind
                      unabhängig — z. B. nur --reduce-key-zones setzen, um
                      jeden Velocity-Layer zu behalten und nur den
                      Tastatur-Split auszudünnen. Die Key-/Velocity-Bereiche
                      der verbleibenden Zonen werden gleichmäßig auf
                      benachbarte Zonen verteilt, um die entstandenen
                      Lücken zu schließen.
```

---

## --info Modus

Analysiert jede unterstützte Eingabedatei und zeigt eine strukturierte
Zusammenfassung — ohne Ausgabedateien zu schreiben.

```
$ python convert.py DrumKit.sfz --info

mpc2emu --info  (1 file(s))

────────────────────────────────────────────────────────────
  DrumKit.sfz
────────────────────────────────────────────────────────────
  Format:    SFZ v1/v2 (text)
  Bank name: DrumKit
  Presets:   1
  Samples:   12
  Zones:     24
  PCM data:  8.34 MB
  Est. E4B:  8.36 MB

  Presets:
    [00] DrumKit              1 layer(s)  24 zone(s)  prog 0

  Samples:
    [00] Kick_A               44100 Hz  16-bit  mono  320 ms  …

  ⚠  1 Warnung(en):
     • Sample 'HiHat_Open': Loop aktiv, aber loop_end=0
```

Mit `--verbose` werden zusätzlich die Voice-Parameter (Amp-ADSR,
Filterfrequenz/Q und Chorus-Amount, sofern gesetzt) sowie einzelne
Key/Velocity-Zonen je Voice angezeigt.

---

## ZuluSCSI Workflows

### CD-Image — E4XT (EMU3-Dateisystem)

Bei `--format e4b` erzeugt `--iso` ein **EMU3-Dateisystem**-Image —
dasselbe Format wie auf originalen E-mu Sample-CDs. ZuluSCSI stellt dieses
als CD-ROM-Laufwerk bereit; der E4XT liest es direkt und zeigt einen
„Default Folder" mit allen Bänken. Es handelt sich **nicht** um ISO 9660.

> Siehe [`docs/EMU3_ISO_FORMAT.md`](docs/EMU3_ISO_FORMAT.md) (Englisch) für
> die komplette reverse-engineerte Referenz dieses Dateisystems (Superblock,
> FAT, Verzeichnisstruktur, Cluster-Allokation und die Hardware-Eigenheiten —
> etwa die `blks`-muss-aufgerundet-werden-Falle —, die erst durch echte
> E4XT-Tests aufgedeckt wurden), sowie das Standard-ISO-9660-Format des
> K2000 weiter unten.

```bash
python convert.py /mpc/programs/ --format e4b --bank-size 64 --bank-start 100 --iso
```

1. Erzeugte `.iso`-Datei auf die ZuluSCSI SD-Karte kopieren
2. Umbenennen zu `CD1.iso` (weitere Discs: `CD2.iso`, `CD3.iso` …)
3. E4XT einschalten → **Load → CD-ROM** → Bank auswählen

Mehrere `.iso`-Dateien auf derselben SD-Karte erscheinen als separate
CD-Laufwerke (CD1, CD2, …).

### CD-Image — K2000 (FAT16-Disk-Image)

Bei `--format krz` erzeugt `--iso` eine **FAT16-Disk-Image-Kopie** (BPB in
Sektor 0, keine Partitionstabelle, OEM `KCDM1.2`) — die universell kompatible
K2000/K2500-Disk-Form, die **jedes K2000-OS liest**. Es ist *kein* ISO 9660:
echtes ISO 9660 braucht K2000-OS **v3.87+** / K2500 2.96+ (`build_iso_9660`
erzeugt das bei Bedarf). ZuluSCSI stellt die `.iso` als CD-ROM bereit.

> **Vollständige Byte-Format-Referenz für KRZ:** siehe
> [`docs/KRZ_FORMAT.md`](docs/KRZ_FORMAT.md) (Englisch) — das Bank/Objekt-Modell
> (Sample / Keymap / Program), die VAST-Programm-Kodierung (Filter, Hüllkurven,
> LFO) und das FAT16-CD/Festplatten-Layout, reverse-engineered aus Hardware und
> dem KurzFiler-Quellcode.

```bash
python convert.py /sfz/pianos/ --format krz --iso
```

1. Erzeugte `.iso`-Datei auf die ZuluSCSI SD-Karte kopieren
2. Umbenennen zu `CD1.iso`
3. K2000 einschalten → **Load → CD-ROM** → Bank auswählen

> Dasselbe FAT16-Image funktioniert auch als **Festplatte** — siehe den
> K2000-HD-Abschnitt unten.

### SCSI Festplatte (.hda) — E4XT

```bash
python convert.py /mpc/programs/ --format e4b --bank-size 64 --hda --hda-size 200
```

1. `output/EMU_BANK.hda` auf die ZuluSCSI SD-Karte kopieren
2. Umbenennen zu `HD10_512.hda` (SCSI-ID 0, 512-Byte-Sektoren)
3. E4XT einschalten → **Load → Hard Disk** → Bank auswählen

Die Festplatte lädt schneller als CD und unterstützt bis zu 14 GB
(EIV-OS-Limit).

### SCSI Festplatte (.hda) — K2000

Bei `--format krz` erzeugt `--hda` ein **K2000-FAT16-Festplatten-Image** — dieselbe
Disk-Image-Kopie wie die CD-Form, aber mit freiem Speicher, damit der K2000 auch
darauf **speichern** kann. **Hardware-bestätigt auf einem K2000R**: Bänke laden
und spielen direkt von einem ZuluSCSI-`HDx`-Gerät.

```bash
python convert.py /sfz/pianos/ --format krz --hda --hda-size 1024
```

1. Erzeugte `.hda`-Datei auf die ZuluSCSI SD-Karte kopieren
2. Umbenennen zu `HD1-<name>.hda` — eine **freie SCSI-ID** wählen (`HD1`, `HD3`, …);
   ZuluSCSI liest sie als Festplatte mit den Standard-512-Byte-Blöcken
3. K2000 einschalten → **Load → Disk** → Bank auswählen

`--hda-size` legt die Volume-Größe in MB fest (Standard: Inhalt + ~50% Reserve;
FAT16-Maximum ~2047 MB).

### Dateien nachträglich mit emu3fs hinzufügen (Linux)

```bash
# Image einbinden
sudo losetup -b 512 /dev/loop0 output/EMU_BANK.hda
mkdir -p /mnt/emu4
sudo mount -t emu4 /dev/loop0 /mnt/emu4

# Dateien kopieren
sudo cp NeueBank.E4B /mnt/emu4/

# Aushängen
sudo umount /mnt/emu4
sudo losetup -d /dev/loop0
```

emu3fs: <https://github.com/dagargo/emu3fs>

---

## E4B Voice-Parameter

Voice-Parameter werden durch Hardware-Reverse-Engineering aus dem Quellformat
auf EOS 4.x abgebildet (verglichen mit bestätigten E4XT-Byte-Werten aus
JL AnalogBank, B.005-FltEnvTest, FLTTYPES sowie den Amp-Hüllkurven-Bänken
AMPENV_SETME / AMP_DECAY_CAL).

> **Vollständige Byte-Format-Referenz:** siehe
> [`docs/E4B_FORMAT.md`](docs/E4B_FORMAT.md) (Englisch) für die komplette
> Bank-/Preset-/Voice-/Zone-/Sample-Struktur, Byte-Offset-Tabellen und die
> nicht offensichtlichen Kodierungskonventionen (und Bugs), die wir dabei
> entdeckt haben — damit andere von dieser Reverse-Engineering-Arbeit
> profitieren können.

### Filter

Alle 8 MPC-Filtertypen (MPC 3.7-Handbuch, Anhang) werden dem nächstliegenden
verfügbaren E4XT-Äquivalent zugeordnet:

| MPC-Typ | Name | E4XT-Typ |
|---|---|---|
| 0 | Off | Bypass (4PLP vollständig offen) |
| 1 | Low 1 — 1-polig TP | 2-Pole LP |
| 2 | Low 2 — 2-polig TP | 2-Pole LP |
| 3 | Low 4 — 4-polig TP | 4-Pole LP |
| 4 | Low 6 — 6-polig TP | 6-Pole LP |
| 5 | Low 8 — 8-polig TP | 6-Pole LP (nächster) |
| 6–10 | High 1–8 | 2nd / 4th Order HP |
| 11–14 | Band 2–8 | 2nd / 4th Order BP |
| 15–18 | BS 2P–8P (Bandsperr-/Notchfilter) | Contrary BP |
| 19–22 | BB 2P–8P (Bandanhebung) | 4th Order BP (nächster) |
| 23–25 | Model 1–3 (analoge Emulationen) | 4-Pole LP |
| 26–28 | Vocal 1–3 (Formant) | 4-Pole LP |
| 29 | MPC3000 LPF (12 dB/Okt) | 2-Pole LP |

Filterfrequenz (0,0–1,0 linear → exponentielle Hz-Skala, 0≈57 Hz / 255=20 kHz),
Resonanz (0,0–1,0 direkt) sowie die 6-stufige Filterhüllkurve
(Attack1/2 · Decay1/2 · Release1/2 mit Rate + Level je Stufe) werden
aus dem Quell-Preset übernommen.

### Amplitudenhüllkurve

Die vollständige 6-stufige Amplitudenhüllkurve (`PZT[0:12]`, gleiche Struktur
wie die Filterhüllkurve) wird aus Attack / Decay / Sustain / Release des
Quell-Presets übernommen. Das Amp-**Decay-Raten**-Byte (`PZT[4]`) und die
**Raten↔Zeit**-Umrechnung wurden am E4XT reverse-engineered: Das Decay-Byte
wurde per Einzelbyte-Sweep isoliert und die Ratenkurve aus sechs gemessenen
Decay-bis-Stille-Zeiten zu `time_s = 0.0310 · e^(0.0581 · rate)` kalibriert
(Rate 0 = sofort, 127 ≈ 47 s). Siehe
[`docs/re_procedures/amp_envelope.md`](docs/re_procedures/amp_envelope.md).

### Chorus

Der **Chorus-Amount** je Voice (`vpar[42]`) wird gelesen und geschrieben: Der
0–100-%-Regler des E4XT wird linear auf ein `0–127`-Byte abgebildet
(`round(pct/100 × 127)`), hardware-bestätigt gegen kommerzielle Bänke und einen
25/50/75/100-%-Speicher-Sweep. (Die Chorus-*Stereobreite* ist ein separates,
noch nicht dekodiertes Byte.)

### Loops

WAV-SMPL-Chunks werden für alle Eingabedateien gelesen. Vorwärts-Loops
verwenden die E4XT-bestätigte Codierung (`opts=0x0031`). EOS hat keinen
Ping-Pong-(Alternierend-)Loop-Modus, daher werden Ping-Pong-Loops **ins PCM
gerendert**: eine umgekehrte Kopie des Loop-Inneren wird eingefügt, sodass ein
Vorwärts-Loop den Bounce reproduziert (dieselbe Technik, die EOS für
importierte EIII-Loops verwendet).

Samples mit **SMP**-Einstellung im MPC-Programmeditor (RootNote=0, keine
Tonhöhenverfolgung) werden in einer einzigen Zone über den gesamten Tastaturbereich
(root=60) platziert, um extreme Tonhöhen-Transposition zu vermeiden.

---

## Vintage Resampler

Simuliert die Signalkette zweier klassischer E-mu-Sampler:

| Profil | Gerät | Bit-Tiefe | Samplerate | Charakter |
|---|---|---|---|---|
| `emulator2` | EMU Emulator II (1984) | 8 Bit | 27.500 Hz | Hartes Truncation-Rauschen, RC-Filter, DC-Offset |
| `emax1` | EMU Emax I (1986) | 12 Bit | 27.500 Hz | TPDF-Dither, saubereres Rauschen |

Signalkette (6 Stufen):
1. Anti-Alias-Filter (1-polig RC für E2, 2-polig Butterworth für Emax)
2. Dezimation auf Zielsamplerate (naiv — gewolltes Aliasing)
3. **Gain-Staging**: Jedes Sample wird vor der Quantisierung Richtung
   Vollaussteuerung angehoben — genau das, was ein Sound-Designer der Ära
   beim Sampeln getan hätte, um das Beste aus der begrenzten Bit-Tiefe des
   Geräts herauszuholen. Ohne diesen Schritt verliert Quellmaterial, das
   deutlich unter Vollaussteuerung liegt (bei modernen WAV/SF2/SFZ-
   Libraries üblich), weit mehr Auflösung an den Quantisierer als das
   Profil eigentlich modellieren soll, und klingt am Ende rauschiger als
   die echte Hardware es je täte.
4. Requantisierung + optionales TPDF-Dithering (arbeitet jetzt auf einem
   korrekt ausgesteuerten Signal, sodass das Ausgangs-SNR der Profilvorgabe entspricht)
5. Bandpass-Coloring (Ausgangsfiltermodell, deaktivierbar mit `--no-bandpass`)
6. Pegel-Wiederherstellung: standardmäßig wird jedes Sample danach auf
   seinen ursprünglichen Spitzenpegel zurückskaliert, damit es die
   Lautstärke behält, mit der das Patch erstellt wurde. Mit
   `--resample-keep-gain` bleibt stattdessen der lautere, ausgesteuerte Pegel erhalten.

Samples werden parallel verarbeitet (`ProcessPoolExecutor`).
Standard: `cpu_count − 1` Worker; überschreibbar mit `--jobs N`.

---

## Bank-Splitter

Verteilt Presets automatisch auf mehrere Ausgabebanken:

- **First-Fit-Decreasing**-Algorithmus — maximiert den Füllgrad
- Presets bleiben immer **komplett** in einer Bank
- Samples werden innerhalb einer Bank **dedupliziert**; Namen über 16 Zeichen
  werden mit numerischem Suffix abgekürzt um Eindeutigkeit zu gewährleisten
- Warnung wenn ein Preset das Limit überschreitet

---

## Übergroße Presets einpassen

Ein Preset wird nie über mehrere Bänke aufgeteilt, daher muss ein einzelnes
Preset, das zu groß für eine Bank ist (oder über `--max-preset-size` liegt),
**ausgedünnt** werden, um zu passen. In einer interaktiven Shell gibt mpc2emu
dimensionierte Vorschläge aus — Velocity-Layer entfernen → Key-Zonen ausdünnen →
heruntersampeln, verlustärmste zuerst — und wendet deine Wahl an. Mit
`--auto-fit` geschieht das automatisch. Ein Batch-Lauf ohne `--auto-fit` gibt die
Vorschläge aus und endet mit einem Exit-Code ungleich null, sodass niemals
stillschweigend eine übergroße / nicht ladbare Bank geschrieben wird. Das
funktioniert für E4B (128 MB E4XT) und KRZ (64 MB K2000).

Hardware-Grenzen je Bank: max. **1000 Samples** und **1000 Presets** pro Bank;
maximale Bankgröße **128 MB** (E4XT) / **64 MB** (K2000).

---

## Projektstruktur

```
mpc2emu/
├── LICENSE
├── DISCLAIMER.md
├── DISCLAIMER_de.md
├── README.md
├── README_de.md
├── convert.py                  # CLI-Einstiegspunkt
├── info_cmd.py                 # --info Implementierung
├── test_pipeline.py            # Smoke-Tests
├── models/
│   └── common.py               # Interne Datenmodelle
├── parsers/
│   ├── registry.py             # Format-Autoerkennung / Parser-Dispatch
│   ├── xpm_parser.py           # Akai MPC XPM (Filter, Loops, SMP-Velocity-Split)
│   ├── pgm_parser.py           # Akai MPC500/1000/2500 + 2000/XL + MPC60 Drum-Programm
│   ├── mpc60_parser.py         # Akai MPC60 SET / FAT12-Floppy-Image (12-Bit-RAM-Set)
│   ├── talsmpl_parser.py       # TAL-Sampler (Parser + Writer; 13-Modi-Filtertabelle)
│   ├── tal_template.py         # TAL-Sampler-Preset-Vorlage für den Writer
│   ├── sampledir_parser.py     # WAV-Sample-Ordner → automatisch gebautes Multisample-Preset
│   ├── sfz_parser.py           # SFZ v1/v2
│   ├── sf2_parser.py           # SoundFont 2
│   ├── exs24_parser.py         # Logic EXS24 (LE klassisch + v1.1; Stereo-Deduplizierung)
│   ├── gig_parser.py           # GigaSampler / GigaStudio
│   └── e4b_parser.py           # EMU-E4B-Import (Umkehrung von e4b_writer)
├── writers/
│   ├── e4b_writer.py           # EMU E4B (FORM-Größe + EMSt; Filter, Loops, Zonen)
│   ├── krz_writer.py           # Kurzweil KRZ
│   ├── iso_builder.py          # EMU3-Filesystem-Image für ZuluSCSI-CD-Emulation
│   ├── hda_builder.py          # SCSI-Festplatten-Image (.hda)
│   ├── fat12.py                # FAT12-Floppy-Image (K2000R Gotek / FlashFloppy)
│   ├── fat16.py                # FAT16-Image im nativen EOS-Layout (--hda-fs fat)
│   ├── fat32.py                # FAT32-Image-Builder
│   └── bank_splitter.py        # Bank-Aufteilung
├── processors/
│   ├── resampler.py             # Vintage Resampler
│   ├── zone_reducer.py          # Key-Zonen-/Velocity-Layer-Ausdünnung für Vintage-Speichergrenzen
│   └── loop_renderer.py         # Ping-Pong → Vorwärts-Loop (Bounce ins PCM eingebacken)
└── tests/
    └── re_banks/                # Hardware-RE-Helfer: Testbank-Generatoren
        ├── gen_amp_envelope_test.py   #   Amp-Hüllkurve (Decay-Byte / Raten-Kalibrierung)
        ├── gen_filter_envelope_test.py #  Filterhüllkurve Decay-1-Raten-Kalibrierung
        ├── gen_xpm_envelope_test.py   #   MPC-(.xpm)-Hüllkurve Wert→Zeit-Kurve (MPC One)
        ├── analyze_envelope_recording.py # Decay-Zeiten je Note aus einer Aufnahme messen (numpy)
        ├── gen_filter_types_test.py   #   vpar[58] Filtertyp-Sweep
        ├── gen_zone_entry_test.py     #   Sekundärzonen-Eintrag-Feldtests
        └── inspect_vpar.py            #   beliebiges vpar[N] über Bänke ausgeben (fand vpar[42]=Chorus)
```

---

## Bekannte Einschränkungen

| Feature | Status |
|---|---|
| Stereo-Samples nativ (E4B) | ❌ wird zu Mono downgemischt |
| GIG Giga-Codec (komprimiert) | ❌ nicht unterstützt |
| TAL `.talwav` (verschlüsselt) | ❌ nicht lesbar |
| EXS24 PPC Big-Endian | ❌ nicht unterstützt — gleiche Magic-Bytes wie LE, nicht unterscheidbar |
| EXS24 v1.1 Mehrschicht-Velocity | ⚠️ nur erste Schicht — positionsbasierte Zuordnung |
| EXS24 v1.1 L/R-Stereo | ✅ dedupliziert — `_R`-Gruppe entfällt, wenn `_L`-Partner existiert |
| E4B Filter-Typ / Cutoff / Q | ✅ aus MPC XPM (MPC 3.7 Handbuch) sowie EXS24 (FILTER1) und GIG (VCF) |
| E4B Filterhüllkurve aus Quelle | ✅ XPM, SFZ (`fileg_*`), SF2 (Mod-Env→Cutoff), GIG (EG2/VCF) und EXS24 (ENV2) |
| E4B Vorwärts-Loops | ✅ SMPL-Chunk wird gelesen; `opts=0x0031` hardware-bestätigt |
| E4B Ping-Pong-Loops | ✅ EOS hat keinen Ping-Pong-Modus — als Vorwärts-Loop ins PCM gerendert (Bounce eingebacken) |
| E4B Mehrfach-Loop-Samples | ❌ nur der erste SMPL-Loop-Eintrag wird genutzt |
| E4B Non-Transpose (SMP) Voice | ✅ eine Non-Transpose-Voice je Velocity-Bereich (root=60, Zonen über gesamten Bereich) |
| E4B FORM-Größe / EMSt-Chunk | ✅ EMU-Konvention (`filesize−12`) + abschließender `EMSt` — lädt in e-xplorer & von CD |
| E4B VCA-(Amp-)Hüllkurve ADSR aus Quelle | ✅ vollständige 6-stufige Amp-Hüllkurve (`PZT[0:12]`); Decay-Byte `PZT[4]` + Raten↔Zeit-Kurve hardware-kalibriert |
| E4B Chorus-Amount | ✅ je Voice `vpar[42]` gelesen/geschrieben (0–100 % → 0–127, hardware-bestätigt) |
| E4B Chorus-Stereobreite | ❌ separates Byte, noch nicht dekodiert |
| EMU3-ISO-Laden von ZuluSCSI-CD | ✅ `blks`-Ceiling-Division-Fix — End-of-File-Fehler behoben |
| KRZ VAST-Parameter | ⚠️ Safe Defaults — auf K2000 editierbar |
| LFO Rate / Form / Routing | ✅ LFO-Rate/-Form + Pitch-/Filter-Routing für E4B und KRZ abgebildet, plus tempo-synchrone MPC-LFOs via `--lfo-sync-bpm`; einige Tiefenkalibrierungen näherungsweise |
| Binäres MPC `.pgm` | ✅ MPC500/1000/2500, MPC2000/2000XL, MPC60 unterstützt (automatisch erkannt) |
| MPC3000 `.pgm` | ❌ nicht unterstützt — Magic kollidiert mit MPC60, benötigt Body-Diskriminator |
| HDA > 16 Dir-Einträge | ⚠️ einzelner 512-Byte-Dir-Block — warnt und behält erste 16 (Überschuss verworfen, nicht stillschweigend) |

---

## Lizenz und Drittquellen

Dieses Projekt steht unter der **GNU General Public License v2.0 oder
neuer (GPL-2.0-or-later)** — siehe [`LICENSE`](LICENSE).

Es wurde kein Quellcode kopiert. Alle Parser und Writer sind eigenständige
Python-Neuimplementierungen, die durch Formatspezifikationen und
Open-Source-Referenzprojekte informiert wurden:

| Datei | Quelle | Lizenz | Autor |
|---|---|---|---|
| `gig_parser.py` | [libgig](https://www.linuxsampler.org/libgig/) — DLS/Giga-Struktur; `3ewa`-Artikulationslayout + `GIG_EXP_DECODE` EG1/EG2/VCF-Dekodierung (`gig.cpp` `DimensionRegion`), byte-genau gegen `gigdump` verifiziert | GPL-2.0-or-later | Christian Schoenebeck |
| `hda_builder.py` | [emu3fs](https://github.com/dagargo/emu3fs) | GPL-2.0-or-later | David García Goñi |
| `e4b_writer.py`, `iso_builder.py` | [emu3bm](https://github.com/dagargo/emu3bm) — `struct emu3_sample` (E3S1-Sample-Header-Felder) und `emu3_set_fattrs()` (Ceiling-Division-`blks`-Formel für EMU3-Dateisystem) | GPL-3.0-or-later | David García Goñi |
| `krz_writer.py` | [KurzFiler](https://kurzfiler.sourceforge.io/) | GPL-2.0 | Marc Halbrügge |
| `exs24_parser.py` | [ConvertWithMoss](https://github.com/git-moss/ConvertWithMoss) — EXS24-Chunk-Layout; `TYPE_PARAMS`-Block, `EXS24Parameters`-IDs und `EXS24Detector`-Filter-/Hüllkurven-Umrechnungen (FILTER1 + ENV2) | LGPL-3.0 | Jürgen Moßgraber |
| `talsmpl_parser.py` | [ConvertWithMoss](https://github.com/git-moss/ConvertWithMoss) | LGPL-3.0 | Jürgen Moßgraber |
| `pgm_parser.py` | [ConvertWithMoss](https://github.com/git-moss/ConvertWithMoss) — `format/akai/mpc1000`, `format/akai/mpc2000` und `format/akai/mpc60`; MPC2000/XL gegen eine Akai-Werks-CD verifiziert, MPC60-`.PGM`/`.SND`-Container aus echtem Kit reverse-engineered | LGPL-3.0 | Jürgen Moßgraber |
| `mpc60_parser.py` | [ConvertWithMoss](https://github.com/git-moss/ConvertWithMoss) — `format/akai/mpc60` (MPC60-SET-Layout + 12-Bit-Entpackung); gegen den Referenz-Decoder *Akai MPC60 to WAV* verifiziert | LGPL-3.0 | Jürgen Moßgraber |
| `e4b_writer.py` | Reverse Engineering aus E4XT-Hardware-Bänken (JL AnalogBank, FltEnvTest, FLTTYPES-Reihe, AMPENV_SETME + AMP_DECAY_CAL Amp-Hüllkurven-/Decay-Bänke sowie die Chorus-Amount-`vpar[42]`-Lesungen/Sweep), kommerziellen EOS-CD-ROMs plus dem ProRec-/Rob-Papen-/Kirk-Hunter-Bank-Korpus zur Parameter-Analyse, `struct emu3_sample` aus [emu3bm](https://github.com/dagargo/emu3bm) (E3S1-Feldlayout) und [Phils E4-Format-Notizen](http://www.philizound.co.uk/freebies/software/emu-reorder/emu-reorder.html) | — | Originalcode |
| `iso_builder.py` | EMU3-Filesystem-Struktur aus [emu3fs](https://github.com/dagargo/emu3fs) (GPL-2.0-or-later), Referenz-Images verifiziert; `blks`-Ceiling-Formel aus `emu3_set_fattrs()` in [emu3bm](https://github.com/dagargo/emu3bm) | GPL-2.0-or-later | David García Goñi |

---

*E-mu, Emulator, EOS sind Marken von Creative Technology Ltd. ·
Kurzweil ist eine Marke von Young Chang Co. Ltd. ·
Akai MPC ist eine Marke von inMusic Brands Inc. ·
GigaStudio/GigaSampler sind Marken der TEAC Corporation. ·
Logic, EXS24, MainStage sind Marken von Apple Inc. ·
TAL-Sampler ist eine Marke von TAL Software GmbH. ·
SoundFont ist eine Marke von Creative Technology Ltd.*
