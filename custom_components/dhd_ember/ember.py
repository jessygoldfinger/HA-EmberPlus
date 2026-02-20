"""Ember+ protocol client for DHD audio mixing consoles.

Implements the S101 framing layer, minimal BER/EmBER encoding, and the
Glow DTD subset needed to interact with DHD's Ember+ provider:

- Device > Identity  (read-only strings)
- Device > GPI 1..50 (boolean, read/write)
- Device > GPO 1..50 (boolean, read-only)

Reference:
    https://github.com/Lawo/ember-plus/wiki
    https://developer.dhd.audio/docs/api/ember/

TCP port: 9000 (DHD default)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# S101 constants
# ---------------------------------------------------------------------------
S101_BOF = 0xFE
S101_EOF = 0xFF
S101_CE = 0xFD  # escape byte
S101_INVALID = 0xF8  # bytes >= this need escaping

# S101 message header
S101_SLOT = 0x00
S101_MSG_EMBER = 0x0E
S101_CMD_EMBER = 0x00
S101_CMD_KEEPALIVE_REQ = 0x01
S101_CMD_KEEPALIVE_RESP = 0x02
S101_VERSION = 0x01

# Ember flags
EMBER_FLAG_FIRST = 0x80
EMBER_FLAG_LAST = 0x40
EMBER_FLAG_SINGLE = EMBER_FLAG_FIRST | EMBER_FLAG_LAST

# Glow DTD
GLOW_DTD_TYPE = 0x01
GLOW_SCHEMA_MAJOR = 0x02
GLOW_SCHEMA_MINOR = 0x1F

# ---------------------------------------------------------------------------
# CRC-CCITT16 (polynomial 0x1021, init 0xFFFF)
# ---------------------------------------------------------------------------
_CRC_TABLE: list[int] = []


def _init_crc_table() -> None:
    """Build CRC-16/MCRF4XX lookup table (reflected poly 0x8408)."""
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
        _CRC_TABLE.append(crc)


_init_crc_table()


def _crc_ccitt16(data: bytes, init: int = 0xFFFF) -> int:
    """CRC-16/MCRF4XX: reflected CCITT with poly 0x1021, init 0xFFFF."""
    crc = init
    for b in data:
        crc = (_CRC_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)) & 0xFFFF
    return crc


# ---------------------------------------------------------------------------
# S101 framing
# ---------------------------------------------------------------------------

def s101_encode(payload: bytes) -> bytes:
    """Encode a payload into an S101 frame (BOF + escaped data + CRC + EOF)."""
    crc = ~_crc_ccitt16(payload) & 0xFFFF
    raw = payload + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    out = bytearray([S101_BOF])
    for b in raw:
        if b >= S101_INVALID:
            out.append(S101_CE)
            out.append(b ^ 0x20)
        else:
            out.append(b)
    out.append(S101_EOF)
    return bytes(out)


def s101_decode(frame: bytes) -> bytes:
    """Decode an S101 frame, verify CRC, return the payload."""
    if not frame or frame[0] != S101_BOF or frame[-1] != S101_EOF:
        raise EmberProtocolError("Invalid S101 frame markers")

    # Un-escape
    raw = bytearray()
    i = 1  # skip BOF
    end = len(frame) - 1  # skip EOF
    while i < end:
        b = frame[i]
        if b == S101_CE:
            i += 1
            if i < end:
                raw.append(frame[i] ^ 0x20)
        else:
            raw.append(b)
        i += 1

    if len(raw) < 2:
        raise EmberProtocolError("S101 frame too short for CRC")

    payload = bytes(raw[:-2])
    crc_received = raw[-2] | (raw[-1] << 8)
    crc_computed = ~_crc_ccitt16(payload) & 0xFFFF

    if crc_received != crc_computed:
        raise EmberProtocolError(
            f"S101 CRC mismatch: received 0x{crc_received:04X}, "
            f"computed 0x{crc_computed:04X}"
        )

    return payload


# ---------------------------------------------------------------------------
# S101 message builders
# ---------------------------------------------------------------------------

def build_ember_message(ber_data: bytes) -> bytes:
    """Build a complete S101 Ember message with framing."""
    header = bytes([
        S101_SLOT,
        S101_MSG_EMBER,
        S101_CMD_EMBER,
        S101_VERSION,
        EMBER_FLAG_SINGLE,
        GLOW_DTD_TYPE,
        0x02,  # app bytes length
        GLOW_SCHEMA_MAJOR,
        GLOW_SCHEMA_MINOR,
    ])
    return s101_encode(header + ber_data)


def build_keepalive_request() -> bytes:
    """Build an S101 keepalive request."""
    header = bytes([
        S101_SLOT,
        S101_MSG_EMBER,
        S101_CMD_KEEPALIVE_REQ,
        S101_VERSION,
    ])
    return s101_encode(header)


def build_keepalive_response() -> bytes:
    """Build an S101 keepalive response."""
    header = bytes([
        S101_SLOT,
        S101_MSG_EMBER,
        S101_CMD_KEEPALIVE_RESP,
        S101_VERSION,
    ])
    return s101_encode(header)


# ---------------------------------------------------------------------------
# Minimal BER encoding helpers
# ---------------------------------------------------------------------------

# BER tag classes
BER_CLASS_UNIVERSAL = 0x00
BER_CLASS_APPLICATION = 0x40
BER_CLASS_CONTEXT = 0x80

# BER constructed flag
BER_CONSTRUCTED = 0x20

# Universal tags
BER_TAG_BOOLEAN = 0x01
BER_TAG_INTEGER = 0x02
BER_TAG_UTF8STRING = 0x0C
BER_TAG_SEQUENCE = 0x30
BER_TAG_SET = 0x31


def ber_encode_tag(tag_class: int, constructed: bool, number: int) -> bytes:
    """Encode a BER tag."""
    first = tag_class
    if constructed:
        first |= BER_CONSTRUCTED
    if number < 31:
        return bytes([first | number])
    # Long form
    first |= 0x1F
    parts: list[int] = []
    n = number
    while n > 0:
        parts.append(n & 0x7F)
        n >>= 7
    parts.reverse()
    result = bytearray([first])
    for i, p in enumerate(parts):
        if i < len(parts) - 1:
            result.append(p | 0x80)
        else:
            result.append(p)
    return bytes(result)


def ber_encode_length(length: int) -> bytes:
    """Encode a BER length."""
    if length < 0x80:
        return bytes([length])
    parts: list[int] = []
    n = length
    while n > 0:
        parts.append(n & 0xFF)
        n >>= 8
    parts.reverse()
    return bytes([0x80 | len(parts)] + parts)


def ber_encode_boolean(value: bool) -> bytes:
    """Encode a BER BOOLEAN."""
    return bytes([BER_TAG_BOOLEAN, 0x01, 0xFF if value else 0x00])


def ber_encode_integer(value: int) -> bytes:
    """Encode a BER INTEGER."""
    if value == 0:
        data = b"\x00"
    else:
        byte_len = (value.bit_length() + 8) // 8
        data = value.to_bytes(byte_len, "big", signed=True)
    return bytes([BER_TAG_INTEGER]) + ber_encode_length(len(data)) + data


def ber_encode_utf8(value: str) -> bytes:
    """Encode a BER UTF8String."""
    encoded = value.encode("utf-8")
    return bytes([BER_TAG_UTF8STRING]) + ber_encode_length(len(encoded)) + encoded


def ber_tlv(tag: bytes, value: bytes) -> bytes:
    """Build a TLV (tag + length + value)."""
    return tag + ber_encode_length(len(value)) + value


# ---------------------------------------------------------------------------
# Minimal BER decoding helpers
# ---------------------------------------------------------------------------

def ber_decode_tag(data: bytes, offset: int) -> tuple[int, int, bool, int]:
    """Decode a BER tag. Returns (tag_class, number, constructed, new_offset)."""
    if offset >= len(data):
        raise EmberProtocolError("BER: unexpected end of data reading tag")
    b = data[offset]
    tag_class = b & 0xC0
    constructed = bool(b & BER_CONSTRUCTED)
    number = b & 0x1F
    offset += 1

    if number == 0x1F:
        number = 0
        while offset < len(data):
            nb = data[offset]
            offset += 1
            number = (number << 7) | (nb & 0x7F)
            if not (nb & 0x80):
                break

    return tag_class, number, constructed, offset


def ber_decode_length(data: bytes, offset: int) -> tuple[int, int]:
    """Decode a BER length. Returns (length, new_offset)."""
    if offset >= len(data):
        raise EmberProtocolError("BER: unexpected end of data reading length")
    b = data[offset]
    offset += 1

    if b == 0x80:
        return -1, offset

    if b < 0x80:
        return b, offset

    num_bytes = b & 0x7F
    length = 0
    for _ in range(num_bytes):
        if offset >= len(data):
            raise EmberProtocolError(
                "BER: unexpected end of data reading length bytes"
            )
        length = (length << 8) | data[offset]
        offset += 1

    return length, offset


def ber_decode_boolean(data: bytes, offset: int, length: int) -> bool:
    """Decode a BER BOOLEAN value."""
    if length < 1:
        return False
    return data[offset] != 0x00


def ber_decode_integer(data: bytes, offset: int, length: int) -> int:
    """Decode a BER INTEGER value."""
    if length == 0:
        return 0
    return int.from_bytes(data[offset : offset + length], "big", signed=True)


def ber_decode_utf8(data: bytes, offset: int, length: int) -> str:
    """Decode a BER UTF8String value."""
    return data[offset : offset + length].decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Glow DTD tags
# ---------------------------------------------------------------------------

GLOW_TAG_ROOT_ELEMENT_COLLECTION = ber_encode_tag(
    BER_CLASS_APPLICATION, True, 11
)
GLOW_TAG_QUALIFIED_NODE = ber_encode_tag(BER_CLASS_APPLICATION, True, 10)
GLOW_TAG_QUALIFIED_PARAM = ber_encode_tag(BER_CLASS_APPLICATION, True, 9)
GLOW_TAG_COMMAND = ber_encode_tag(BER_CLASS_APPLICATION, True, 2)

# Context tags for QualifiedNode
GLOW_CTX_NODE_PATH = ber_encode_tag(BER_CLASS_CONTEXT, False, 0)
GLOW_CTX_NODE_CONTENTS = ber_encode_tag(BER_CLASS_CONTEXT, True, 1)
GLOW_CTX_NODE_CHILDREN = ber_encode_tag(BER_CLASS_CONTEXT, True, 2)

# Context tags for QualifiedParameter
GLOW_CTX_PARAM_PATH = ber_encode_tag(BER_CLASS_CONTEXT, False, 0)
GLOW_CTX_PARAM_CONTENTS = ber_encode_tag(BER_CLASS_CONTEXT, True, 1)

# Context tags for Parameter contents
GLOW_CTX_PARAM_VALUE = ber_encode_tag(BER_CLASS_CONTEXT, False, 2)

# Command numbers
GLOW_CMD_DIR = 32
GLOW_CMD_SUBSCRIBE = 30
GLOW_CMD_UNSUBSCRIBE = 31


# ---------------------------------------------------------------------------
# Glow message builders
# ---------------------------------------------------------------------------

def _encode_oid(path: list[int]) -> bytes:
    """Encode a path as a RELATIVE-OID BER value."""
    result = bytearray()
    for component in path:
        if component < 0x80:
            result.append(component)
        else:
            parts: list[int] = []
            n = component
            while n > 0:
                parts.append(n & 0x7F)
                n >>= 7
            parts.reverse()
            for i, p in enumerate(parts):
                if i < len(parts) - 1:
                    result.append(p | 0x80)
                else:
                    result.append(p)
    return bytes(result)


def build_get_directory(path: list[int] | None = None) -> bytes:
    """Build a Glow getDirectory command for a given path."""
    # ElementCollection.element tag = Context[0]
    elem_tag = ber_encode_tag(BER_CLASS_CONTEXT, True, 0)

    cmd_number = ber_encode_integer(GLOW_CMD_DIR)
    cmd_contents = ber_tlv(
        ber_encode_tag(BER_CLASS_CONTEXT, False, 0),
        cmd_number,
    )
    command = ber_tlv(GLOW_TAG_COMMAND, cmd_contents)

    if path is None:
        # Root: RootElementCollection > Command
        return ber_tlv(GLOW_TAG_ROOT_ELEMENT_COLLECTION, command)

    oid = _encode_oid(path)
    path_tlv = ber_tlv(
        GLOW_CTX_NODE_PATH,
        bytes([0x0D]) + ber_encode_length(len(oid)) + oid,
    )
    # Wrap command in elementCollection.element > Command
    cmd_in_elem = ber_tlv(elem_tag, command)
    children_tlv = ber_tlv(
        GLOW_CTX_NODE_CHILDREN,
        ber_tlv(
            ber_encode_tag(BER_CLASS_APPLICATION, True, 4),
            cmd_in_elem,
        ),
    )
    # Wrap QualifiedNode in elementCollection.element
    node = ber_tlv(GLOW_TAG_QUALIFIED_NODE, path_tlv + children_tlv)
    wrapped = ber_tlv(elem_tag, node)
    return ber_tlv(GLOW_TAG_ROOT_ELEMENT_COLLECTION, wrapped)


def build_set_value(path: list[int], value: bool) -> bytes:
    """Build a Glow setValue command for a boolean parameter."""
    oid = _encode_oid(path)
    path_tlv = ber_tlv(
        GLOW_CTX_PARAM_PATH,
        bytes([0x0D]) + ber_encode_length(len(oid)) + oid,
    )
    value_tlv = ber_tlv(
        GLOW_CTX_PARAM_CONTENTS,
        ber_tlv(
            GLOW_CTX_PARAM_VALUE,
            ber_encode_boolean(value),
        ),
    )
    param = ber_tlv(GLOW_TAG_QUALIFIED_PARAM, path_tlv + value_tlv)
    return ber_tlv(GLOW_TAG_ROOT_ELEMENT_COLLECTION, param)


def build_subscribe(path: list[int]) -> bytes:
    """Build a Glow subscribe command for a node path."""
    cmd_number = ber_encode_integer(GLOW_CMD_SUBSCRIBE)
    cmd_contents = ber_tlv(
        ber_encode_tag(BER_CLASS_CONTEXT, False, 0),
        cmd_number,
    )
    command = ber_tlv(GLOW_TAG_COMMAND, cmd_contents)

    oid = _encode_oid(path)
    path_tlv = ber_tlv(
        GLOW_CTX_NODE_PATH,
        bytes([0x0D]) + ber_encode_length(len(oid)) + oid,
    )
    children_tlv = ber_tlv(
        GLOW_CTX_NODE_CHILDREN,
        ber_tlv(
            ber_encode_tag(BER_CLASS_APPLICATION, True, 4),
            command,
        ),
    )
    node = ber_tlv(GLOW_TAG_QUALIFIED_NODE, path_tlv + children_tlv)
    return ber_tlv(GLOW_TAG_ROOT_ELEMENT_COLLECTION, node)


# ---------------------------------------------------------------------------
# Glow response parser
# ---------------------------------------------------------------------------

class EmberNode:
    """Represents a node or parameter in the Ember+ tree."""

    def __init__(self) -> None:
        self.path: list[int] = []
        self.identifier: str = ""
        self.description: str = ""
        self.value: Any = None
        self.access: int = 0
        self.children: dict[str, EmberNode] = {}
        self.is_parameter: bool = False

    def __repr__(self) -> str:
        if self.is_parameter:
            return f"Param({self.identifier}={self.value})"
        return f"Node({self.identifier}, children={len(self.children)})"


def parse_glow_response(data: bytes) -> list[EmberNode]:
    """Parse a Glow response and extract nodes/parameters."""
    nodes: list[EmberNode] = []
    try:
        _parse_element(data, 0, len(data), nodes)
    except Exception as exc:
        _LOGGER.debug("Error parsing Glow response: %s", exc)
    return nodes


def _parse_element(
    data: bytes, offset: int, end: int, nodes: list[EmberNode]
) -> None:
    """Recursively parse BER elements from a Glow response."""
    while offset < end:
        if offset >= len(data):
            break

        # Stop on zero-padding (DHD pads frames with 0x00 bytes)
        if data[offset] == 0x00:
            break

        try:
            tag_class, tag_number, constructed, new_offset = ber_decode_tag(
                data, offset
            )
            length, new_offset = ber_decode_length(data, new_offset)
        except EmberProtocolError:
            break

        offset = new_offset

        if length == -1:
            content_end = _find_eoc(data, offset)
        else:
            content_end = offset + length

        if content_end > len(data):
            break

        if tag_class == BER_CLASS_APPLICATION and constructed:
            if tag_number == 10:
                node = _parse_qualified_node(data, offset, content_end)
                if node:
                    nodes.append(node)
            elif tag_number == 9:
                node = _parse_qualified_parameter(data, offset, content_end)
                if node:
                    nodes.append(node)
            else:
                # RootElementCollection(11), ElementCollection(4), etc.
                _parse_element(data, offset, content_end, nodes)
        elif constructed:
            _parse_element(data, offset, content_end, nodes)

        offset = content_end
        if length == -1:
            offset += 2  # skip EOC (0x00, 0x00)


def _find_eoc(data: bytes, offset: int) -> int:
    """Find end-of-contents (0x00, 0x00) for indefinite length."""
    pos = offset
    while pos < len(data) - 1:
        if data[pos] == 0x00 and data[pos + 1] == 0x00:
            return pos
        pos += 1
    return len(data)


def _parse_path(data: bytes, offset: int, length: int) -> list[int]:
    """Parse a RELATIVE-OID encoded path."""
    pos = offset
    end_pos = offset + length
    if pos < end_pos and data[pos] == 0x0D:
        pos += 1
        oid_len, pos = ber_decode_length(data, pos)
        end_pos = pos + oid_len

    path: list[int] = []
    component = 0
    while pos < end_pos:
        b = data[pos]
        component = (component << 7) | (b & 0x7F)
        if not (b & 0x80):
            path.append(component)
            component = 0
        pos += 1
    return path


def _parse_qualified_node(
    data: bytes, offset: int, end: int
) -> EmberNode | None:
    """Parse a QualifiedNode element."""
    node = EmberNode()
    pos = offset

    while pos < end:
        if pos >= len(data) or data[pos] == 0x00:
            break
        try:
            tag_class, tag_number, constructed, pos = ber_decode_tag(data, pos)
            length, pos = ber_decode_length(data, pos)
        except EmberProtocolError:
            break
        content_end = pos + length if length >= 0 else _find_eoc(data, pos)

        if tag_class == BER_CLASS_CONTEXT:
            if tag_number == 0:
                node.path = _parse_path(data, pos, content_end - pos)
            elif tag_number == 1 and constructed:
                _parse_node_contents(data, pos, content_end, node)
            elif tag_number == 2 and constructed:
                child_nodes: list[EmberNode] = []
                _parse_element(data, pos, content_end, child_nodes)
                for child in child_nodes:
                    node.children[child.identifier] = child

        pos = content_end
        if length == -1:
            pos += 2

    return node if node.path else None


def _parse_qualified_parameter(
    data: bytes, offset: int, end: int
) -> EmberNode | None:
    """Parse a QualifiedParameter element."""
    node = EmberNode()
    node.is_parameter = True
    pos = offset

    while pos < end:
        if pos >= len(data) or data[pos] == 0x00:
            break
        try:
            tag_class, tag_number, constructed, pos = ber_decode_tag(data, pos)
            length, pos = ber_decode_length(data, pos)
        except EmberProtocolError:
            break
        content_end = pos + length if length >= 0 else _find_eoc(data, pos)

        if tag_class == BER_CLASS_CONTEXT:
            if tag_number == 0:
                node.path = _parse_path(data, pos, content_end - pos)
            elif tag_number == 1 and constructed:
                _parse_param_contents(data, pos, content_end, node)

        pos = content_end
        if length == -1:
            pos += 2

    return node if node.path else None


def _parse_node_contents(
    data: bytes, offset: int, end: int, node: EmberNode
) -> None:
    """Parse the contents SET of a node."""
    pos = offset
    while pos < end:
        if pos >= len(data) or data[pos] == 0x00:
            break
        try:
            tag_class, tag_number, constructed, pos = ber_decode_tag(data, pos)
            length, pos = ber_decode_length(data, pos)
        except EmberProtocolError:
            break
        content_end = pos + length if length >= 0 else _find_eoc(data, pos)

        if tag_class == BER_CLASS_UNIVERSAL and constructed:
            # SET or SEQUENCE wrapper — recurse into it
            _parse_node_contents(data, pos, content_end, node)
        elif tag_class == BER_CLASS_CONTEXT:
            if tag_number == 0:
                node.identifier = _decode_string_value(
                    data, pos, content_end
                )
            elif tag_number == 1:
                node.description = _decode_string_value(
                    data, pos, content_end
                )

        pos = content_end
        if length == -1:
            pos += 2


def _parse_param_contents(
    data: bytes, offset: int, end: int, node: EmberNode
) -> None:
    """Parse the contents SET of a parameter.

    DHD wraps contents in: Context[1] > SET > Context[n] > value.
    The SET may use indefinite length.
    """
    pos = offset
    while pos < end:
        if pos >= len(data) or data[pos] == 0x00:
            break
        try:
            tag_class, tag_number, constructed, pos = ber_decode_tag(data, pos)
            length, pos = ber_decode_length(data, pos)
        except EmberProtocolError:
            break
        content_end = pos + length if length >= 0 else _find_eoc(data, pos)

        if tag_class == BER_CLASS_UNIVERSAL and constructed:
            # SET or SEQUENCE wrapper — recurse into it
            _parse_param_contents(data, pos, content_end, node)
        elif tag_class == BER_CLASS_CONTEXT:
            if tag_number == 0:
                node.identifier = _decode_string_value(
                    data, pos, content_end
                )
            elif tag_number == 1:
                node.description = _decode_string_value(
                    data, pos, content_end
                )
            elif tag_number == 2:
                if constructed:
                    # Value is wrapped in a constructed context tag
                    node.value = _decode_value(data, pos, content_end)
                else:
                    node.value = _decode_value(data, pos, content_end)
            elif tag_number == 3:
                if constructed:
                    node.access = _decode_integer_value(data, pos, content_end)
                else:
                    node.access = ber_decode_integer(
                        data, pos, content_end - pos
                    )

        pos = content_end
        if length == -1:
            pos += 2


def _decode_value(data: bytes, offset: int, end: int) -> Any:
    """Decode a BER-encoded value (boolean, integer, or string)."""
    if offset >= end or data[offset] == 0x00:
        return None
    try:
        tag_class, tag_number, constructed, pos = ber_decode_tag(data, offset)
        length, pos = ber_decode_length(data, pos)
    except EmberProtocolError:
        return None
    if tag_class == BER_CLASS_UNIVERSAL:
        if tag_number == BER_TAG_BOOLEAN:
            return ber_decode_boolean(data, pos, length)
        if tag_number == BER_TAG_INTEGER:
            return ber_decode_integer(data, pos, length)
        if tag_number == BER_TAG_UTF8STRING:
            return ber_decode_utf8(data, pos, length)
    return data[pos : pos + length] if length > 0 else None


def _clean_string(s: str) -> str:
    """Remove non-printable characters from a decoded string."""
    return "".join(c for c in s if c.isprintable() or c in (" ", "\t")).strip()


def _decode_string_value(data: bytes, offset: int, end: int) -> str:
    """Decode a BER UTF8String value, possibly wrapped in a constructed tag."""
    if offset >= end or data[offset] == 0x00:
        return ""
    try:
        tag_class, tag_number, constructed, pos = ber_decode_tag(data, offset)
        length, pos = ber_decode_length(data, pos)
    except EmberProtocolError:
        return ""
    if tag_class == BER_CLASS_UNIVERSAL and tag_number == BER_TAG_UTF8STRING:
        return _clean_string(ber_decode_utf8(data, pos, length))
    # Fallback: try to read as raw string
    if length > 0:
        return _clean_string(
            data[pos : pos + length].decode("utf-8", errors="replace")
        )
    return ""


def _decode_integer_value(data: bytes, offset: int, end: int) -> int:
    """Decode a BER INTEGER value, possibly wrapped in a constructed tag."""
    if offset >= end or data[offset] == 0x00:
        return 0
    try:
        tag_class, tag_number, constructed, pos = ber_decode_tag(data, offset)
        length, pos = ber_decode_length(data, pos)
    except EmberProtocolError:
        return 0
    if tag_class == BER_CLASS_UNIVERSAL and tag_number == BER_TAG_INTEGER:
        return ber_decode_integer(data, pos, length)
    return 0


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class EmberProtocolError(Exception):
    """Raised when the Ember+ protocol encounters an error."""


class EmberConnectionError(Exception):
    """Raised when the connection to the Ember+ device fails."""


# ---------------------------------------------------------------------------
# High-level async Ember+ client
# ---------------------------------------------------------------------------

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 10
DEFAULT_EMBER_PORT = 9000


class EmberClient:
    """Async TCP client for DHD Ember+ protocol.

    Connects to a DHD mixer on TCP port 9000, discovers the Ember+ tree,
    and provides high-level methods for reading/writing GPI and GPO states.
    """

    def __init__(self, host: str, port: int = DEFAULT_EMBER_PORT) -> None:
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._listener_task: asyncio.Task[None] | None = None
        self._response_queue: asyncio.Queue[bytes] = asyncio.Queue()

        # Current states
        self._gpi_states: dict[int, bool] = {}
        self._gpo_states: dict[int, bool] = {}
        self._gpi_labels: dict[int, str] = {}
        self._gpo_labels: dict[int, str] = {}

        # Push callback: callback(io_type: str, number: int, state: bool)
        self._state_callback: Callable[[str, int, bool], None] | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def host(self) -> str:
        """Return the configured host."""
        return self._host

    @property
    def port(self) -> int:
        """Return the configured port."""
        return self._port

    @property
    def connected(self) -> bool:
        """Return True when the TCP socket is open."""
        return self._writer is not None and not self._writer.is_closing()

    @property
    def gpi_states(self) -> dict[int, bool]:
        """Return a copy of all GPI states."""
        return dict(self._gpi_states)

    @property
    def gpo_states(self) -> dict[int, bool]:
        """Return a copy of all GPO states."""
        return dict(self._gpo_states)

    @property
    def gpi_labels(self) -> dict[int, str]:
        """Return a copy of all GPI labels."""
        return dict(self._gpi_labels)

    @property
    def gpo_labels(self) -> dict[int, str]:
        """Return a copy of all GPO labels."""
        return dict(self._gpo_labels)

    def set_state_callback(
        self, callback: Callable[[str, int, bool], None]
    ) -> None:
        """Register a callback for state changes.

        Args:
            callback: Called with (io_type, number, state) where
                      io_type is "gpi" or "gpo".
        """
        self._state_callback = callback

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open a TCP connection to the Ember+ provider."""
        if self.connected:
            return

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=CONNECT_TIMEOUT,
            )
            _LOGGER.debug(
                "Connected to DHD Ember+ at %s:%s", self._host, self._port
            )
        except (OSError, asyncio.TimeoutError) as err:
            self._reader = None
            self._writer = None
            raise EmberConnectionError(
                f"Failed to connect to {self._host}:{self._port}"
            ) from err

        self._start_listener()

    async def disconnect(self) -> None:
        """Close the TCP connection."""
        self._stop_listener()

        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            finally:
                self._writer = None
                self._reader = None
                _LOGGER.debug(
                    "Disconnected from DHD Ember+ at %s:%s",
                    self._host, self._port,
                )

    async def _ensure_connected(self) -> None:
        """Reconnect if the socket was closed."""
        if not self.connected:
            await self.connect()

    async def test_connection(self) -> bool:
        """Test connectivity by opening the TCP socket."""
        await self._ensure_connected()
        return True

    # ------------------------------------------------------------------
    # Background listener
    # ------------------------------------------------------------------

    def _start_listener(self) -> None:
        """Start the background listener task."""
        if self._listener_task is not None and not self._listener_task.done():
            return
        self._listener_task = asyncio.ensure_future(self._listener_loop())

    def _stop_listener(self) -> None:
        """Cancel the background listener task."""
        if self._listener_task is not None:
            self._listener_task.cancel()
            self._listener_task = None

    async def _listener_loop(self) -> None:
        """Read S101 frames from the TCP stream."""
        assert self._reader is not None
        buf = bytearray()

        try:
            while True:
                try:
                    chunk = await self._reader.read(4096)
                    if not chunk:
                        _LOGGER.warning("Ember+ connection closed by peer")
                        break
                    buf.extend(chunk)
                except asyncio.CancelledError:
                    return
                except Exception:
                    _LOGGER.exception("Error reading from Ember+ stream")
                    break

                # Extract complete S101 frames
                while True:
                    bof_idx = -1
                    for i, b in enumerate(buf):
                        if b == S101_BOF:
                            bof_idx = i
                            break
                    if bof_idx == -1:
                        buf.clear()
                        break

                    eof_idx = -1
                    for i in range(bof_idx + 1, len(buf)):
                        if buf[i] == S101_EOF:
                            eof_idx = i
                            break
                    if eof_idx == -1:
                        if bof_idx > 0:
                            del buf[:bof_idx]
                        break

                    frame = bytes(buf[bof_idx : eof_idx + 1])
                    del buf[: eof_idx + 1]

                    try:
                        payload = s101_decode(frame)
                    except EmberProtocolError as exc:
                        _LOGGER.debug("S101 decode error: %s", exc)
                        continue

                    self._handle_payload(payload)

        except asyncio.CancelledError:
            return
        except Exception:
            _LOGGER.exception("Ember+ listener loop crashed")

    def _handle_payload(self, payload: bytes) -> None:
        """Handle a decoded S101 payload."""
        if len(payload) < 4:
            return

        msg_type = payload[1]
        command = payload[2]

        if msg_type != S101_MSG_EMBER:
            return

        if command == S101_CMD_KEEPALIVE_REQ:
            if self._writer and not self._writer.is_closing():
                self._writer.write(build_keepalive_response())
            return

        if command == S101_CMD_KEEPALIVE_RESP:
            return

        if command == S101_CMD_EMBER:
            if len(payload) < 9:
                return
            app_bytes_len = payload[6]
            ber_start = 7 + app_bytes_len
            ber_data = payload[ber_start:]

            if ber_data:
                nodes = parse_glow_response(ber_data)
                self._process_nodes(nodes)
                self._response_queue.put_nowait(ber_data)

    def _process_nodes(self, nodes: list[EmberNode]) -> None:
        """Process parsed Ember+ nodes and update internal state."""
        for node in nodes:
            if node.is_parameter and node.path:
                self._process_parameter(node)
            if node.children:
                self._process_nodes(list(node.children.values()))

    def _process_parameter(self, param: EmberNode) -> None:
        """Process a single parameter update."""
        path = param.path
        io_type: str | None = None
        number: int | None = None

        # DHD tree: Device(0) > GPI(1) > GPI x(n)
        # DHD tree: Device(0) > GPO(2) > GPO x(n)
        if len(path) >= 3:
            if path[1] == 1:
                io_type = "gpi"
                number = path[2]
            elif path[1] == 2:
                io_type = "gpo"
                number = path[2]

        # Fallback: detect from identifier
        if io_type is None or number is None:
            ident = param.identifier.strip().lower()
            if ident.startswith("gpi"):
                io_type = "gpi"
                try:
                    number = int(ident.replace("gpi", "").strip())
                except ValueError:
                    return
            elif ident.startswith("gpo"):
                io_type = "gpo"
                try:
                    number = int(ident.replace("gpo", "").strip())
                except ValueError:
                    return
            else:
                return

        # Strip leading/trailing whitespace from identifier and description
        clean_ident = param.identifier.strip() if param.identifier else ""
        clean_desc = param.description.strip() if param.description else ""

        if isinstance(param.value, bool):
            old_state = None
            if io_type == "gpi":
                old_state = self._gpi_states.get(number)
                self._gpi_states[number] = param.value
                if clean_desc:
                    self._gpi_labels[number] = clean_desc
                elif clean_ident:
                    self._gpi_labels.setdefault(number, clean_ident)
                else:
                    self._gpi_labels.setdefault(number, f"GPI {number}")
            elif io_type == "gpo":
                old_state = self._gpo_states.get(number)
                self._gpo_states[number] = param.value
                if clean_desc:
                    self._gpo_labels[number] = clean_desc
                elif clean_ident:
                    self._gpo_labels.setdefault(number, clean_ident)
                else:
                    self._gpo_labels.setdefault(number, f"GPO {number}")

            if old_state != param.value and self._state_callback is not None:
                _LOGGER.debug(
                    "Ember+ push: %s %d = %s", io_type, number, param.value,
                )
                try:
                    self._state_callback(io_type, number, param.value)
                except Exception:
                    _LOGGER.exception("Error in state callback")

    # ------------------------------------------------------------------
    # High-level commands
    # ------------------------------------------------------------------

    async def _send_ember(self, glow_data: bytes) -> None:
        """Send a Glow message wrapped in S101."""
        async with self._lock:
            await self._ensure_connected()
            assert self._writer is not None
            frame = build_ember_message(glow_data)
            self._writer.write(frame)
            await self._writer.drain()

    async def discover(self) -> None:
        """Discover the Ember+ tree by recursive getDirectory walk."""
        _LOGGER.debug("Discovering Ember+ tree...")

        # Walk the tree: getDirectory on root, then each discovered node
        visited: set[tuple[int, ...]] = set()
        queue: list[list[int] | None] = [None]  # None = root

        while queue:
            path = queue.pop(0)
            path_key = tuple(path) if path else ()
            if path_key in visited:
                continue
            visited.add(path_key)

            await self._send_ember(build_get_directory(path))
            await asyncio.sleep(0.5)

            # Drain response queue and look for new nodes to walk
            while not self._response_queue.empty():
                try:
                    ber_data = self._response_queue.get_nowait()
                    nodes = parse_glow_response(ber_data)
                    for node in nodes:
                        if node.path and not node.is_parameter:
                            node_path = node.path
                            if tuple(node_path) not in visited:
                                queue.append(node_path)
                except Exception:
                    break

            # Limit depth to avoid infinite loops
            if len(visited) > 200:
                _LOGGER.warning("Ember+ tree walk: depth limit reached")
                break

        # Wait for any remaining push updates
        await asyncio.sleep(2.0)

        _LOGGER.info(
            "Ember+ discovery complete: %d GPIs, %d GPOs",
            len(self._gpi_states), len(self._gpo_states),
        )

    async def subscribe_all(self) -> None:
        """Subscribe to all GPI and GPO changes for push updates."""
        await self._send_ember(build_subscribe([0, 1]))
        await asyncio.sleep(0.2)
        await self._send_ember(build_subscribe([0, 2]))
        await asyncio.sleep(0.2)
        _LOGGER.debug("Subscribed to GPI and GPO changes")

    async def set_gpi_state(self, number: int, state: bool) -> None:
        """Set a GPI to on or off."""
        _LOGGER.debug("Setting GPI %d to %s", number, state)
        glow = build_set_value([0, 1, number], state)
        await self._send_ember(glow)
        self._gpi_states[number] = state
