"""
Leomail v3 — SOCKS5 Auth Bridge
Local HTTP CONNECT proxy that tunnels through authenticated SOCKS5 proxies.
Chromium/Playwright doesn't support SOCKS5 auth natively, so we bridge it.

Usage:
    bridge = Socks5Bridge("proxy_host", 1080, "user", "pass")
    await bridge.start()  # starts on random localhost port
    # Use http://localhost:{bridge.port} as proxy for Playwright (no auth)
    await bridge.stop()
"""
import asyncio
import struct
import random
from loguru import logger


class Socks5Bridge:
    """Local HTTP proxy that chains through an authenticated SOCKS5 upstream."""

    def __init__(self, socks_host: str, socks_port: int, username: str, password: str):
        self.socks_host = socks_host
        self.socks_port = socks_port
        self.username = username
        self.password = password
        self.port = 0  # assigned on start
        self._server = None

    async def start(self):
        """Start local proxy on a random port."""
        self._server = await asyncio.start_server(
            self._handle_client, "127.0.0.1", 0
        )
        self.port = self._server.sockets[0].getsockname()[1]
        logger.debug(f"SOCKS5 bridge started: 127.0.0.1:{self.port} → socks5://{self.socks_host}:{self.socks_port}")
        return self.port

    async def stop(self):
        """Stop the local proxy."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.debug(f"SOCKS5 bridge stopped (port {self.port})")

    async def _socks5_connect(self, target_host: str, target_port: int):
        """
        Connect to target through SOCKS5 proxy with username/password auth.
        Returns (reader, writer) for the tunneled connection.
        """
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.socks_host, self.socks_port),
            timeout=15,
        )

        try:
            # SOCKS5 greeting: version=5, 2 methods (no-auth + user/pass)
            writer.write(b"\x05\x02\x00\x02")
            await writer.drain()

            resp = await asyncio.wait_for(reader.readexactly(2), timeout=10)
            if resp[0] != 0x05:
                raise Exception(f"Bad SOCKS5 version: {resp[0]}")

            if resp[1] == 0x02:
                # Username/Password auth (RFC 1929)
                user_bytes = self.username.encode("utf-8")
                pass_bytes = self.password.encode("utf-8")
                auth_msg = b"\x01" + bytes([len(user_bytes)]) + user_bytes + bytes([len(pass_bytes)]) + pass_bytes
                writer.write(auth_msg)
                await writer.drain()

                auth_resp = await asyncio.wait_for(reader.readexactly(2), timeout=10)
                if auth_resp[1] != 0x00:
                    raise Exception(f"SOCKS5 auth failed (status={auth_resp[1]})")
            elif resp[1] == 0x00:
                pass  # No auth needed
            else:
                raise Exception(f"SOCKS5 unsupported auth method: {resp[1]}")

            # CONNECT request
            host_bytes = target_host.encode("utf-8")
            connect_msg = (
                b"\x05\x01\x00\x03"
                + bytes([len(host_bytes)])
                + host_bytes
                + struct.pack("!H", target_port)
            )
            writer.write(connect_msg)
            await writer.drain()

            # Read response header (4 bytes minimum)
            resp = await asyncio.wait_for(reader.readexactly(4), timeout=10)
            if resp[1] != 0x00:
                error_map = {
                    1: "general failure",
                    2: "connection not allowed",
                    3: "network unreachable",
                    4: "host unreachable",
                    5: "connection refused",
                    6: "TTL expired",
                    7: "command not supported",
                    8: "address type not supported",
                }
                raise Exception(f"SOCKS5 connect failed: {error_map.get(resp[1], f'code {resp[1]}')}")

            # Skip bound address
            atyp = resp[3]
            if atyp == 0x01:  # IPv4
                await reader.readexactly(4 + 2)
            elif atyp == 0x03:  # Domain
                domain_len = (await reader.readexactly(1))[0]
                await reader.readexactly(domain_len + 2)
            elif atyp == 0x04:  # IPv6
                await reader.readexactly(16 + 2)

            return reader, writer

        except Exception:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            raise

    async def _handle_client(self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter):
        """Handle incoming HTTP CONNECT request from Playwright."""
        remote_writer = None
        try:
            # Read the first line (HTTP request)
            first_line = await asyncio.wait_for(client_reader.readline(), timeout=10)
            if not first_line:
                return

            line = first_line.decode("utf-8", errors="ignore").strip()

            if line.upper().startswith("CONNECT"):
                # CONNECT host:port HTTP/1.1
                parts = line.split()
                if len(parts) < 2:
                    return
                target = parts[1]
                if ":" in target:
                    host, port_str = target.rsplit(":", 1)
                    port = int(port_str)
                else:
                    host = target
                    port = 443

                # Read remaining headers (discard)
                while True:
                    header = await asyncio.wait_for(client_reader.readline(), timeout=5)
                    if header in (b"\r\n", b"\n", b""):
                        break

                # Connect through SOCKS5
                remote_reader, remote_writer = await self._socks5_connect(host, port)

                # Send 200 to Playwright
                client_writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                await client_writer.drain()

                # Bridge data
                await self._bridge(client_reader, client_writer, remote_reader, remote_writer)
            else:
                # Plain HTTP request — forward through SOCKS5
                # Parse Host header
                headers_data = first_line
                host = None
                port = 80
                while True:
                    header = await asyncio.wait_for(client_reader.readline(), timeout=5)
                    headers_data += header
                    if header in (b"\r\n", b"\n", b""):
                        break
                    h = header.decode("utf-8", errors="ignore").strip()
                    if h.lower().startswith("host:"):
                        host_val = h.split(":", 1)[1].strip()
                        if ":" in host_val:
                            host, port_str = host_val.rsplit(":", 1)
                            port = int(port_str)
                        else:
                            host = host_val

                if not host:
                    return

                remote_reader, remote_writer = await self._socks5_connect(host, port)
                remote_writer.write(headers_data)
                await remote_writer.drain()

                await self._bridge(client_reader, client_writer, remote_reader, remote_writer)

        except Exception as e:
            logger.debug(f"SOCKS5 bridge connection error: {e}")
        finally:
            client_writer.close()
            try:
                await client_writer.wait_closed()
            except Exception:
                pass
            if remote_writer:
                remote_writer.close()
                try:
                    await remote_writer.wait_closed()
                except Exception:
                    pass

    @staticmethod
    async def _bridge(r1, w1, r2, w2):
        """Bridge two connections bidirectionally."""
        async def pipe(reader, writer):
            try:
                while True:
                    data = await reader.read(65536)
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
            except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
                pass
            except Exception:
                pass

        t1 = asyncio.create_task(pipe(r1, w2))
        t2 = asyncio.create_task(pipe(r2, w1))

        done, pending = await asyncio.wait(
            [t1, t2], return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
