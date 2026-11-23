"""A made-up echelle spectrograph as a Zemax lens file, for the optics tests.

All in air, with ideal (paraxial) lenses so the image positions follow from
the grating equation:

    object (slit, x/y in mm) -> collimator f_c -> echelle (transmissive,
    T1 lines/um, order m; the stop) -> coordinate break: 90 deg about z ->
    cross-disperser (T2 lines/um, order 1) -> camera f_cam -> coordinate
    break (decenter) -> image.

Two configurations differ in the echelle order (a PRAM operand).
"""

from __future__ import annotations

import struct

import numpy as np

F_COLL = 100.0
F_CAM = 200.0
T1 = 0.01  # echelle lines/um
T2 = 0.05  # cross-disperser lines/um
DX, DY = 20.0, 5.0  # image decenter [mm]
HALF = (1.0, 2.0)  # detector half-sizes [mm]
ORDERS = (20, 21)  # echelle order in configs 1, 2
WAVE = 0.5  # um


def zmx_text() -> str:
    surf = []

    def add(body: str) -> None:
        surf.append(f"SURF {len(surf)}\n{body}")

    add('  TYPE STANDARD\n  CURV 0.0 0 0 0 0 ""\n  DISZ 100\n')
    add(f"  TYPE PARAXIAL\n  COMM collimator\n  PARM 1 {F_COLL}\n  DISZ 50\n")
    add(
        f"  STOP\n  TYPE DGRATING\n  COMM echelle\n  PARM 1 {T1}\n  PARM 2 {ORDERS[0]}\n  DISZ 10\n"
    )
    add("  TYPE COORDBRK\n  PARM 5 90\n  DISZ 0\n")
    add(f"  TYPE DGRATING\n  COMM cross-disperser\n  PARM 1 {T2}\n  PARM 2 1\n  DISZ 10\n")
    add(f"  TYPE PARAXIAL\n  COMM camera\n  PARM 1 {F_CAM}\n  DISZ {F_CAM}\n")
    add(f"  TYPE COORDBRK\n  PARM 1 {DX}\n  PARM 2 {DY}\n  DISZ 0\n")
    add(f"  TYPE STANDARD\n  COMM detector\n  SQAP {HALF[0]} {HALF[1]} 0\n  DISZ 0\n")
    head = (
        "VERS 190513 80 123457 L123457\nMODE SEQ\nNAME synthetic echelle\n"
        "UNIT MM X W X CM MR CPMM\nENVD 20 1 0\nPWAV 1\n"
        f"WAVM 1 {WAVE} 1\nXFLN 0 0 0\nYFLN 0 0.2 -0.2\nFCOM 2 upper\n"
    )
    mce = 'MNUM 2 1\nMOFF 0 1 "ORDER 20" 0 0 0 1 1 0 0.0 "" 0\n'
    for c, m in enumerate(ORDERS, 1):
        mce += f'PRAM 2 {c} {m} 0 2 0 1 1 0 0 0 "" 0\n'
    return head + "".join(surf) + mce


def expected_xy(x0, y0, lam, m):
    """Image position (detector local frame, mm) from the grating equation."""
    d = np.array([-x0 / F_COLL, -y0 / F_COLL, 1.0])
    d /= np.linalg.norm(d)
    kx, ky = d[0], d[1] + m * lam * T1
    # 90 deg about z: local x = global y, local y = -global x
    lx, ly = ky, -kx + lam * T2
    lz = np.sqrt(1 - lx * lx - ly * ly)
    return F_CAM * lx / lz - DX, F_CAM * ly / lz - DY


def lzw_compress(data: bytes, max_bits: int = 16) -> bytes:
    """The encoder matching :func:`specfast.optics.zar.lzw_decompress`."""
    table = {bytes([i]): i for i in range(256)}
    codes = []
    w = b""
    for b in data:
        wc = w + bytes([b])
        if wc in table:
            w = wc
            continue
        codes.append(table[w])
        if len(table) < (1 << max_bits):
            table[wc] = len(table)
        w = bytes([b])
    if w:
        codes.append(table[w])
    out, buf, nbuf = bytearray(), 0, 0
    width = 9
    for k, code in enumerate(codes):
        size = 256 + max(0, k - 1)  # decoder's table size when it reads code k
        while size >= (1 << width) and width < max_bits:
            width += 1
        buf = (buf << width) | code
        nbuf += width
        while nbuf >= 8:
            nbuf -= 8
            out.append((buf >> nbuf) & 0xFF)
            buf &= (1 << nbuf) - 1
    if nbuf:
        out.append((buf << (8 - nbuf)) & 0xFF)
    return bytes(out)


def zar_bytes(files: dict[str, bytes]) -> bytes:
    """A .zar archive holding ``files`` (LZW-compressed)."""
    out = bytearray()
    for name, data in files.items():
        comp = lzw_compress(data)
        hdr = bytearray(0x288)
        struct.pack_into("<IIIIQQ", hdr, 0, 1004, 0, 1, 0, len(comp), len(data))
        nm = (name + ".LZW").encode("utf-16-le")
        hdr[0x30 : 0x30 + len(nm)] = nm
        out += hdr + comp
    return bytes(out)
