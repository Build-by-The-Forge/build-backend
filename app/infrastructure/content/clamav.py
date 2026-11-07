"""A clamd client over TCP (M3-D PR 6, ruling 7).

The worker streams a document's bytes with INSTREAM and reads one verdict
line. Self-hosted ClamAV: no third party receives the file. Anything other
than a clean "OK" or a "FOUND" verdict is an error, and the document stays
quarantined: the scan fails closed.

Protocol (clamd(8)): commands are prefixed with "z" and end with NUL.
INSTREAM takes chunks, each a 4-byte big-endian length then the bytes, and
a zero-length chunk to finish; the reply is "stream: OK", "stream: <name>
FOUND" or "... ERROR". VERSION replies "ClamAV <engine>/<signatures>/<date>".
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass

CHUNK = 64 * 1024


class ScannerUnavailable(Exception):
    """No verdict: unreachable, timed out, refused, or an answer we can't read."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class Verdict:
    clean: bool
    # The scanner's signature name for a rejected file; never shown to the uploader.
    signature: str | None
    scanner: str
    signature_version: str


class ClamdScanner:
    def __init__(self, host: str, port: int, timeout_seconds: float, max_bytes: int) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes

    async def _exchange(self, writes: list[bytes]) -> str:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(self._host, self._port), self._timeout)
        except (OSError, TimeoutError) as exc:
            raise ScannerUnavailable("SCANNER_UNREACHABLE") from exc
        try:
            for data in writes:
                writer.write(data)
                await asyncio.wait_for(writer.drain(), self._timeout)
            reply = await asyncio.wait_for(reader.read(4096), self._timeout)
        except (OSError, TimeoutError) as exc:
            raise ScannerUnavailable("SCANNER_TIMEOUT") from exc
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
        return reply.rstrip(b"\x00\n").decode("utf-8", errors="replace")

    async def version(self) -> tuple[str, str]:
        """(scanner, signature version), e.g. ("ClamAV 1.4.1", "27450")."""
        reply = await self._exchange([b"zVERSION\x00"])
        parts = reply.split("/")
        if len(parts) < 2 or not parts[0].startswith("ClamAV") or not parts[1].strip():
            raise ScannerUnavailable("SCANNER_BAD_VERSION")
        return parts[0].strip()[:100], parts[1].strip()[:100]

    async def scan(self, data: bytes) -> Verdict:
        if len(data) > self._max_bytes:
            # Larger than the scanner is configured to read: never accepted unscanned.
            raise ScannerUnavailable("SCAN_TOO_LARGE")
        scanner, signature_version = await self.version()
        writes = [b"zINSTREAM\x00"]
        for start in range(0, len(data), CHUNK):
            chunk = data[start : start + CHUNK]
            writes.append(struct.pack("!L", len(chunk)) + chunk)
        writes.append(struct.pack("!L", 0))
        reply = await self._exchange(writes)
        if reply == "stream: OK":
            return Verdict(True, None, scanner, signature_version)
        if reply.startswith("stream: ") and reply.endswith(" FOUND"):
            name = reply[len("stream: ") : -len(" FOUND")].strip()
            return Verdict(False, name[:200] or "unknown", scanner, signature_version)
        # "INSTREAM size limit exceeded. ERROR", or anything else: no verdict.
        raise ScannerUnavailable("SCANNER_ERROR")
