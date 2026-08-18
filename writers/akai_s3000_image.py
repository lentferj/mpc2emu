# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# Part of mpc2emu — https://github.com/lentferj/mpc2emu
# Contributions: Jan Lentfer, with AI assistance (see README).
"""AKAI S1000/S3000 disk-image writer — hard disk (SCSI/ZuluSCSI) and floppy.

Builds media the sampler mounts directly, rather than loose files that still
need a third-party tool to be placed on a disk.

The format is not vendor-documented; see `docs/AKAI_S3000_FORMAT.md` for the
sources and for what is and is not verified.  Layout summary, all numbers
little-endian:

    harddisk block   0x2000 (8 KB)      floppy block   0x0400 (1 KB)

    partition header       3 blocks     at partition-relative block 0
      0x0000  size in blocks
      0x0002  98 magic fields, value i*3333 & 0xffff
      0x00C6  checksum: size + sum of those fields
      0x00CA  root directory, 100 volume entries of 16 bytes
      0x070A  FAT, 0x1E00 entries of 2 bytes
      0x4400  partition table (first partition on the disk only)
      0x4600  "TAGS" + 26 tag names of 12 bytes

    volume directory       2 blocks     510 file entries of 24 bytes,
                                        then 48 bytes of volume parameters

A file occupies ceil(size / blocksize) blocks chained through the FAT.
"""

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from parsers.akai_s3000_parser import AKAI_NAME_LEN, akai_to_str, str_to_akai
from writers.atomic import atomic_write

# ── block geometry ─────────────────────────────────────────────────────────
HD_BLOCK = 0x2000                   # 8 KB
FL_BLOCK = 0x0400                   # 1 KB

PARTHEAD_BLKS = 3
VOLDIR_HD_BLKS = 2                  # S3000 harddisk volume directory
VOLDIR_FL_BLKS = 12                 # S3000 floppy volume directory
FLL_HEAD_BLKS = 4                   # low-density floppy header
FLH_HEAD_BLKS = 5                   # high-density floppy header

FLL_SIZE = 0x0320                   # 800 blocks = 800 KB
FLH_SIZE = 0x0640                   # 1600 blocks = 1.6 MB

# ── capacity limits ────────────────────────────────────────────────────────
#: 60 MB. **The FORMAT screen's DEFAULT, not an established maximum** — the
#: field is editable, with a "max:" shown beside it that we have not read.
#: VinSamLib raised this 2026-08-12 and they are right to: treating a default
#: as a ceiling is the same move as treating a corpus maximum as a format
#: limit, which is what the 229/191 case turned out to be.
#:
#: Using it as a cap is nonetheless SAFE, and that is why it stays: it makes
#: more and smaller partitions than strictly needed, and a sampler that
#: accepts 120 MB partitions will still read 60 MB ones. If the true maximum
#: is ever read off the panel, this becomes an optimisation rather than a
#: correction. What was wrong was only the word "cap" in the old comment.
PART_MAX_BLOCKS = 0x1E00
HD_MAX_BLOCKS = 0xFFFF              # block numbers are 16-bit → ~512 MB
MAX_PARTITIONS = 18
ROOTDIR_ENTRIES = 100               # volumes per partition
VOLDIR_ENTRIES = 510                # files per volume

# ── on-disk offsets within the partition header ────────────────────────────
_OFF_MAGIC = 0x0002
_OFF_CHKSUM = 0x00C6
_OFF_ROOTDIR = 0x00CA
_OFF_FAT = 0x070A
_OFF_PARTTAB = 0x4400
_OFF_TAGS = 0x4600

_MAGICNUM, _MAGICVAL = 98, 3333             # partition header
_PARTTAB_MAGICNUM, _PARTTAB_MAGICVAL = 128, 9999

# ── FAT codes ──────────────────────────────────────────────────────────────
FAT_FREE = 0x0000
FAT_SYS = 0x4000                    # reserved for the system (headers)
FAT_DIREND = 0x8000                 # end of a volume-directory chain (S3000)
FAT_FILEEND = 0xC000                # end of a file chain

# ── directory-entry values ─────────────────────────────────────────────────
VOL_TYPE_INACT = 0x00
VOL_TYPE_S3000 = 0x03
VOL_TYPE_CD3000 = 0x07              # CD3000 CD-ROM; the sampler treats it as S3000
OSVER_S3000 = 0x1100                # "17.00", the S3000 maximum

#: The file type is a letter identifying the kind, in one of three ranges by
#: sampler generation: `A`-`Z` for the S900, `a`-`z` for the S1000, and the
#: S1000 letters with bit 7 set for the S3000.  A sample is `s`, so an S3000
#: one is 0xF3; a program is `p`, so 0xF0.
_S900_RANGE = (ord('A'), ord('Z'))
_S1000_RANGE = (ord('a'), ord('z'))
_S3000_RANGE = (ord('a') | 0x80, ord('z') | 0x80)

#: Two S3000 types whose extension does not follow the rule.
_FTYPE_CDSETUP = ord('T')                       # CD3000 CD-ROM setup  -> .CD
_FTYPE_CDSAMPLE = ord('h') | 0x80               # CD3000 sample params -> .s+


def ftype_to_ext(ftype: int) -> str:
    """The extension for a file-type byte.

    WHAT THE BYTE ACTUALLY IS, established with s3ked 2026-08-18 by reading
    directories the S3000XL wrote itself: **it is an ASCII letter naming the
    file, and bit 7 marks the S3000 generation.** Masked to 7 bits it reads
    plainly:

        'p' program   's' sample   'm' multi
        't' take list 'x' effects  'd' drum inputs

    That is why this is a RULE over ranges rather than a table of known types.
    A table is a list of what somebody has seen; the ranges are a model of what
    the format is, so an unseen letter still yields an extension instead of
    vanishing, and the fix is never to keep adding rows.

    Only `.S1`/`.P1` carry the generation digit in the S1000 range — an FX file
    is `.X`, not `.X1`. Reading a real library disc turns up `.X`, `.D`, `.Q`
    and `.M3` alongside the samples and programs, and dropping their extension
    would lose the one thing that says what they are. That is how this shape was
    arrived at: from the reading side, where the problem is visible.

    The multi is high-bit set — `0xed`, confirmed raw on two machine-written
    directories (the flash BOOT SYSTEM# volume and an HD volume the sampler
    saved). It is NOT `0x6d`: program, sample and multi arrive with bit 7 set,
    while take list, effects and drum inputs do not.
    """
    if ftype == _FTYPE_CDSETUP:
        return 'CD'
    if ftype == _FTYPE_CDSAMPLE:
        return 's+'
    if _S900_RANGE[0] <= ftype <= _S900_RANGE[1]:
        return f"{chr(ord('A') + ftype - _S900_RANGE[0])}9"
    if _S1000_RANGE[0] <= ftype <= _S1000_RANGE[1]:
        letter = chr(ord('A') + ftype - _S1000_RANGE[0])
        return f"{letter}1" if ftype in (ord('p'), ord('s')) else letter
    if _S3000_RANGE[0] <= ftype <= _S3000_RANGE[1]:
        return f"{chr(ord('A') + ftype - _S3000_RANGE[0])}3"
    return f"x{ftype:02x}"


def ext_to_ftype(ext: str) -> Optional[int]:
    """The file-type byte for an extension, or None if it is not an AKAI one."""
    ext = ext.upper() if ext.lower() != 's+' else ext.lower()
    for ft in (list(range(*_S900_RANGE)) + [_S900_RANGE[1]]
               + list(range(*_S1000_RANGE)) + [_S1000_RANGE[1]]
               + list(range(*_S3000_RANGE)) + [_S3000_RANGE[1]]
               + [_FTYPE_CDSETUP, _FTYPE_CDSAMPLE]):
        if ftype_to_ext(ft).upper() == ext.upper():
            return ft
    return None


#: The types this project writes, kept as names for readability.
FILE_TYPES = {
    'S3': ord('s') | 0x80,          # S3000 sample
    'P3': ord('p') | 0x80,          # S3000 program
    'M3': ord('m') | 0x80,          # S3000 multi
    'S1': ord('s'),                 # S1000 sample
    'P1': ord('p'),                 # S1000 program
}

#: Volume parameters as the sampler writes them for a fresh S3000 volume.
#: The individual fields are undocumented in every available source; these are
#: the observed defaults and are reproduced verbatim rather than interpreted.
_VOLPARAM_S3000 = bytes([0x00, 0x01, 0x01, 0x00, 0x00, 0x00,
                         0x32, 0x09, 0x0C, 0xFF] + [0x00] * 38)
_VOLPARAM_LEN = 0x30

#: Floor for auto-sizing a hard-disk image, in MB.
_AUTO_MIN_MB = 8

# ── CD-ROM (CD3000) ────────────────────────────────────────────────────────
#: The CD-ROM info sits in the 3 blocks right after the partition header and
#: indexes every file in the partition, so the sampler can browse the disc
#: without reading each volume directory in turn.
CDINFO_BLK = PARTHEAD_BLKS
CDINFO_BLKS = 3
_CDINFO_HEAD_LEN = 2 + 2 * ROOTDIR_ENTRIES + AKAI_NAME_LEN      # 214
#: How many file entries fit behind that header.
CDINFO_MAX_FILES = (CDINFO_BLKS * HD_BLOCK - _CDINFO_HEAD_LEN) // 24
CDINFO_DEFAULT_LABEL = 'CDROM'

#: Marker entry that identifies a floppy as carrying an S3000 volume
#: directory: file type 0xFF (never a valid type) in the header's first entry.
_FL_S3000_FLAG_TYPE = 0xFF


class AkaiImageError(Exception):
    """Raised when the requested content cannot be laid out on the media."""


# ── small helpers ──────────────────────────────────────────────────────────

def _u16(buf: bytearray, off: int, v: int) -> None:
    buf[off] = v & 0xFF
    buf[off + 1] = (v >> 8) & 0xFF


def _u24(buf: bytearray, off: int, v: int) -> None:
    buf[off] = v & 0xFF
    buf[off + 1] = (v >> 8) & 0xFF
    buf[off + 2] = (v >> 16) & 0xFF


def _blocks(nbytes: int, block: int) -> int:
    return (nbytes + block - 1) // block


def split_akai_name(filename: str) -> Tuple[str, int]:
    """Split ``NAME.S3`` into its 12-character name and its file-type byte.

    The extension is not decoration: the sampler stores only the type byte,
    and it is derived from the extension.  A file with no recognised
    extension cannot be placed on the media at all.
    """
    stem, _, ext = filename.rpartition('.')
    if not stem:
        stem, ext = filename, ''
    ftype = ext_to_ftype(ext) if ext else None
    if ftype is None:
        raise AkaiImageError(
            f"{filename}: unknown AKAI file type '.{ext}' — a sample is .S3 "
            f"and a program .P3 (.S1/.P1 for S1000)")
    return stem.upper()[:AKAI_NAME_LEN], ftype


def akai_volume_name(name: str) -> str:
    """Normalise a name to what the sampler will actually display.

    The AKAI alphabet has no lower case and no underscore, so a name is
    round-tripped through the encoding rather than reported as given — an
    "EMU_BANK_01" that shows up as "EMU BANK 01" on the front panel is
    confusing to chase.
    """
    return akai_to_str(str_to_akai(name)).rstrip() or 'VOLUME'


def _file_entry(name: str, ftype: int, size: int, start: int,
                osver: int = OSVER_S3000) -> bytes:
    """One 24-byte volume-directory entry."""
    e = bytearray(24)
    e[0:AKAI_NAME_LEN] = str_to_akai(name)
    # e[12:16] are the four tag slots — 0 means untagged.
    e[16] = ftype
    _u24(e, 17, size)
    _u16(e, 20, start)
    _u16(e, 22, osver)
    return bytes(e)


# ── hard disk ──────────────────────────────────────────────────────────────

def _partition_header(part_blocks: int, volumes: Sequence[Tuple[str, int]],
                      fat: Sequence[int], parttab: Optional[Sequence[int]],
                      vol_type: int = VOL_TYPE_S3000) -> bytes:
    """Build the 3-block partition header.

    ``volumes`` is (name, start block) per active volume; ``parttab`` is the
    list of partition sizes, and is written only for the first partition on
    the disk — that is where the sampler looks for it.
    """
    h = bytearray(PARTHEAD_BLKS * HD_BLOCK)

    _u16(h, 0x0000, part_blocks)

    # The magic fields are what marks this as an AKAI harddisk partition; the
    # checksum covers the partition size and those fields, nothing else.
    chk = part_blocks
    for i in range(_MAGICNUM):
        m = (i * _MAGICVAL) & 0xFFFF
        _u16(h, _OFF_MAGIC + 2 * i, m)
        chk += m
    chk &= 0xFFFFFFFF
    h[_OFF_CHKSUM:_OFF_CHKSUM + 4] = chk.to_bytes(4, 'little')

    # Root directory.  Unused slots keep their default names and are marked
    # inactive; the sampler shows them as empty volumes.
    for i in range(ROOTDIR_ENTRIES):
        o = _OFF_ROOTDIR + 16 * i
        if i < len(volumes):
            name, start = volumes[i]
            h[o:o + AKAI_NAME_LEN] = str_to_akai(name)
            h[o + 12] = vol_type
            h[o + 13] = 0                       # load number: off
            _u16(h, o + 14, start)
        else:
            h[o:o + AKAI_NAME_LEN] = str_to_akai(f"VOLUME {i + 1:03d}")
            h[o + 12] = VOL_TYPE_INACT

    for i, code in enumerate(fat):
        _u16(h, _OFF_FAT + 2 * i, code)

    if parttab is not None:
        for i in range(_PARTTAB_MAGICNUM):
            _u16(h, _OFF_PARTTAB + 2 * i, (i * _PARTTAB_MAGICVAL) & 0xFFFF)
        h[_OFF_PARTTAB + 0x100] = len(parttab) & 0xFF       # partition count
        h[_OFF_PARTTAB + 0x101] = 0                         # no DD partitions
        for i, siz in enumerate(parttab):
            _u16(h, _OFF_PARTTAB + 0x102 + 2 * i, siz)
        # The total is appended after the last partition entry.
        _u16(h, _OFF_PARTTAB + 0x102 + 2 * len(parttab), sum(parttab) & 0xFFFF)

    h[_OFF_TAGS:_OFF_TAGS + 4] = b'TAGS'
    for i in range(26):
        o = _OFF_TAGS + 4 + AKAI_NAME_LEN * i
        h[o:o + AKAI_NAME_LEN] = str_to_akai(f"TAG {chr(ord('A') + i)}")

    return bytes(h)


def _volume_directory(entries: Sequence[bytes], blks: int, block: int,
                      volparam: bool = True) -> bytes:
    """Build a volume directory: the file entries, then the volume parameters.

    On a floppy the parameters live in the header label instead, and the space
    after the entries stays zero — pass ``volparam=False``.
    """
    d = bytearray(blks * block)
    for i, e in enumerate(entries):
        d[24 * i:24 * i + 24] = e
    if volparam:
        o = 24 * VOLDIR_ENTRIES
        d[o:o + _VOLPARAM_LEN] = _VOLPARAM_S3000
    return bytes(d)


def _cdinfo(entries_per_volume: Sequence[Sequence[bytes]], label: str) -> bytes:
    """Build the 3-block CD-ROM info for one partition.

    It is an index, not storage: the file count, the byte length of each
    volume's directory entries, the disc label, and then a flat copy of every
    file entry in volume order.  The files themselves live where the FAT says.
    """
    b = bytearray(CDINFO_BLKS * HD_BLOCK)
    flat = bytearray()
    n = 0
    for vi, entries in enumerate(entries_per_volume):
        take = entries[:max(0, CDINFO_MAX_FILES - n)]
        for e in take:
            flat += e
        n += len(take)
        if vi < ROOTDIR_ENTRIES:
            _u16(b, 2 + 2 * vi, len(take) * 24)
    _u16(b, 0, n)
    o = 2 + 2 * ROOTDIR_ENTRIES
    b[o:o + AKAI_NAME_LEN] = str_to_akai(label)
    b[_CDINFO_HEAD_LEN:_CDINFO_HEAD_LEN + len(flat)] = flat
    return bytes(b)


def _plan_partitions(volumes, part_blocks, size_limited=False,
                     sys_blocks=PARTHEAD_BLKS):
    """Assign volumes to partitions, filling each before opening the next.

    Returns a list of per-partition volume lists.  A volume is never split
    across a partition boundary: the sampler addresses a volume's blocks
    relative to its own partition, so a split volume could not be described.
    """
    parts: List[list] = [[]]
    used = sys_blocks
    for name, files in volumes:
        need = VOLDIR_HD_BLKS + sum(_blocks(len(d), HD_BLOCK) for _n, d in files)
        if need > part_blocks - sys_blocks:
            raise AkaiImageError(
                f"volume '{name}' needs {need} blocks "
                f"({need * HD_BLOCK / 1048576:.1f} MB) but a partition holds at "
                f"most {part_blocks - sys_blocks} "
                f"({(part_blocks - sys_blocks) * HD_BLOCK / 1048576:.1f} MB) — "
                + ("raise --hda-size" if size_limited
                   else "split it into several volumes"))
        if used + need > part_blocks or len(parts[-1]) >= ROOTDIR_ENTRIES:
            parts.append([])
            used = sys_blocks
        parts[-1].append((name, files))
        used += need
    return [p for p in parts if p] or [[]]


def _plan_given(volumes, groups, part_blocks, size_limited=False,
                sys_blocks=PARTHEAD_BLKS):
    """Use a caller's partition grouping verbatim, after checking it fits.

    `groups` is a sequence of index sequences into `volumes`:
    ``[[0, 1], [2]]`` puts the first two volumes in partition A and the third
    in partition B.

    A converter has no view about which partition a volume lands in -- the
    grouping falls out of what is being converted, and _plan_partitions' fill
    rule is right for that. A LIBRARIAN's user does have a view: keep this
    library together, leave A short so it can be appended to later, and
    stepping to partition B is a different gesture on the front panel from
    stepping to volume 7 of A. Requested by VinSamLib 2026-08-16 for exactly
    that.

    Validated against the same limits the planner enforces, and refusing for
    the same reasons, so a hand-made grouping cannot produce an image the
    automatic one would have refused to build.
    """
    seen: set = set()
    plan: List[list] = []
    for gi, group in enumerate(groups):
        part: list = []
        used = sys_blocks
        for idx in group:
            if not 0 <= idx < len(volumes):
                raise AkaiImageError(
                    f"partition {chr(ord('A') + gi)} names volume index {idx}, "
                    f"but there are {len(volumes)} volume(s)")
            if idx in seen:
                raise AkaiImageError(
                    f"volume index {idx} ('{volumes[idx][0]}') appears in more "
                    f"than one partition")
            seen.add(idx)
            name, files = volumes[idx]
            need = VOLDIR_HD_BLKS + sum(_blocks(len(d), HD_BLOCK) for _n, d in files)
            if need > part_blocks - sys_blocks:
                raise AkaiImageError(
                    f"volume '{name}' needs {need} blocks "
                    f"({need * HD_BLOCK / 1048576:.1f} MB) but a partition holds "
                    f"at most {part_blocks - sys_blocks} "
                    f"({(part_blocks - sys_blocks) * HD_BLOCK / 1048576:.1f} MB)"
                    + (" — raise --hda-size" if size_limited else ""))
            if used + need > part_blocks:
                raise AkaiImageError(
                    f"partition {chr(ord('A') + gi)} was given "
                    f"{len(group)} volume(s) needing more than the "
                    f"{(part_blocks - sys_blocks) * HD_BLOCK / 1048576:.1f} MB a "
                    f"partition holds; '{name}' does not fit. Split the group.")
            used += need
            part.append((name, files))
        plan.append(part)
    missing = [i for i in range(len(volumes)) if i not in seen]
    if missing:
        raise AkaiImageError(
            f"{len(missing)} volume(s) are in no partition: "
            + ", ".join(volumes[i][0] for i in missing[:4])
            + (" ..." if len(missing) > 4 else ""))
    return [p for p in plan if p] or [[]]


def build_akai_hd_image(volumes: Sequence[Tuple[str, Sequence[Tuple[str, bytes]]]],
                        output_path: str,
                        size_mb: Optional[int] = None,
                        part_mb: int = 60,
                        cdrom: bool = False,
                        cd_label: Optional[str] = None,
                        partitions: Optional[Sequence[Sequence[int]]] = None) -> Dict:
    """Write an AKAI S3000 SCSI hard-disk or CD3000 CD-ROM image.

    ``volumes`` is ``[(volume_name, [(filename, data), ...]), ...]`` where each
    filename carries its AKAI extension (``KICK.S3``, ``DRUMS.P3``).

    ``size_mb`` sizes the whole disk; the default is just large enough for the
    content.  ``part_mb`` sets the partition size — 60 MB is the sampler's
    maximum and the usual choice, since a smaller one only means more
    partitions to step through on the front panel.

    ``partitions`` overrides the automatic layout with an explicit grouping:
    ``[[0, 1], [2]]`` puts the first two volumes in partition A and the third
    in B.  Left as ``None`` the volumes are packed by filling each partition
    before opening the next, which is right for a converter, where the grouping
    simply falls out of what is being converted.  A librarian's user has a view
    about it — keep this library together, leave A short so it can be appended
    to later — and the front panel agrees with them: stepping to partition B is
    a different gesture from stepping to volume 7 of A.

    A supplied grouping is validated against the same limits the planner
    enforces and refused for the same reasons, plus two of its own: a volume
    named twice, and a volume named in no partition.  Silently dropping a
    volume is the one outcome this must not have.

    With ``cdrom``, three blocks after each partition header are reserved for
    the CD-ROM info index and volumes are typed CD3000.  The result is *not*
    ISO 9660 — it is the AKAI partition format written raw, which is what a
    CD3000-format disc actually is, so it is burned as a plain data image.

    Returns a summary dict (``partitions``, ``blocks``, ``bytes``, ``volumes``,
    ``files``, ``free_blocks``).
    """
    sys_blocks = PARTHEAD_BLKS + (CDINFO_BLKS if cdrom else 0)
    vol_type = VOL_TYPE_CD3000 if cdrom else VOL_TYPE_S3000
    for name, files in volumes:
        if len(files) > VOLDIR_ENTRIES:
            raise AkaiImageError(
                f"volume '{name}' holds {len(files)} files but the S3000 "
                f"volume directory has {VOLDIR_ENTRIES} entries")

    part_blocks = min(PART_MAX_BLOCKS, max(sys_blocks + VOLDIR_HD_BLKS,
                                           (part_mb * 1048576) // HD_BLOCK))
    total_blocks = ((size_mb * 1048576) // HD_BLOCK) if size_mb is not None else None
    if total_blocks is not None:
        # A disk smaller than the nominal partition size is one short
        # partition, not a partition hanging off the end of the disk.
        part_blocks = min(part_blocks, total_blocks)

    if partitions is None:
        plan = _plan_partitions(volumes, part_blocks,
                                size_limited=total_blocks is not None
                                and part_blocks == total_blocks,
                                sys_blocks=sys_blocks)
    else:
        plan = _plan_given(volumes, partitions, part_blocks,
                           size_limited=total_blocks is not None
                           and part_blocks == total_blocks,
                           sys_blocks=sys_blocks)
    used = [sys_blocks + sum(VOLDIR_HD_BLKS
                                + sum(_blocks(len(d), HD_BLOCK) for _n, d in f)
                                for _v, f in p) for p in plan]

    if total_blocks is None:
        # Auto-size: content plus a quarter again for headroom, rounded up to
        # a whole megabyte, so there is room to add a volume later.
        # Auto-size stays close to the content on purpose: these images are
        # copied to a ZuluSCSI SD card over USB, where every spare megabyte is
        # copy time.  The floor is just enough to save a program back.
        content = int(sum(used) * 1.25)
        total_blocks = max(content, _AUTO_MIN_MB * (1048576 // HD_BLOCK))

        # AN EXPLICIT GROUPING NEEDS SLOTS THE CONTENT WOULD NOT HAVE CREATED.
        #
        # Partition SLOTS follow from the disk SIZE; the auto-size follows the
        # CONTENT. So a caller who asks for three partitions of small volumes
        # gets a disk with room for one, and a correct-but-baffling refusal:
        # "content needs 3 partitions but a 16 MB disk with 60 MB partitions
        # has 1". VinSamLib hit it on their first end-to-end run, and it is
        # the common case for a librarian rather than an edge one -- the
        # reason to force a boundary is usually that the content would NOT
        # have produced it.
        #
        # The requested slot count is knowable from the grouping, so this
        # computes it rather than documenting the trap. Documenting would have
        # left every future caller a test run to spend, and this is the same
        # class of fault as 'partitions' meaning slots: correct behaviour, no
        # crash where the confusion is, visible only from outside.
        #
        # The first N-1 partitions are full and the last is sized to its own
        # content, keeping the disk close to the material for the ZuluSCSI
        # copy-time reason above rather than rounding every partition up.
        if partitions is not None and len(plan) > 1:
            last = used[-1] if used else sys_blocks
            need = (len(plan) - 1) * part_blocks + max(last, sys_blocks + VOLDIR_HD_BLKS)
            total_blocks = max(total_blocks, need)

        total_blocks = _blocks(total_blocks * HD_BLOCK, 1048576) * (1048576 // HD_BLOCK)

    if total_blocks > HD_MAX_BLOCKS:
        raise AkaiImageError(
            f"disk would be {total_blocks} blocks; block numbers are 16-bit, "
            f"so the sampler cannot address past {HD_MAX_BLOCKS} "
            f"({HD_MAX_BLOCKS * HD_BLOCK // 1048576} MB)")

    # Carve the disk into partitions of at most `part_blocks`.
    sizes: List[int] = []
    remaining = total_blocks
    while remaining >= sys_blocks + VOLDIR_HD_BLKS and len(sizes) < MAX_PARTITIONS:
        s = min(part_blocks, remaining)
        sizes.append(s)
        remaining -= s
    if not sizes:
        raise AkaiImageError(
            f"disk of {total_blocks} blocks is smaller than one partition "
            f"header plus volume directory")
    # Give the leftover to the last partition rather than stranding it, unless
    # that would take it past the sampler's per-partition maximum.
    if sizes[-1] + remaining <= PART_MAX_BLOCKS:
        sizes[-1] += remaining
        remaining = 0

    if len(plan) > len(sizes):
        raise AkaiImageError(
            f"content needs {len(plan)} partitions but a "
            f"{total_blocks * HD_BLOCK / 1048576:.0f} MB disk with "
            f"{part_blocks * HD_BLOCK / 1048576:.0f} MB partitions has "
            f"{len(sizes)} — raise --hda-size")
    for i, need in enumerate(used):
        if need > sizes[i]:
            raise AkaiImageError(
                f"partition {chr(ord('A') + i)} needs "
                f"{need * HD_BLOCK / 1048576:.1f} MB but is "
                f"{sizes[i] * HD_BLOCK / 1048576:.1f} MB — raise --hda-size")
    # Count the partitions that HOLD something before padding the plan out to
    # the disk's slot count -- after this line len(plan) is the slot count and
    # the distinction the return value documents would be lost.
    n_used = len(plan)
    plan += [[] for _ in range(len(sizes) - len(plan))]
    tail_blocks = remaining             # addressable by nothing; zero padding

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_files = 0
    free_blocks = 0

    with atomic_write(out) as fh:
        for pi, (psize, pvols) in enumerate(zip(sizes, plan)):
            fat = [FAT_FREE] * PART_MAX_BLOCKS
            for b in range(sys_blocks):
                fat[b] = FAT_SYS

            body = bytearray()          # everything after the partition header
            rootdir: List[Tuple[str, int]] = []
            nxt = sys_blocks
            if cdrom:
                # Reserve the info block now and fill it once every volume's
                # entries are known — it indexes the whole partition.
                body += b'\0' * (CDINFO_BLKS * HD_BLOCK)
            per_volume_entries: List[List[bytes]] = []

            for vname, files in pvols:
                dir_start = nxt
                for b in range(dir_start, dir_start + VOLDIR_HD_BLKS - 1):
                    fat[b] = b + 1
                fat[dir_start + VOLDIR_HD_BLKS - 1] = FAT_DIREND
                nxt += VOLDIR_HD_BLKS
                dir_at = len(body)
                body += b'\0' * (VOLDIR_HD_BLKS * HD_BLOCK)

                entries = []
                for fname, data in files:
                    name, ftype = split_akai_name(fname)
                    nblk = _blocks(len(data), HD_BLOCK)
                    start = nxt
                    for b in range(start, start + nblk - 1):
                        fat[b] = b + 1
                    fat[start + nblk - 1] = FAT_FILEEND
                    nxt += nblk
                    body += data + b'\0' * (nblk * HD_BLOCK - len(data))
                    entries.append(_file_entry(name, ftype, len(data), start))
                    n_files += 1

                body[dir_at:dir_at + VOLDIR_HD_BLKS * HD_BLOCK] = \
                    _volume_directory(entries, VOLDIR_HD_BLKS, HD_BLOCK)
                rootdir.append((vname, dir_start))
                per_volume_entries.append(entries)

            if cdrom:
                body[0:CDINFO_BLKS * HD_BLOCK] = _cdinfo(
                    per_volume_entries, cd_label or CDINFO_DEFAULT_LABEL)

            free_blocks += psize - nxt
            fh.write(_partition_header(psize, rootdir, fat[:PART_MAX_BLOCKS],
                                       sizes if pi == 0 else None, vol_type))
            fh.write(body)
            # Pad out to the declared partition size so the next partition
            # starts where the partition table says it does.
            fh.write(b'\0' * ((psize - nxt) * HD_BLOCK))
        fh.write(b'\0' * (tail_blocks * HD_BLOCK))

    return {
        # TWO DIFFERENT NUMBERS, AND CALLERS ASSUME THE WRONG ONE.
        #
        # 'partitions' is how many partition SLOTS the disk is carved into,
        # which follows from the disk size. 'partitions_used' is how many of
        # them actually hold a volume. They differ whenever the auto-size adds
        # headroom: six 25 MB volumes fill three partitions on a disk that HAS
        # four, and both numbers are correct.
        #
        # VinSamLib built a layout preview against 'partitions', got 4 where
        # their reader found 3, and spent the difference looking for a
        # fill-rule disagreement that did not exist. A caller drawing a preview
        # wants 'partitions_used'; a caller describing the disk wants
        # 'partitions'.
        'partitions': len(sizes),
        'partitions_used': n_used,
        'blocks': total_blocks,
        'bytes': total_blocks * HD_BLOCK,
        'volumes': sum(len(p) for p in plan),
        'files': n_files,
        'free_blocks': free_blocks,
    }


def append_akai_volumes(image_path: str,
                        volumes: Sequence[Tuple[str, Sequence[Tuple[str, bytes]]]],
                        on_duplicate: str = 'prompt') -> Dict:
    """Add volumes to an existing AKAI hard-disk image, in place.

    No rebuild: free blocks are taken from the FAT and a free slot from the
    root directory, exactly as the sampler would.  The image keeps its size and
    its existing volumes keep their blocks.

    ``on_duplicate`` decides what happens when a volume name is already on the
    disk: ``skip``, ``add-new`` (append anyway — the sampler allows duplicate
    volume names), ``overwrite`` (drop the old one first) or ``prompt``.
    """
    path = Path(image_path)
    data = bytearray(path.read_bytes())
    if len(data) < PARTHEAD_BLKS * HD_BLOCK:
        raise AkaiImageError(f"{path.name} is too small to be an AKAI disk image")

    def u16(o):
        return data[o] | (data[o + 1] << 8)

    if not all(u16(2 + 2 * i) == (i * _MAGICVAL) & 0xFFFF for i in (1, 2, 50, 97)):
        raise AkaiImageError(
            f"{path.name} is not an AKAI hard-disk image (partition header "
            f"magic missing) — appending to a floppy is not supported")

    partnum = min(data[_OFF_PARTTAB + 0x100], MAX_PARTITIONS)
    sizes = [u16(_OFF_PARTTAB + 0x102 + 2 * i) for i in range(partnum)] or [u16(0)]
    bases, off = [], 0
    for psize in sizes:
        if psize == 0 or off * HD_BLOCK >= len(data):
            break
        bases.append((off * HD_BLOCK, psize))
        off += psize

    existing = {}
    for base, psize in bases:
        for vi in range(ROOTDIR_ENTRIES):
            o = base + _OFF_ROOTDIR + 16 * vi
            if data[o + 12] != VOL_TYPE_INACT:
                existing.setdefault(akai_to_str(data[o:o + AKAI_NAME_LEN]).rstrip(),
                                    (base, psize, vi))

    added, skipped = [], []
    for vname, files in volumes:
        name = akai_volume_name(vname)
        if name in existing:
            action = on_duplicate
            if action == 'prompt':
                ans = input(f"  Volume '{name}' is already on the image "
                            f"— [s]kip, [a]dd anyway, [o]verwrite? ").strip().lower()
                action = {'s': 'skip', 'a': 'add-new', 'o': 'overwrite'}.get(
                    ans[:1] if ans else 's', 'skip')
            if action == 'skip':
                skipped.append(name)
                continue
            if action == 'overwrite':
                base, _psize, vi = existing[name]
                _free_volume(data, base, vi)
                del existing[name]

        placed = False
        for base, psize in bases:
            fat = [u16(base + _OFF_FAT + 2 * i) for i in range(PART_MAX_BLOCKS)]
            slot = next((i for i in range(ROOTDIR_ENTRIES)
                         if data[base + _OFF_ROOTDIR + 16 * i + 12] == VOL_TYPE_INACT),
                        None)
            if slot is None:
                continue
            free = [b for b in range(PARTHEAD_BLKS, min(psize, PART_MAX_BLOCKS))
                    if fat[b] == FAT_FREE]
            need = VOLDIR_HD_BLKS + sum(_blocks(len(d), HD_BLOCK) for _n, d in files)
            if len(free) < need:
                continue

            it = iter(free)
            dirblocks = [next(it) for _ in range(VOLDIR_HD_BLKS)]
            entries = []
            for fname, fdata in files:
                fname_, ftype = split_akai_name(fname)
                blks = [next(it) for _ in range(_blocks(len(fdata), HD_BLOCK))]
                for j, b in enumerate(blks):
                    o = base + b * HD_BLOCK
                    chunk = fdata[j * HD_BLOCK:(j + 1) * HD_BLOCK]
                    data[o:o + HD_BLOCK] = chunk + b'\0' * (HD_BLOCK - len(chunk))
                _chain_into(data, base, blks, FAT_FILEEND)
                entries.append(_file_entry(fname_, ftype, len(fdata), blks[0]))

            dirbytes = _volume_directory(entries, VOLDIR_HD_BLKS, HD_BLOCK)
            for j, b in enumerate(dirblocks):
                o = base + b * HD_BLOCK
                data[o:o + HD_BLOCK] = dirbytes[j * HD_BLOCK:(j + 1) * HD_BLOCK]
            _chain_into(data, base, dirblocks, FAT_DIREND)

            o = base + _OFF_ROOTDIR + 16 * slot
            data[o:o + AKAI_NAME_LEN] = str_to_akai(name)
            data[o + 12] = VOL_TYPE_S3000
            data[o + 13] = 0
            _u16(data, o + 14, dirblocks[0])
            existing[name] = (base, psize, slot)
            added.append(name)
            placed = True
            break

        if not placed:
            raise AkaiImageError(
                f"no room on {path.name} for volume '{name}' — no partition has "
                f"both a free volume slot and enough free blocks")

    # A CD-ROM partition carries an index of every file on it.  Leaving it
    # stale after an append would show the sampler the old contents, so it is
    # rebuilt from what is actually there now.
    for base, psize in bases:
        if _is_cdrom_partition(data, base):
            _refresh_cdinfo(data, base, psize)

    with atomic_write(path) as _fh:
        _fh.write(bytes(data))
    return {'added': added, 'skipped': skipped}


def _is_cdrom_partition(data, base: int) -> bool:
    """CD-ROM info occupies the blocks right after the partition header, and
    they are the only ones besides the header marked reserved-for-system."""
    return all((data[base + _OFF_FAT + 2 * b] |
                (data[base + _OFF_FAT + 2 * b + 1] << 8)) == FAT_SYS
               for b in range(CDINFO_BLK, CDINFO_BLK + CDINFO_BLKS))


def _refresh_cdinfo(data: bytearray, base: int, psize: int) -> None:
    """Rebuild a CD partition's file index from its volume directories."""
    o = base + CDINFO_BLK * HD_BLOCK
    label = akai_to_str(bytes(data[o + 2 + 2 * ROOTDIR_ENTRIES:
                                   o + 2 + 2 * ROOTDIR_ENTRIES + AKAI_NAME_LEN]))

    per_volume: List[List[bytes]] = []
    for vi in range(ROOTDIR_ENTRIES):
        ro = base + _OFF_ROOTDIR + 16 * vi
        if data[ro + 12] == VOL_TYPE_INACT:
            continue
        start = data[ro + 14] | (data[ro + 15] << 8)
        blocks, b, seen = [], start, set()
        while 0 <= b < min(psize, PART_MAX_BLOCKS) and b not in seen:
            seen.add(b)
            blocks.append(b)
            nxt = (data[base + _OFF_FAT + 2 * b] |
                   (data[base + _OFF_FAT + 2 * b + 1] << 8))
            if nxt in (FAT_DIREND, FAT_FILEEND, FAT_FREE, FAT_SYS):
                break
            b = nxt
        dirbytes = b''.join(bytes(data[base + x * HD_BLOCK:
                                       base + (x + 1) * HD_BLOCK]) for x in blocks)
        per_volume.append([dirbytes[24 * i:24 * i + 24]
                           for i in range(min(VOLDIR_ENTRIES, len(dirbytes) // 24))
                           if dirbytes[24 * i + 16] != 0x00])

    data[o:o + CDINFO_BLKS * HD_BLOCK] = _cdinfo(per_volume, label.rstrip())


def _chain_into(data: bytearray, base: int, blocks: Sequence[int], end: int) -> None:
    """Write a FAT chain over `blocks`, terminated with `end`."""
    for i, b in enumerate(blocks):
        nxt = blocks[i + 1] if i + 1 < len(blocks) else end
        _u16(data, base + _OFF_FAT + 2 * b, nxt)


def _free_volume(data: bytearray, base: int, vi: int) -> None:
    """Release a volume's directory and file blocks, and clear its root slot.

    The blocks are only marked free in the FAT — their contents are left alone,
    which is what the sampler does when it deletes a volume.
    """
    o = base + _OFF_ROOTDIR + 16 * vi
    start = data[o + 14] | (data[o + 15] << 8)

    def walk(b, ends):
        seen, out = set(), []
        while 0 <= b < PART_MAX_BLOCKS and b not in seen:
            seen.add(b)
            out.append(b)
            nxt = data[base + _OFF_FAT + 2 * b] | (data[base + _OFF_FAT + 2 * b + 1] << 8)
            if nxt in ends or nxt == FAT_FREE or nxt == FAT_SYS:
                break
            b = nxt
        return out

    dirblocks = walk(start, (FAT_DIREND, FAT_FILEEND))
    dirbytes = b''.join(bytes(data[base + b * HD_BLOCK:base + (b + 1) * HD_BLOCK])
                        for b in dirblocks)
    doomed = list(dirblocks)
    for i in range(min(VOLDIR_ENTRIES, len(dirbytes) // 24)):
        e = dirbytes[24 * i:24 * i + 24]
        if e[16] == 0x00:
            continue
        doomed += walk(e[20] | (e[21] << 8), (FAT_FILEEND,))
    for b in doomed:
        _u16(data, base + _OFF_FAT + 2 * b, FAT_FREE)

    data[o:o + 16] = str_to_akai(f"VOLUME {vi + 1:03d}") + bytes(4)


# ── floppy ─────────────────────────────────────────────────────────────────

def build_akai_floppy_image(files: Sequence[Tuple[str, bytes]],
                            output_path: str,
                            volume_name: str = 'VOLUME 001',
                            density: str = 'hd') -> Dict:
    """Write an AKAI S3000 floppy image (1.6 MB high density, 800 KB low).

    The disk is not DOS-formatted — 80 tracks x 2 sides x 10 sectors x 1024
    bytes — so it is useful mainly through a Gotek or other emulator, the same
    way the K2000 floppy path is.

    The whole floppy is a single volume; its name lives in the header label
    rather than in a root directory.
    """
    if density not in ('hd', 'ld'):
        raise AkaiImageError(f"density must be 'hd' or 'ld', not {density!r}")
    hd = density == 'hd'
    total = FLH_SIZE if hd else FLL_SIZE
    head_blks = FLH_HEAD_BLKS if hd else FLL_HEAD_BLKS
    sys_blks = head_blks + VOLDIR_FL_BLKS

    if len(files) > VOLDIR_ENTRIES:
        raise AkaiImageError(
            f"{len(files)} files but the S3000 volume directory has "
            f"{VOLDIR_ENTRIES} entries")

    need = sum(_blocks(len(d), FL_BLOCK) for _n, d in files)
    if sys_blks + need > total:
        raise AkaiImageError(
            f"content is {need * FL_BLOCK / 1024:.0f} KB but only "
            f"{(total - sys_blks) * FL_BLOCK / 1024:.0f} KB fit on a "
            f"{'1.6 MB' if hd else '800 KB'} floppy")

    fat = [FAT_FREE] * total
    for b in range(sys_blks):
        fat[b] = FAT_SYS

    body = bytearray()
    entries = []
    nxt = sys_blks
    for fname, data in files:
        name, ftype = split_akai_name(fname)
        nblk = _blocks(len(data), FL_BLOCK)
        for b in range(nxt, nxt + nblk - 1):
            fat[b] = b + 1
        fat[nxt + nblk - 1] = FAT_FILEEND
        entries.append(_file_entry(name, ftype, len(data), nxt))
        body += data + b'\0' * (nblk * FL_BLOCK - len(data))
        nxt += nblk

    # Header: 64 file-entry slots (unused on an S3000 floppy — the real
    # directory sits behind the header), then the FAT, then the label.
    head = bytearray(head_blks * FL_BLOCK)
    for i in range(64):
        o = 24 * i
        # Raw 0x20 filler, not AKAI-encoded text: 0x20 decodes as 'V'.
        head[o:o + AKAI_NAME_LEN] = b'\x20' * AKAI_NAME_LEN
        _u16(head, o + 22, OSVER_S3000)
    # The first slot carries the "this is an S3000 floppy" marker in place of
    # a file type.
    head[16] = _FL_S3000_FLAG_TYPE

    fat_at = 64 * 24
    for i, code in enumerate(fat):
        _u16(head, fat_at + 2 * i, code)

    label_at = fat_at + total * 2
    head[label_at:label_at + AKAI_NAME_LEN] = str_to_akai(volume_name)
    _u16(head, label_at + 14, OSVER_S3000)
    o = label_at + 16
    head[o:o + _VOLPARAM_LEN] = _VOLPARAM_S3000

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with atomic_write(out) as fh:
        fh.write(head)
        fh.write(_volume_directory(entries, VOLDIR_FL_BLKS, FL_BLOCK,
                                   volparam=False))
        fh.write(body)
        fh.write(b'\0' * ((total - nxt) * FL_BLOCK))

    return {
        'blocks': total,
        'bytes': total * FL_BLOCK,
        'files': len(files),
        'free_blocks': total - nxt,
    }
