"""Tests for the DHD Ember+ protocol client."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.dhd_ember.ember import (
    EmberClient,
    EmberConnectionError,
    EmberProtocolError,
    _crc_ccitt16,
    ber_encode_boolean,
    ber_encode_integer,
    ber_encode_length,
    ber_encode_tag,
    ber_encode_utf8,
    s101_decode,
    s101_encode,
    BER_CLASS_APPLICATION,
    BER_CLASS_CONTEXT,
    BER_CLASS_UNIVERSAL,
    S101_BOF,
    S101_EOF,
)


class TestCRC:
    """Tests for CRC-CCITT16."""

    def test_empty(self) -> None:
        """CRC of empty data should be the init value."""
        assert _crc_ccitt16(b"") == 0xFFFF

    def test_known_value(self) -> None:
        """CRC should produce consistent results."""
        crc1 = _crc_ccitt16(b"\x00\x0E\x00\x01")
        crc2 = _crc_ccitt16(b"\x00\x0E\x00\x01")
        assert crc1 == crc2
        assert isinstance(crc1, int)


class TestS101Framing:
    """Tests for S101 encode/decode."""

    def test_round_trip(self) -> None:
        """Encoding then decoding must yield the original payload."""
        payload = bytes([0x00, 0x0E, 0x00, 0x01, 0xC0, 0x01, 0x02, 0x02, 0x1F])
        frame = s101_encode(payload)
        assert frame[0] == S101_BOF
        assert frame[-1] == S101_EOF
        decoded = s101_decode(frame)
        assert decoded == payload

    def test_escaping(self) -> None:
        """Bytes >= 0xF8 must be escaped in the frame."""
        payload = bytes([0xFF, 0xFE, 0xFD, 0xF8])
        frame = s101_encode(payload)
        # The raw payload bytes should not appear unescaped
        inner = frame[1:-1]  # strip BOF/EOF
        assert 0xFF not in inner
        assert 0xFE not in inner
        decoded = s101_decode(frame)
        assert decoded == payload

    def test_invalid_frame_no_bof(self) -> None:
        """A frame without BOF must raise."""
        with pytest.raises(EmberProtocolError):
            s101_decode(b"\x00\x01\xFF")

    def test_invalid_frame_no_eof(self) -> None:
        """A frame without EOF must raise."""
        with pytest.raises(EmberProtocolError):
            s101_decode(b"\xFE\x00\x01")

    def test_crc_mismatch(self) -> None:
        """A frame with corrupted CRC must raise."""
        payload = b"\x00\x0E\x00\x01"
        frame = bytearray(s101_encode(payload))
        # Corrupt a byte in the middle
        if len(frame) > 3:
            frame[2] ^= 0x01
        with pytest.raises(EmberProtocolError, match="CRC"):
            s101_decode(bytes(frame))


class TestBEREncoding:
    """Tests for BER encoding helpers."""

    def test_encode_boolean_true(self) -> None:
        assert ber_encode_boolean(True) == b"\x01\x01\xFF"

    def test_encode_boolean_false(self) -> None:
        assert ber_encode_boolean(False) == b"\x01\x01\x00"

    def test_encode_integer_zero(self) -> None:
        assert ber_encode_integer(0) == b"\x02\x01\x00"

    def test_encode_integer_positive(self) -> None:
        encoded = ber_encode_integer(32)
        assert encoded[0] == 0x02  # INTEGER tag
        assert encoded[-1] == 32

    def test_encode_utf8(self) -> None:
        encoded = ber_encode_utf8("GPI 1")
        assert encoded[0] == 0x0C  # UTF8String tag
        assert b"GPI 1" in encoded

    def test_encode_length_short(self) -> None:
        assert ber_encode_length(5) == b"\x05"
        assert ber_encode_length(127) == b"\x7F"

    def test_encode_length_long(self) -> None:
        encoded = ber_encode_length(256)
        assert encoded[0] & 0x80  # long form flag

    def test_encode_tag_short(self) -> None:
        tag = ber_encode_tag(BER_CLASS_CONTEXT, False, 0)
        assert tag == bytes([0x80])

    def test_encode_tag_constructed(self) -> None:
        tag = ber_encode_tag(BER_CLASS_APPLICATION, True, 11)
        assert tag[0] & 0x20  # constructed flag


class TestConnection:
    """Tests for EmberClient connect/disconnect."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        client = EmberClient("127.0.0.1", 9000)

        mock_reader = MagicMock(spec=asyncio.StreamReader)
        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_writer.is_closing.return_value = False

        with patch(
            "custom_components.dhd_ember.ember.asyncio.open_connection",
            return_value=(mock_reader, mock_writer),
        ):
            await client.connect()

        assert client.connected is True

    @pytest.mark.asyncio
    async def test_connect_failure_raises(self) -> None:
        client = EmberClient("192.0.2.1", 9000)

        with patch(
            "custom_components.dhd_ember.ember.asyncio.open_connection",
            side_effect=OSError("Connection refused"),
        ):
            with pytest.raises(EmberConnectionError):
                await client.connect()

        assert client.connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        client = EmberClient("127.0.0.1", 9000)

        mock_reader = MagicMock(spec=asyncio.StreamReader)
        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_writer.is_closing.return_value = False
        mock_writer.wait_closed = AsyncMock()

        with patch(
            "custom_components.dhd_ember.ember.asyncio.open_connection",
            return_value=(mock_reader, mock_writer),
        ):
            await client.connect()

        await client.disconnect()
        assert client.connected is False

    @pytest.mark.asyncio
    async def test_set_gpi_state(self) -> None:
        """set_gpi_state should update internal state optimistically."""
        client = EmberClient("127.0.0.1", 9000)
        client._send_ember = AsyncMock()
        await client.set_gpi_state(1, True)
        assert client.gpi_states[1] is True
        client._send_ember.assert_awaited_once()
