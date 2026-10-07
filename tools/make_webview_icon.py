"""Regenerate tools/webview_host.ico (solid #FC4D50 circle, 7 sizes)."""

import struct
from pathlib import Path

COLOR = (0xFC, 0x4D, 0x50)
SIZES = [16, 24, 32, 48, 64, 128, 256]
SS = 4


def render(size: int) -> list[bytes]:
    n = size * SS
    center = (n - 1) / 2.0
    radius = (size * 0.96 / 2.0) * SS
    r2 = radius * radius
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            hits = 0
            for sy in range(SS):
                dy = (y * SS + sy + 0.5) - center
                base = dy * dy
                for sx in range(SS):
                    dx = (x * SS + sx + 0.5) - center
                    if dx * dx + base <= r2:
                        hits += 1
            alpha = round(255 * hits / (SS * SS))
            row += bytes((COLOR[2], COLOR[1], COLOR[0], alpha))
        rows.append(bytes(row))
    return rows


def bmp_entry(size: int, rows: list[bytes]) -> bytes:
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    xor = b"".join(reversed(rows))
    and_stride = ((size + 31) // 32) * 4
    and_mask = b"\x00" * (and_stride * size)
    return header + xor + and_mask


def build() -> bytes:
    entries = [(size, bmp_entry(size, render(size))) for size in SIZES]
    out = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
    offset = 6 + 16 * len(entries)
    for size, data in entries:
        dim = 0 if size == 256 else size
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _, data in entries:
        out += data
    return bytes(out)


def main() -> None:
    target = Path(__file__).resolve().parent / "webview_host.ico"
    target.write_bytes(build())
    print(f"wrote {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
