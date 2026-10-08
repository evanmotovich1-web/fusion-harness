#!/usr/bin/env python3
"""Foreground stdlib PDF text decoder. ASCII85+Flate and Flate streams."""
from __future__ import annotations

import base64
import re
import sys
import zlib
from pathlib import Path


def pdf_unescape(s: bytes) -> str:
    out = bytearray()
    i = 0
    while i < len(s):
        if s[i] != 0x5C:  # backslash
            out.append(s[i])
            i += 1
            continue
        i += 1
        if i >= len(s):
            break
        c = s[i]
        if c in (0x0A, 0x0D):  # line continuation
            if c == 0x0D and i + 1 < len(s) and s[i + 1] == 0x0A:
                i += 2
            else:
                i += 1
            continue
        simple = {
            0x6E: 0x0A,  # n
            0x72: 0x0D,  # r
            0x74: 0x09,  # t
            0x62: 0x08,  # b
            0x66: 0x0C,  # f
            0x28: 0x28,  # (
            0x29: 0x29,  # )
            0x5C: 0x5C,  # \
        }
        if c in simple:
            out.append(simple[c])
            i += 1
            continue
        if 0x30 <= c <= 0x37:
            octal = [c]
            i += 1
            while i < len(s) and 0x30 <= s[i] <= 0x37 and len(octal) < 3:
                octal.append(s[i])
                i += 1
            out.append(int(bytes(octal), 8) & 0xFF)
            continue
        out.append(c)
        i += 1
    return out.decode("latin1", errors="replace")


def decode_ascii85(data: bytes) -> bytes:
    data = re.sub(rb"\s+", b"", data)
    adobe = data.endswith(b"~>")
    if adobe:
        data = data[:-2]
    return base64.a85decode(data, adobe=False)


def inflate(data: bytes) -> bytes:
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS, zlib.MAX_WBITS | 16):
        try:
            return zlib.decompress(data, wbits)
        except zlib.error:
            continue
    raise zlib.error("inflate failed")


STREAM_RE = re.compile(rb"stream\r?\n(.*?)endstream", re.S)
DICT_BEFORE_RE = re.compile(rb"<<((?:(?!<<).)*?)>>\s*stream\r?\n", re.S)
FILTER_RE = re.compile(rb"/Filter\s*(\[[^\]]*\]|/[\w]+)")
LITERAL_RE = re.compile(rb"\((?:\\.|[^\\)])*\)")
HEX_RE = re.compile(rb"<([0-9A-Fa-f \r\n]+)>")
TJ_RE = re.compile(rb"\[(.*?)\]\s*TJ", re.S)
Tj_RE = re.compile(rb"(\((?:\\.|[^\\)])*\)|<([0-9A-Fa-f \r\n]+)>)\s*Tj")
QUOTE_RE = re.compile(rb"(\((?:\\.|[^\\)])*\))\s*'")
TSTAR_RE = re.compile(rb"T\*")
TD_RE = re.compile(rb"(-?[\d.]+)\s+(-?[\d.]+)\s+Td")
TITLE_RE = re.compile(rb"/Title\s*\((?:\\.|[^\\)])*\)")
AUTHOR_RE = re.compile(rb"/Author\s*\((?:\\.|[^\\)])*\)")
CREATION_RE = re.compile(rb"/CreationDate\s*\((?:\\.|[^\\)])*\)")
PRODUCER_RE = re.compile(rb"/Producer\s*\((?:\\.|[^\\)])*\)")


def filters_of(dict_bytes: bytes) -> list[str]:
    m = FILTER_RE.search(dict_bytes)
    if not m:
        return []
    blob = m.group(1)
    return [x.decode("ascii") for x in re.findall(rb"/([A-Za-z0-9]+)", blob)]


def decode_stream(raw: bytes, payload: bytes, start: int) -> bytes | None:
    window = raw[max(0, start - 800) : start]
    filts = filters_of(window)
    data = payload
    try:
        for f in filts:
            if f in ("ASCII85Decode", "A85"):
                data = decode_ascii85(data)
            elif f in ("FlateDecode", "Fl"):
                data = inflate(data)
            elif f in ("DCTDecode", "JPXDecode", "CCITTFaxDecode", "JBIG2Decode"):
                return None
            else:
                return None
        if not filts:
            try:
                data = inflate(data)
            except zlib.error:
                try:
                    data = decode_ascii85(data)
                    data = inflate(data)
                except Exception:
                    return None
        return data
    except Exception:
        return None


def parse_tounicode(data: bytes) -> dict[int, str]:
    cmap: dict[int, str] = {}
    if b"beginbfchar" not in data and b"beginbfrange" not in data:
        return cmap

    def hex_int(h: bytes) -> int:
        return int(re.sub(rb"\s+", b"", h), 16)

    def hex_chr(h: bytes) -> str:
        raw = bytes.fromhex(re.sub(rb"\s+", b"", h).decode("ascii"))
        if len(raw) == 1:
            return chr(raw[0])
        if len(raw) % 2 == 0:
            return raw.decode("utf-16-be", errors="replace")
        return raw.decode("latin1", errors="replace")

    for src, dst in re.findall(rb"<([0-9A-Fa-f\s]+)>[ \t]+<([0-9A-Fa-f\s]+)>\s*(?=\n|<|endbfchar)", data):
        # bfchar pairs only inside beginbfchar... we'll still accept; ranges handled below
        pass
    in_char = False
    in_range = False
    for line in data.splitlines():
        if b"beginbfchar" in line:
            in_char = True
            in_range = False
            continue
        if b"endbfchar" in line:
            in_char = False
            continue
        if b"beginbfrange" in line:
            in_range = True
            in_char = False
            continue
        if b"endbfrange" in line:
            in_range = False
            continue
        if in_char:
            m = re.match(rb"\s*<([0-9A-Fa-f]+)>[ \t]+<([0-9A-Fa-f]+)>\s*$", line)
            if m:
                cmap[hex_int(m.group(1))] = hex_chr(m.group(2))
        if in_range:
            m = re.match(
                rb"\s*<([0-9A-Fa-f]+)>[ \t]+<([0-9A-Fa-f]+)>[ \t]+<([0-9A-Fa-f]+)>\s*$",
                line,
            )
            if m:
                start = hex_int(m.group(1))
                end = hex_int(m.group(2))
                dest = hex_int(m.group(3))
                for i, cid in enumerate(range(start, end + 1)):
                    cmap[cid] = chr(dest + i)
    return cmap


def collect_cmaps(raw: bytes) -> dict[int, str]:
    cmap: dict[int, str] = {}
    for m in STREAM_RE.finditer(raw):
        payload = m.group(1)
        decoded = decode_stream(raw, payload, m.start())
        if not decoded:
            continue
        cmap.update(parse_tounicode(decoded))
    return cmap


def map_hex_string(hexpart: bytes, cmap: dict[int, str]) -> str:
    hx = re.sub(rb"\s+", b"", hexpart)
    if len(hx) % 2:
        hx += b"0"
    try:
        raw = bytes.fromhex(hx.decode("ascii"))
    except ValueError:
        return ""
    # 2-byte CIDs when even length >= 2 and cmap present
    if cmap and len(raw) % 2 == 0:
        out = []
        for i in range(0, len(raw), 2):
            cid = (raw[i] << 8) | raw[i + 1]
            out.append(cmap.get(cid, chr(cid) if cid < 256 else ""))
        return "".join(out)
    if cmap and len(raw) == 1:
        return cmap.get(raw[0], chr(raw[0]))
    return raw.decode("latin1", errors="replace")


def extract_literals(content: bytes, cmap: dict[int, str] | None = None) -> list[str]:
    texts: list[str] = []
    cmap = cmap or {}
    i = 0
    n = len(content)
    while i < n:
        if content.startswith(b"T*", i) and (i == 0 or not content[i - 1 : i].isalnum()):
            texts.append("\n")
            i += 2
            continue
        m = re.match(rb"(-?[\d.]+)\s+(-?[\d.]+)\s+T[dD]", content[i : i + 48])
        if m:
            try:
                x = float(m.group(1))
                y = float(m.group(2))
            except ValueError:
                x, y = 0.0, 0.0
            if abs(y) > 4:
                texts.append("\n")
            i += m.end()
            continue
        if content.startswith(b"TJ", i):
            i += 2
            continue
        if content.startswith((b"Tj", b"TJ", b"'")):
            i += 1
            continue
        if content[i : i + 1] == b"(":
            j = i + 1
            depth = 1
            while j < n and depth:
                if content[j] == 0x5C:
                    j += 2
                    continue
                if content[j] == 0x28:
                    depth += 1
                elif content[j] == 0x29:
                    depth -= 1
                j += 1
            lit = content[i + 1 : j - 1]
            rest = content[j : j + 12].lstrip()
            if rest.startswith(b"Tj") or rest.startswith(b"'") or rest.startswith(b'"') or rest.startswith(b"TJ"):
                texts.append(pdf_unescape(lit))
            i = j
            continue
        if content[i : i + 1] == b"<" and i + 1 < n and content[i + 1] not in b"<":
            k = content.find(b">", i + 1)
            if k > i:
                hexpart = content[i + 1 : k]
                rest = content[k + 1 : k + 12].lstrip()
                if rest.startswith(b"Tj") or rest.startswith(b"'") or rest.startswith(b'"'):
                    texts.append(map_hex_string(hexpart, cmap))
                i = k + 1
                continue
        i += 1
    return texts


def tidy(parts: list[str]) -> str:
    buf: list[str] = []
    for p in parts:
        if p == "\n":
            if buf and buf[-1] != "\n":
                buf.append("\n")
            continue
        if p == " ":
            if buf and buf[-1] not in (" ", "\n"):
                buf.append(" ")
            continue
        if not p:
            continue
        if buf and buf[-1] not in ("\n", " ") and not p.startswith((" ", "\n")):
            prev = buf[-1]
            glue = (
                len(p) <= 2
                or len(prev) <= 2
                or prev.endswith("-")
                or p[:1] in ",.;:!?')]}%"
            )
            if prev.endswith("-"):
                buf[-1] = prev[:-1]
            elif not glue:
                buf.append(" ")
        buf.append(p)
    text = "".join(buf)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip() + "\n"


def meta_field(raw: bytes, name: bytes) -> str:
    m = re.search(rb"/" + name + rb"\s*\(((?:\\.|[^\\)])*)\)", raw)
    if not m:
        return ""
    return pdf_unescape(m.group(1)).replace("\x00", "").strip()


def decode_pdf(path: Path) -> str:
    raw = path.read_bytes()
    header = [
        f"SOURCE\t{path}",
        f"BYTES\t{len(raw)}",
        f"TITLE\t{meta_field(raw, b'Title')}",
        f"AUTHOR\t{meta_field(raw, b'Author')}",
        f"CREATIONDATE\t{meta_field(raw, b'CreationDate')}",
        f"PRODUCER\t{meta_field(raw, b'Producer')}",
        f"PAGES_KIDS\t{raw.count(b'/Type /Page')}",
        "",
        "----- DECODED TEXT -----",
        "",
    ]
    pages_text: list[str] = []
    page_no = 0
    cmap = collect_cmaps(raw)
    for m in STREAM_RE.finditer(raw):
        payload = m.group(1)
        decoded = decode_stream(raw, payload, m.start())
        if not decoded:
            continue
        # skip obvious font programs
        if decoded.startswith((b"\x00\x01\x00\x00", b"OTTO", b"true", b"wOFF")):
            continue
        if b"BT" not in decoded and b"Tj" not in decoded and b"TJ" not in decoded:
            continue
        page_no += 1
        parts = extract_literals(decoded, cmap)
        body = tidy(parts)
        if body.strip():
            pages_text.append(f"----- PAGE {page_no} -----\n{body}")
    if not pages_text:
        header.append("[NO SELECTABLE TEXT EXTRACTED]\n")
        return "\n".join(header)
    return "\n".join(header) + "\n".join(pages_text) + "\n"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: decode_pdf.py INPUT.pdf OUTPUT.txt", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    if not src.is_file():
        print(f"missing: {src}", file=sys.stderr)
        return 1
    text = decode_pdf(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    print(f"wrote {dst} chars={len(text)} pages={text.count('----- PAGE ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
