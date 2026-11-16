"""Inspect embedded Director movie resources without executing game code.

Run from the package root: python3 port-analysis/inspect_movie.py
Outputs are written beside this script. No third-party dependencies required.
"""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import struct


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "MB_2010-10-08.exe"
OUT = Path(__file__).resolve().parent
data = SOURCE.read_bytes()

candidates = [
    m.start() for m in re.finditer(b"XFIR", data)
    if data[m.start() + 8:m.start() + 12] == b"39VM"
]
if len(candidates) != 1:
    raise ValueError(f"Expected one embedded MV93 movie, got {candidates}")
movie = candidates[0]
movie_size = struct.unpack_from("<I", data, movie + 4)[0] + 8
if movie + movie_size > len(data):
    raise ValueError("Truncated movie")
if data[movie + 12:movie + 16] != b"pami":
    raise ValueError("Missing movie index map")

# This projector stores absolute offsets into the EXE, not movie-relative offsets.
memory_map = struct.unpack_from("<I", data, movie + 24)[0]
if data[memory_map:memory_map + 4] != b"pamm":
    raise ValueError("Missing resource map at the absolute offset")
header_size, entry_size, allocated, used = struct.unpack_from(
    "<HHII", data, memory_map + 8
)
if header_size != 24 or entry_size != 20 or used > allocated:
    raise ValueError("Unexpected resource map layout")
if memory_map + 8 + header_size + allocated * entry_size > len(data):
    raise ValueError("Truncated resource map")

entries = []
symbols = []
for index in range(used):
    pos = memory_map + 8 + header_size + index * entry_size
    tag = data[pos:pos + 4][::-1].decode("ascii")
    length, offset, flags, reserved, next_index = struct.unpack_from(
        "<IIHHI", data, pos + 4
    )
    if tag in ("free", "junk", "\0\0\0\0"):
        continue
    if offset + 8 + length > len(data):
        raise ValueError(f"Truncated chunk {index}")
    if data[offset:offset + 4][::-1].decode("ascii") != tag:
        raise ValueError(f"Resource map mismatch for chunk {index}")
    payload = data[offset + 8:offset + 8 + length]
    row = {"id": index, "tag": tag, "offset": offset,
           "length": length, "flags": flags}
    if tag == "XMED":
        row["shockwave_3d_signature"] = payload.startswith(b"3DEM")
        row["flash_signature_in_first_20_bytes"] = b"FWS" in payload[:20]
    entries.append(row)
    if tag == "Lnam":
        cursor, count = struct.unpack_from(">HH", payload, 16)
        names = []
        for _ in range(count):
            size = payload[cursor]
            cursor += 1
            if cursor + size > len(payload):
                raise ValueError("Truncated Lingo name table")
            names.append(payload[cursor:cursor + size].decode("mac_roman"))
            cursor += size
        if cursor != len(payload):
            raise ValueError("Name table has unexplained trailing bytes")
        symbols.append({"chunk_id": index, "names": names})

summary = {
    "source": SOURCE.name, "source_sha256": sha256(data).hexdigest(),
    "movie_offset": movie, "movie_bytes": movie_size,
    "memory_map_offset": memory_map,
    "allocated_map_slots": allocated, "used_map_slots": used,
    "resource_counts_excluding_free_and_junk": dict(Counter(r["tag"] for r in entries)),
    "name_table_entries": sum(len(t["names"]) for t in symbols),
    "note": "Structural inspection only; no game execution or source decompilation.",
}
for name, value in [("movie-summary.json", summary), ("movie-chunks.json", entries),
                    ("lingo-symbols.json", symbols)]:
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n")
print(json.dumps(summary, indent=2))
