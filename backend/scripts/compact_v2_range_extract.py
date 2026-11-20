"""Read a few georeferenced image tiles from a STORED CompactV2 ZIP entry.

This does not download the source .bundle. The ZIP local header identifies
the start of its uncompressed bytes; the Esri fixed 64+131072 index identifies
exact image offsets and lengths. All reads are bounded by RangeZipReader.
"""
import struct
import zipfile

HEADER_BYTES = 64
INDEX_BYTES = 131_072
MIN_BODY_OFFSET = HEADER_BYTES + INDEX_BYTES
MAX_TILE_BYTES = 4 * 1024 * 1024


def entry_payload_start(reader, info):
    if info.compress_type != zipfile.ZIP_STORED:
        raise ValueError("Selective extraction needs ZIP_STORED bundle")
    reader.seek(info.header_offset)
    hdr = reader.read(30)
    if len(hdr) != 30 or hdr[:4] != b"PK\x03\x04":
        raise ValueError("Invalid ZIP local file header")
    flags, method = struct.unpack_from("<HH", hdr, 6)
    if flags & 0x1 or method != zipfile.ZIP_STORED:
        raise ValueError("Encrypted or compressed source not accepted")
    name_len, extra_len = struct.unpack_from("<HH", hdr, 26)
    if name_len == 0 or name_len > 65_535 or extra_len > 65_535:
        raise ValueError("Invalid local header lengths")
    # Check the local filename against the central ZIP directory, not only
    # the offsets: central directory metadata is not enough on its own.
    local_name = reader.read(name_len)
    if local_name.decode("utf-8") != info.filename:
        raise ValueError("ZIP central/local filename disagreement")
    return info.header_offset + 30 + name_len + extra_len


def fixed_header_index(reader, payload_start, info):
    if info.file_size < MIN_BODY_OFFSET:
        raise ValueError("CompactV2 bundle too small")
    reader.seek(payload_start)
    prefix = reader.read(MIN_BODY_OFFSET)
    if len(prefix) != MIN_BODY_OFFSET:
        raise ValueError("Missing CompactV2 fixed header/index")
    version, declared_count = struct.unpack_from("<II", prefix, 0)
    # Published Kentucky TPKX may declare 0 despite valid full index.
    if version != 3 or declared_count not in (0, 16_384):
        raise ValueError("Unexpected CompactV2 header")
    if struct.unpack_from("<I", prefix, 12)[0] != 5:
        raise ValueError("Invalid CompactV2 offset byte width")
    if struct.unpack_from("<Q", prefix, 32)[0] != 40:
        raise ValueError("Invalid CompactV2 user header")
    if struct.unpack_from("<I", prefix, 40)[0] != 20 + INDEX_BYTES:
        raise ValueError("Invalid CompactV2 user header size")
    if struct.unpack_from("<I", prefix, 60)[0] != INDEX_BYTES:
        raise ValueError("Invalid CompactV2 index size")
    return prefix


def select_xyz_tiles(reader, info, origin_y, origin_x, zoom,
                     bounds, xy_func, image_validator):
    offset = entry_payload_start(reader, info)
    prefix = fixed_header_index(reader, offset, info)
    nw = xy_func(bounds[0], bounds[3], zoom)
    se = xy_func(bounds[2], bounds[1], zoom)
    for y in range(max(origin_y, min(nw[1], se[1])),
                   min(origin_y + 127, max(nw[1], se[1])) + 1):
        for x in range(max(origin_x, min(nw[0], se[0])),
                       min(origin_x + 127, max(nw[0], se[0])) + 1):
            position = HEADER_BYTES + ((y - origin_y) * 128 +
                                        (x - origin_x)) * 8
            value = struct.unpack_from("<Q", prefix, position)[0]
            tile_offset = value & ((1 << 40) - 1)
            tile_size = value >> 40
            if tile_size == 0:
                continue
            if (tile_size > MAX_TILE_BYTES or tile_offset < MIN_BODY_OFFSET or
                    tile_offset + tile_size > info.file_size):
                raise ValueError("Invalid CompactV2 source tile offset/size")
            reader.seek(offset + tile_offset)
            raw = reader.read(tile_size)
            if len(raw) != tile_size:
                raise ValueError("Truncated source tile range")
            fmt = image_validator(raw)
            if fmt is None:
                raise ValueError("Source tile is not an original 256px image")
            yield zoom, x, y, fmt, raw
