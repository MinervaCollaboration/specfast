"""Unpack Zemax archives (``.zar``).

A ``.zar`` file is a sequence of entries. Each entry has a 0x288-byte header
(little-endian: format version, flags, compressed size and uncompressed size
as 64-bit integers at offsets 0x10 and 0x18, a FILETIME, and the UTF-16 file
name from 0x30), followed by the payload. Names ending in ``.LZW`` are
compressed with LZW: 9- to 16-bit codes, most significant bit first, no
header, no clear code, the dictionary growing from code 256 and the code
width increasing when the next free code reaches ``2**width``.

Encrypted black-box files (``.ZBB``) are returned as they are; nothing here
decrypts them.
"""

from __future__ import annotations

import struct
from pathlib import Path

HEADER_SIZE = 0x288
_NAME_OFFSET = 0x30


class ZarError(ValueError):
    """A malformed archive or compressed stream."""


def lzw_decompress(data: bytes, max_bits: int = 16) -> bytes:
    """Decode a Zemax LZW stream (see the module docstring)."""
    table: list[bytes] = [bytes([i]) for i in range(256)]
    out = bytearray()
    prev: bytes | None = None
    width = 9
    buf = 0
    nbuf = 0
    limit = 1 << max_bits
    for byte in data:
        buf = (buf << 8) | byte
        nbuf += 8
        while nbuf >= width:
            nbuf -= width
            code = (buf >> nbuf) & ((1 << width) - 1)
            buf &= (1 << nbuf) - 1
            if code < len(table):
                entry = table[code]
            elif code == len(table) and prev is not None:
                entry = prev + prev[:1]
            else:
                raise ZarError(f"LZW: invalid code {code} after {len(out)} bytes")
            out += entry
            if prev is not None and len(table) < limit:
                table.append(prev + entry[:1])
            prev = entry
            if len(table) >= (1 << width) and width < max_bits:
                width += 1
    return bytes(out)


def read_zar(path: str | Path) -> dict[str, bytes]:
    """All files in a ``.zar`` archive, decompressed, keyed by file name
    (with any ``.LZW`` suffix removed)."""
    raw = Path(path).read_bytes()
    files: dict[str, bytes] = {}
    i = 0
    while i < len(raw):
        if i + HEADER_SIZE > len(raw):
            raise ZarError(f"{path}: truncated entry header at byte {i}")
        csize, usize = struct.unpack_from("<QQ", raw, i + 0x10)
        name = raw[i + _NAME_OFFSET : i + HEADER_SIZE].decode("utf-16-le").split("\x00")[0]
        start = i + HEADER_SIZE
        payload = raw[start : start + csize]
        if len(payload) != csize:
            raise ZarError(f"{path}: entry {name!r} is truncated")
        if name.upper().endswith(".LZW"):
            data = lzw_decompress(payload)
            name = name[:-4]
        else:
            data = payload
        if usize and len(data) != usize:
            raise ZarError(f"{path}: entry {name!r} decoded to {len(data)} bytes, expected {usize}")
        files[name] = data
        i = start + csize
    return files


def decode_text(data: bytes) -> str:
    """Zemax text files are UTF-16 (with BOM) or UTF-8/ASCII; return str with
    ``\\n`` line ends and no BOM."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16")
    elif len(data) > 1 and data[1:2] == b"\x00":
        text = data.decode("utf-16-le")
    else:
        text = data.decode("utf-8", errors="replace")
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def find(files: dict[str, bytes], suffix: str) -> list[str]:
    """Names in ``files`` with the given suffix (case-insensitive)."""
    return sorted(n for n in files if n.lower().endswith(suffix.lower()))
