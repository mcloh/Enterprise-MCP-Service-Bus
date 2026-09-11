"""Shared e2e fixtures: a real OPA process, a real JWKS HTTP endpoint + RS256
token signing, and helpers to run the Gateway/Sales servers in-process
against them. No Keycloak available in this environment (no Java) -- see
RI/README.md for exactly what that does and does not validate.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import jwt
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from mcp.client.session import ClientSession
from mcp.client.streamable_http import (  # type: ignore[attr-defined]
    create_mcp_http_client,
    streamable_http_client,
)
from mcp.shared.exceptions import MCPError

REPO_ROOT = Path(__file__).parents[2]
POLICIES_DIR = REPO_ROOT / "config" / "policies"

ISSUER = "https://keycloak.example/realms/emcp"
AUDIENCE = "emcp-gateway"
KID = "test-key-1"

GATEWAY_PORT = 18000
SALES_PORT = 18100


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


# --- Real OPA process (EP-03) --------------------------------------------


@pytest.fixture(scope="session")
def opa_url() -> Iterator[str]:
    opa_binary = shutil.which(os.environ.get("OPA_BINARY", "opa"))
    if opa_binary is None:
        pytest.skip(
            "opa binary not found on PATH (set OPA_BINARY or install it -- see RI/README.md)"
        )

    port = free_port()
    process = subprocess.Popen(
        [opa_binary, "run", "--server", "--addr", f"127.0.0.1:{port}", str(POLICIES_DIR)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        import httpx

        for _ in range(100):
            try:
                httpx.get(f"{base_url}/health", timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(0.05)
        else:
            raise RuntimeError("opa server did not become healthy in time")
        yield base_url
    finally:
        process.terminate()
        process.wait(timeout=5)


# --- Real JWKS HTTP endpoint + RS256 signing (EP-01-T03) ------------------


class _JWKSHandler(BaseHTTPRequestHandler):
    jwks_document: dict[str, object] = {}

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps(self.jwks_document).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture(scope="session")
def rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(scope="session")
def jwks_url(rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]) -> Iterator[str]:
    _, public_key = rsa_keypair
    jwk = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    _JWKSHandler.jwks_document = {"keys": [jwk]}

    server = HTTPServer(("127.0.0.1", 0), _JWKSHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/jwks"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def sign_token(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> Callable[..., str]:
    private_key, _ = rsa_keypair

    def _sign(
        client_id: str,
        *,
        issuer: str = ISSUER,
        audience: str = AUDIENCE,
        expires_in_seconds: int = 300,
        signing_key: rsa.RSAPrivateKey | None = None,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": issuer,
            "aud": audience,
            "sub": f"service-account-{client_id}",
            "azp": client_id,
            "iat": now,
            "exp": now + expires_in_seconds,
        }
        return jwt.encode(
            claims, signing_key or private_key, algorithm="RS256", headers={"kid": KID}
        )

    return _sign


# --- Running Gateway + Sales servers, wired to the fixtures above --------


class RunningServer:
    def __init__(self, config: uvicorn.Config) -> None:
        self.server = uvicorn.Server(config)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self.server.serve())
        while not self.server.started:
            await asyncio.sleep(0.01)
        # See test_walking_skeleton.py's original note: give the ASGI app's
        # own lifespan (session manager task group) one extra tick.
        await asyncio.sleep(0.05)

    async def stop(self) -> None:
        self.server.should_exit = True
        assert self._task is not None
        await self._task


@pytest.fixture
async def governed_stack(
    monkeypatch: pytest.MonkeyPatch, opa_url: str, jwks_url: str
) -> AsyncIterator[None]:
    """Real OPA + real JWKS-backed OIDC auth, wired into fresh Gateway/Sales
    instances for one test (EP-01/EP-03/EP-04/EP-05 all real, only Keycloak
    itself is substituted by the JWKS server -- see RI/README.md)."""
    monkeypatch.setenv("SALES_DOMAIN_URL", f"http://127.0.0.1:{SALES_PORT}/mcp")
    monkeypatch.setenv("OPA_URL", opa_url)
    monkeypatch.setenv("OIDC_JWKS_URL", jwks_url)
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)

    import example_mcp_servers.sales_domain.server as sales_module

    sales_config = uvicorn.Config(
        sales_module.server.streamable_http_app(host="127.0.0.1"),
        host="127.0.0.1",
        port=SALES_PORT,
        log_level="warning",
    )
    sales_server = RunningServer(sales_config)
    await sales_server.start()

    import emcp_bus.gateway.server as gateway_module

    auth_settings, token_verifier = gateway_module.build_auth()
    gateway_config = uvicorn.Config(
        gateway_module.server.streamable_http_app(
            host="127.0.0.1", auth=auth_settings, token_verifier=token_verifier
        ),
        host="127.0.0.1",
        port=GATEWAY_PORT,
        log_level="warning",
    )
    gateway_server = RunningServer(gateway_config)
    await gateway_server.start()

    try:
        yield
    finally:
        await gateway_server.stop()
        await sales_server.stop()


async def run_against_gateway[ResultT](
    operation: Callable[[ClientSession], Awaitable[ResultT]],
    *,
    token: str | None = None,
) -> ResultT:
    """Connect to the gateway (optionally authenticated) and run `operation(session)`.

    Retries on `MCPError` ("SSE stream ended without a response" has been
    observed, rarely, under this in-process dual-uvicorn test setup under
    scheduler contention) -- a test-harness robustness concern, not a
    Gateway defect: production deployments run one process per service.
    """
    headers = {"Authorization": f"Bearer {token}"} if token else None
    url = f"http://127.0.0.1:{GATEWAY_PORT}/mcp"
    last_error: MCPError | None = None
    for attempt in range(3):
        if attempt:
            await asyncio.sleep(0.1 * attempt)
        try:
            async with (
                create_mcp_http_client(headers=headers) as http_client,
                streamable_http_client(url, http_client=http_client) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                return await operation(session)
        except MCPError as exc:
            last_error = exc
        except BaseExceptionGroup as group:
            # Each nested anyio TaskGroup (`streamable_http_client`'s, then
            # `ClientSession`'s) wraps the one below it in its own
            # ExceptionGroup, so a handler-raised MCPError (e.g. an auth
            # rejection during `initialize`) can arrive doubly-wrapped.
            # Unwrap fully so callers can `pytest.raises(MCPError)`
            # uniformly, same as for one raised directly.
            unwrapped = _unwrap_single_mcp_error(group)
            if unwrapped is not None:
                last_error = unwrapped
            else:
                raise
    assert last_error is not None
    raise last_error


def _unwrap_single_mcp_error(exc: BaseException) -> MCPError | None:
    """If `exc` is an MCPError, or a (possibly nested) ExceptionGroup wrapping
    exactly one, return it; otherwise `None`."""
    if isinstance(exc, MCPError):
        return exc
    if isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        return _unwrap_single_mcp_error(exc.exceptions[0])
    return None
