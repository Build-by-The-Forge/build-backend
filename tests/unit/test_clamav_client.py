"""The clamd client against a fake clamd speaking the real protocol (M3-D PR 6)."""

import asyncio
import struct

import pytest

from app.infrastructure.content.clamav import CHUNK, ClamdScanner, ScannerUnavailable

EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


async def fake_clamd(reply_for_stream, version=b"ClamAV 1.4.1/27450/Thu Nov  6 08:00:00 2026\x00"):
    """A clamd that reads INSTREAM chunks as clamd does and answers with
    ``reply_for_stream(received_bytes)``. Returns (server, port, received)."""
    received: list[bytes] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        command = await reader.readuntil(b"\x00")
        if command == b"zVERSION\x00":
            writer.write(version)
        elif command == b"zINSTREAM\x00":
            data = b""
            while True:
                (size,) = struct.unpack("!L", await reader.readexactly(4))
                if size == 0:
                    break
                data += await reader.readexactly(size)
            received.append(data)
            writer.write(reply_for_stream(data))
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1], received


def scanner(port: int, max_bytes: int = 10_000_000) -> ClamdScanner:
    return ClamdScanner("127.0.0.1", port, 2.0, max_bytes)


def answers(data: bytes) -> bytes:
    return b"stream: Eicar-Test-Signature FOUND\x00" if EICAR in data else b"stream: OK\x00"


@pytest.mark.asyncio
async def test_a_clean_file_is_accepted_with_the_scanner_and_signature_version():
    server, port, received = await fake_clamd(answers)
    async with server:
        verdict = await scanner(port).scan(b"%PDF-1.4 clean")
    assert (verdict.clean, verdict.signature, verdict.scanner, verdict.signature_version) == (
        True,
        None,
        "ClamAV 1.4.1",
        "27450",
    )
    assert received == [b"%PDF-1.4 clean"]


@pytest.mark.asyncio
async def test_a_found_signature_is_rejected_with_its_name():
    server, port, _ = await fake_clamd(answers)
    async with server:
        verdict = await scanner(port).scan(EICAR)
    assert (verdict.clean, verdict.signature) == (False, "Eicar-Test-Signature")


@pytest.mark.asyncio
async def test_a_large_file_is_streamed_whole_in_chunks():
    data = bytes(range(256)) * (CHUNK // 256 * 3 + 7)
    server, port, received = await fake_clamd(answers)
    async with server:
        assert (await scanner(port).scan(data)).clean
    assert received == [data]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply,code",
    [
        (b"INSTREAM size limit exceeded. ERROR\x00", "SCANNER_ERROR"),
        (b"stream: something unexpected\x00", "SCANNER_ERROR"),
        (b"", "SCANNER_ERROR"),
    ],
)
async def test_anything_but_ok_or_found_is_no_verdict(reply, code):
    server, port, _ = await fake_clamd(lambda data: reply)
    async with server:
        with pytest.raises(ScannerUnavailable) as raised:
            await scanner(port).scan(b"%PDF")
    assert raised.value.code == code


@pytest.mark.asyncio
async def test_an_unreadable_version_is_no_verdict():
    server, port, _ = await fake_clamd(answers, version=b"not clamav\x00")
    async with server:
        with pytest.raises(ScannerUnavailable) as raised:
            await scanner(port).scan(b"%PDF")
    assert raised.value.code == "SCANNER_BAD_VERSION"


@pytest.mark.asyncio
async def test_an_unreachable_scanner_is_no_verdict():
    server, port, _ = await fake_clamd(answers)
    server.close()
    await server.wait_closed()
    with pytest.raises(ScannerUnavailable) as raised:
        await scanner(port).scan(b"%PDF")
    assert raised.value.code == "SCANNER_UNREACHABLE"


@pytest.mark.asyncio
async def test_a_file_larger_than_the_scanner_reads_is_never_accepted():
    with pytest.raises(ScannerUnavailable) as raised:
        await scanner(1, max_bytes=10).scan(b"x" * 11)
    assert raised.value.code == "SCAN_TOO_LARGE"
