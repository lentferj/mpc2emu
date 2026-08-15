# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# Part of mpc2emu — https://github.com/jlentfer/mpc2emu
# Contributions: Jan Lentfer, with AI assistance (see README).
"""Reader for AKAI S1000/S3000 disk images — hard disk, CD-ROM and floppy.

The counterpart to `writers/akai_s3000_image.py`; see `docs/AKAI_S3000_FORMAT.md`
for the layout.  This is what makes an AKAI library disk readable without the
sampler: mount nothing, just walk the partition table, the volume directories
and the FAT chains.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from models.common import Bank
from parsers.akai_s3000_parser import (
    akai_to_str, parse_program_bytes, parse_sample_bytes,
    build_preset_from_program, AKAI_NAME_LEN,
)
from writers.akai_s3000_image import (
    HD_BLOCK, FL_BLOCK, PARTHEAD_BLKS, FLL_HEAD_BLKS, FLH_HEAD_BLKS,
    FLL_SIZE, FLH_SIZE, VOLDIR_FL_BLKS, VOLDIR_HD_BLKS, VOLDIR_ENTRIES,
    PART_MAX_BLOCKS,
    ROOTDIR_ENTRIES, MAX_PARTITIONS, CDINFO_BLK, CDINFO_BLKS,
    FAT_FILEEND, FAT_DIREND, FAT_SYS,
    _OFF_ROOTDIR, _OFF_FAT, _OFF_PARTTAB, _MAGICNUM, _MAGICVAL,
    FILE_TYPES, ftype_to_ext,
)

_SAMPLE_TYPES = {FILE_TYPES['S3'], FILE_TYPES['S1']}
_PROGRAM_TYPES = {FILE_TYPES['P3'], FILE_TYPES['P1']}

#: The file itself does not record which sampler generation wrote it -- byte
#: 0x00 is a block id and is identical on both.  The directory entry's type
#: byte is the only place it appears, so it is carried alongside the data.
_S3000_TYPES = {FILE_TYPES['S3'], FILE_TYPES['P3'], FILE_TYPES['M3']}

_FL_S3000_FLAG_TYPE = 0xFF

#: Volume directory shape by root-directory volume type: (blocks, entries).
#: An S1000 volume's directory is **one** block holding 126 entries, not the
#: S3000's two blocks holding 510.  Reading an S1000 volume with the S3000
#: shape walks off the end of the directory into whatever follows and invents
#: files out of it — a third-party S1000 library disc reported 45 files in a
#: volume that holds 21, the rest being noise with unrecognisable type bytes.
_VOLDIR_LAYOUT = {
    0x01: (1, 126),                     # S1000
    0x03: (VOLDIR_HD_BLKS, VOLDIR_ENTRIES),     # S3000
    0x07: (VOLDIR_HD_BLKS, VOLDIR_ENTRIES),     # CD3000
}
_VOLDIR_DEFAULT = (VOLDIR_HD_BLKS, VOLDIR_ENTRIES)


def _u16(d: bytes, o: int) -> int:
    return d[o] | (d[o + 1] << 8)


def _u24(d: bytes, o: int) -> int:
    return d[o] | (d[o + 1] << 8) | (d[o + 2] << 16)


class AkaiVolume:
    """One volume: a name and its files, each already lifted out of the FAT."""

    def __init__(self, name: str, partition: str, files: List[Tuple[str, int, bytes]]):
        self.name = name
        self.partition = partition          # 'A', 'B', … or 'FL' for a floppy
        #: (filename with extension, file-type byte, data)
        self.files = files

    def __repr__(self):
        return f"<AkaiVolume {self.partition}/{self.name} {len(self.files)} files>"

    def samples(self) -> Dict[str, Tuple[bytes, bool]]:
        """name -> (raw file, is_s3000)."""
        return {n.rsplit('.', 1)[0]: (d, t in _S3000_TYPES)
                for n, t, d in self.files if t in _SAMPLE_TYPES}

    def programs(self) -> List[Tuple[str, bytes, bool]]:
        """(filename, raw file, is_s3000) per program."""
        return [(n, d, t in _S3000_TYPES) for n, t, d in self.files
                if t in _PROGRAM_TYPES]


# ── detection ──────────────────────────────────────────────────────────────

def _has_parthead_magic(head: bytes) -> bool:
    """The 98 magic fields are what marks an AKAI harddisk partition.

    Checking several spread-out fields rather than one keeps this from firing
    on a run of zeros: field 0 *is* zero, so testing it alone would match any
    blank image.
    """
    if len(head) < 0xCA:
        return False
    return all(_u16(head, 2 + 2 * i) == (i * _MAGICVAL) & 0xFFFF
               for i in (1, 2, 3, 17, 50, 97))


def _is_akai_floppy(head: bytes, size: int) -> bool:
    """An S3000 floppy is flagged by file type 0xFF in the header's first slot."""
    if size not in (FLL_SIZE * FL_BLOCK, FLH_SIZE * FL_BLOCK):
        return False
    return len(head) > 16 and head[16] == _FL_S3000_FLAG_TYPE


def is_akai_image(path: str) -> bool:
    """True if `path` looks like an AKAI disk or floppy image.

    Used to disambiguate `.img` / `.hda`, which several formats share.
    """
    try:
        p = Path(path)
        size = p.stat().st_size
        with open(p, 'rb') as fh:
            head = fh.read(0x200)
    except OSError:
        return False
    return _has_parthead_magic(head) or _is_akai_floppy(head, size)


def akai_is_cd3000(path: str) -> bool:
    """True if the disc's volumes are typed CD3000 (`0x07`) rather than S3000.

    The type and the CD-ROM info block are independent: of eight real library
    discs, seven are CD3000-typed but only three carry the info block, and one
    is typed plain S3000. So neither alone identifies a CD.
    """
    try:
        with open(path, 'rb') as fh:
            head = fh.read(0x800)
    except OSError:
        return False
    if not _has_parthead_magic(head):
        return False
    return any(head[_OFF_ROOTDIR + 16 * i + 12] == 0x07
               for i in range(ROOTDIR_ENTRIES))


def akai_cd_label(path: str) -> Optional[str]:
    """The CD3000 disc label, or None if this is not an AKAI CD-ROM image.

    A CD-ROM partition is the one whose blocks right after the header are also
    marked reserved-for-system — that is where its file index lives.
    """
    try:
        with open(path, 'rb') as fh:
            head = fh.read((CDINFO_BLK + 1) * HD_BLOCK)
    except OSError:
        return None
    if not _has_parthead_magic(head):
        return None
    if not all(_u16(head, _OFF_FAT + 2 * b) == FAT_SYS
               for b in range(CDINFO_BLK, CDINFO_BLK + CDINFO_BLKS)):
        return None
    o = CDINFO_BLK * HD_BLOCK + 2 + 2 * ROOTDIR_ENTRIES
    if len(head) < o + AKAI_NAME_LEN:
        return None
    return akai_to_str(head[o:o + AKAI_NAME_LEN]).rstrip()


# ── FAT walking ────────────────────────────────────────────────────────────

def _chain(fat, start: int, limit: int, end_codes) -> List[int]:
    """Follow a FAT chain from `start`, refusing to loop forever.

    A damaged image can point a block at itself or back into the chain; a
    library disk that has sat in a loft for thirty years is exactly where that
    shows up, so the walk is bounded and visited blocks are tracked.
    """
    out: List[int] = []
    seen = set()
    b = start
    while 0 <= b < limit and len(out) < limit:
        if b in seen:
            raise ValueError(f"FAT chain loops at block 0x{b:04x}")
        seen.add(b)
        out.append(b)
        nxt = fat[b]
        if nxt in end_codes:
            return out
        if nxt == FAT_SYS or nxt == 0:
            # Reserved or free: the chain ran off its end without a terminator.
            return out
        b = nxt
    return out


def _read_blocks(data: bytes, base: int, blocks, blocksize: int) -> bytes:
    out = bytearray()
    for b in blocks:
        o = base + b * blocksize
        out += data[o:o + blocksize]
    return bytes(out)


def _volume_files(data: bytes, base: int, fat, dirbytes: bytes, blocksize: int,
                  nblocks: int,
                  max_entries: int = VOLDIR_ENTRIES,
                  short: Optional[list] = None,
                  unknown: Optional[list] = None) -> List[Tuple[str, int, bytes]]:
    """Files of one volume.  Entries whose data runs past the end of the image
    are appended to `short` rather than returned — see `_truncation_warning`."""
    files = []
    for i in range(min(max_entries, len(dirbytes) // 24)):
        e = dirbytes[24 * i:24 * i + 24]
        ftype = e[16]
        if ftype == 0x00 or ftype == _FL_S3000_FLAG_TYPE:
            # Type 0x00 is how an EMPTY slot reads, which is why it is skipped.
            #
            # But it may not be ONLY that. s3ked saw an entry of this type on
            # a disc 2026-08-14: 162 bytes, tail bytes `1e 04` where every
            # program and sample carries `1e 09`.
            #
            # **Whether it is a real record is OPEN, and the first report that
            # it was has been withdrawn.** They have one instance and it was
            # the LAST entry in its directory, index 54 of 55 -- exactly where
            # an off-by-one in a reader would put a phantom. Their directory
            # walk stops on a heuristic (extension field not reading as spaces,
            # or a record repeating an earlier one) rather than on a length, so
            # "it satisfies both stop conditions, therefore it is real" is
            # circular: it is real by the rule that decides where the list
            # ends, and that rule is what would be wrong.
            #
            # SETTLED 2026-08-14 (VinSamLib, 21 discs, 1843 volumes, 441 498
            # directory slots): there is no such record type. 32 entries carry
            # the `1e 04` tail; 31 sit past the last real entry and the single
            # mid-directory one is a same-name same-size shadow of the program
            # in the next slot.
            #
            # And the reason is the useful part. **The type byte is the one
            # field the authoring tools reliably clear; the rest of the record
            # is left stale.** Past the first truly empty slot the type byte is
            # zero in 375 623 of 375 623 slots, while sizes there run to
            # 0xFFFFFF and tails take hundreds of values that look like x86
            # code. So `1e 04` is not a record signature -- it is a stale tail
            # in a slot whose type byte was cleared, which is exactly why it
            # never appears beside a live type.
            #
            # OUR walk cannot produce that artefact -- it is length-bounded,
            # reading a fixed entry count from a fixed-size directory region
            # and never guessing where the list ends. So a 0x00-with-size that
            # this reader reports is worth something, which is the reason to
            # report it rather than to decode it.
            #
            # Keep the report, even though the record type turned out not to
            # exist: what it now detects is a slot the authoring tool did NOT
            # clear the way every tool in a 21-disc corpus did, and that is
            # worth a line either way. See TODO for why this reader has never
            # emitted a phantom from one, and why that is luck about the tools
            # rather than a property of the format.
            #
            # We keep skipping it, deliberately: we have no disc carrying one
            # to test against, reading a record of unknown layout is how a
            # parser invents data, and it may yet turn out not to exist. But an
            # empty slot has size 0 and this does not, so the two ARE
            # separable -- and dropping a possibly-real entry without saying so
            # is the failure the comment below is about. Report it.
            #
            # Reported through its OWN channel, not `short`. `short` means
            # "this file's data runs past the end of the image", i.e. a bad
            # copy, and an unknown record type is not that. Filing it there
            # would surface a real finding under a warning that says something
            # else -- which is the failure this project has spent the week
            # cataloguing in other people's code.
            if (unknown is not None and ftype == 0x00
                    and _u24(e, 17) > 0
                    and akai_to_str(e[0:AKAI_NAME_LEN]).strip()):
                unknown.append(f"{akai_to_str(e[0:AKAI_NAME_LEN]).rstrip()} "
                               f"(directory type 0x00, {_u24(e, 17)} bytes)")
            continue
        name = akai_to_str(e[0:AKAI_NAME_LEN]).rstrip()
        size = _u24(e, 17)
        start = _u16(e, 20)
        if size == 0 or start >= nblocks:
            continue
        try:
            blocks = _chain(fat, start, nblocks, (FAT_FILEEND,))
        except ValueError:
            continue
        raw = _read_blocks(data, base, blocks, blocksize)[:size]
        if len(raw) < size:
            # The image stops before this file does. Returning the fragment
            # would be worse than dropping it, but dropping it silently is how
            # a half-downloaded disc converts to a plausible-looking subset.
            if short is not None:
                short.append(f"{name}.{ftype_to_ext(ftype)}")
            continue
        files.append((f"{name}.{ftype_to_ext(ftype)}", ftype, raw))
    return files


# ── image walking ──────────────────────────────────────────────────────────

def read_akai_image(path: str) -> List[AkaiVolume]:
    """Read every volume on an AKAI hard-disk, CD-ROM or floppy image."""
    data = Path(path).read_bytes()
    if _is_akai_floppy(data[:0x200], len(data)):
        return [_read_floppy(data)]
    if not _has_parthead_magic(data[:0x200]):
        raise ValueError(
            f"{Path(path).name} is not an AKAI disk image — the partition "
            f"header magic is missing (and it is not a 800 KB / 1.6 MB AKAI "
            f"floppy).")
    return _read_harddisk(data)


def _truncation_warning(data: bytes, sizes, short,
                        partitions_read: Optional[int] = None) -> Optional[str]:
    """Describe an image that is smaller than its own partition table claims.

    Real discs are a few MB *larger* than the AKAI area — lead-out and padding
    — so only the other direction means a bad copy.

    `partitions_read` matters more than the percentage.  A partition that
    starts past the end of the file is dropped before any directory is read,
    so **none of its files reach `short`** — on one 61%-present disc the byte
    figure was the only signal that three whole partitions (a third of the
    library) were missing, while `short` stayed empty and every volume that
    did parse was perfect.  Read on its own, "61% present" invites the reading
    that the ripper merely omitted empty tail space.
    """
    declared = sum(sizes)
    actual = len(data) // HD_BLOCK
    missing_parts = (len(sizes) - partitions_read
                     if partitions_read is not None else 0)
    if actual >= declared and not short and missing_parts <= 0:
        return None
    parts = []
    if actual < declared:
        parts.append(
            f"image is {actual * HD_BLOCK / 1048576:.0f} MB but its partition "
            f"table declares {declared * HD_BLOCK / 1048576:.0f} MB "
            f"({100.0 * actual / declared:.0f}% present) — it looks like an "
            f"incomplete copy")
    if missing_parts > 0:
        parts.append(
            f"{missing_parts} of {len(sizes)} partitions start past the end of "
            f"the file and were not read at all — their volumes are missing "
            f"from this listing entirely, not merely empty")
    if short:
        parts.append(f"{len(short)} file(s) run past the end and were skipped "
                     f"(e.g. {', '.join(short[:3])})")
    return "  [WARN] " + "; ".join(parts)


#: Directory records this reader recognises as real but cannot decode.
#: Module-level so both media paths report through one list; see the note in
#: _volume_files for what is actually in it.
_unknown_records: list = []


def _read_harddisk(data: bytes) -> List[AkaiVolume]:
    # The partition table lives in the first partition only; its entries give
    # each partition's size in blocks, and partitions are laid end to end.
    # A corrupt count must not walk off the end of the table into the tag
    # names, so it is clamped to the number of entries that exist.
    partnum = min(data[_OFF_PARTTAB + 0x100], MAX_PARTITIONS)
    sizes = [_u16(data, _OFF_PARTTAB + 0x102 + 2 * i) for i in range(partnum)]
    if not sizes:
        sizes = [_u16(data, 0)]             # single partition, no table

    vols: List[AkaiVolume] = []
    short: List[str] = []
    start = 0
    partitions_read = 0
    for pi, psize in enumerate(sizes):
        if psize == 0 or start * HD_BLOCK >= len(data):
            break                           # table over-declares what is there
        partitions_read += 1
        base = start * HD_BLOCK
        start += psize
        head = data[base:base + PARTHEAD_BLKS * HD_BLOCK]
        if not _has_parthead_magic(head):
            continue                        # not a sampler partition (DD, or junk)
        nblocks = min(psize, _u16(head, 0) or psize, PART_MAX_BLOCKS)
        fat = [_u16(head, _OFF_FAT + 2 * i) for i in range(PART_MAX_BLOCKS)]
        letter = chr(ord('A') + pi)

        for vi in range(ROOTDIR_ENTRIES):
            o = _OFF_ROOTDIR + 16 * vi
            if head[o + 12] == 0x00:        # inactive
                continue
            vstart = _u16(head, o + 14)
            if vstart >= nblocks:
                continue
            name = akai_to_str(head[o:o + AKAI_NAME_LEN]).rstrip()
            dir_blks, max_entries = _VOLDIR_LAYOUT.get(head[o + 12], _VOLDIR_DEFAULT)
            try:
                dirblocks = _chain(fat, vstart, nblocks, (FAT_DIREND, FAT_FILEEND))
            except ValueError:
                continue
            # The chain says where the directory lives; the volume type says
            # how big it is.  Trusting the chain alone over-reads an S1000
            # volume, whose end-of-directory FAT code is the same value the
            # S3000 uses for "reserved".
            dirbytes = _read_blocks(data, base, dirblocks[:dir_blks], HD_BLOCK)
            files = _volume_files(data, base, fat, dirbytes, HD_BLOCK, nblocks,
                                  max_entries, short,
                                  unknown=_unknown_records)
            vols.append(AkaiVolume(name, letter, files))

    warn = _truncation_warning(data, sizes, short, partitions_read)
    if warn:
        print(warn)
    for _u in _unknown_records:
        print(f"  [NOTE] skipped an unrecognised directory record: {_u}")
    return vols


def _read_floppy(data: bytes) -> AkaiVolume:
    hd = len(data) == FLH_SIZE * FL_BLOCK
    total = FLH_SIZE if hd else FLL_SIZE
    head_blks = FLH_HEAD_BLKS if hd else FLL_HEAD_BLKS

    fat_at = 64 * 24
    fat = [_u16(data, fat_at + 2 * i) for i in range(total)]
    label_at = fat_at + total * 2
    name = akai_to_str(data[label_at:label_at + AKAI_NAME_LEN]).rstrip()

    dirbytes = data[head_blks * FL_BLOCK:
                    (head_blks + VOLDIR_FL_BLKS) * FL_BLOCK]
    files = _volume_files(data, 0, fat, dirbytes, FL_BLOCK, total,
                          unknown=_unknown_records)
    return AkaiVolume(name or 'FLOPPY', 'FL', files)


# ── Bank conversion ────────────────────────────────────────────────────────

def parse_akai_image(path: str, wav_dir: Optional[str] = None, **kw) -> Bank:
    """Read an AKAI disk image into a single Bank, one preset per program.

    Every volume on the disk contributes its programs; a volume's samples are
    resolved within that volume, which is how the sampler resolves them too —
    two volumes may each hold a different "BASS" and neither should win.
    """
    from parsers.xpm_parser import _safe_name

    p = Path(path)
    vols = read_akai_image(str(p))
    _unknown_records.clear()
    print(f"Parsing AKAI disk image: {p.name}")

    bank = Bank(name=_safe_name(p.stem))
    n_prog = 0
    # Every sample name anywhere on the disc, so an unresolved zone can be
    # told apart from a zone whose sample is simply on another volume.
    disc_samples = {n for vol in vols for n in vol.samples()}
    unresolved: set = set()
    for vol in vols:
        progs = vol.programs()
        smap = vol.samples()
        if not progs:
            if smap:
                print(f"  Volume {vol.partition}/{vol.name}: "
                      f"{len(smap)} sample(s), no program")
            continue
        print(f"  Volume {vol.partition}/{vol.name}: {len(progs)} program(s), "
              f"{len(smap)} sample(s)")

        def lookup(name, _smap=smap):
            return _smap.get(name.strip().upper()) or _smap.get(name.strip())

        def load(name, _smap=smap):
            hit = lookup(name)
            return None if hit is None else hit[0]

        # One cache per volume: names are only unique within a volume.
        cache: dict = {}
        taken = {s.name for s in bank.samples}
        for fname, raw, is_s3000 in progs:
            prog = parse_program_bytes(raw, fallback_name=fname.rsplit('.', 1)[0],
                                       s3000=is_s3000)
            if prog is None:
                print(f"    [WARN] unreadable program: {fname}")
                continue
            preset = build_preset_from_program(
                prog, load, bank,
                fallback_name=fname.rsplit('.', 1)[0],
                cache=cache, taken=taken, quiet=True,
                missing_out=unresolved)
            if preset is None:
                print(f"    [WARN] {fname}: no keygroup resolved to a sample")
                continue
            preset.program_number = n_prog
            bank.presets.append(preset)
            n_prog += 1
            print(f"    Preset '{preset.name}': {len(preset.voices)} voice(s)")

    if not bank.presets:
        # Samples with no program still carry audio worth converting.
        loose = [(v, n, d) for v in vols for n, t, d in v.files
                 if t in _SAMPLE_TYPES]
        raise ValueError(
            f"{p.name} holds no readable AKAI program"
            + (f" ({len(loose)} sample(s) found — convert those individually)"
               if loose else "") + ".")

    print(f"  {len(bank.presets)} preset(s), {len(bank.samples)} sample(s)")
    if unresolved:
        # A zone whose sample is not on its own volume is dropped -- silently,
        # before this. The sampler resolves within the loaded volume too, so
        # dropping is right; not saying so is not. Splitting the count matters
        # because the two halves have different answers: a sample sitting on
        # another volume of THIS disc is recoverable by loading that volume,
        # while one that is nowhere on the disc needs another disc of the set.
        here = sorted(n for n in unresolved if n in disc_samples)
        gone = sorted(n for n in unresolved if n not in disc_samples)
        parts = []
        if here:
            parts.append(f"{len(here)} on another volume of this disc "
                         f"(e.g. {', '.join(here[:3])})")
        if gone:
            parts.append(f"{len(gone)} not on this disc at all "
                         f"(e.g. {', '.join(gone[:3])})")
        print(f"  [WARN] {len(unresolved)} sample name(s) referenced by a "
              f"keygroup could not be resolved on their own volume, and those "
              f"zones were dropped: " + "; ".join(parts))
    return bank
