"""TokenValidator against a real JWKS HTTP endpoint and real RS256-signed
tokens (EP-01-T03) -- no Keycloak available in this environment (no Java),
so a local JWKS server + self-issued tokens exercise the actual OIDC
validation logic (signature, expiry, issuer, audience) that Keycloak would
otherwise be the source of. See RI/README.md for what this does and does
not prove.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from emcp_bus.identity.authn import AuthenticationError, TokenValidator

ISSUER = "https://keycloak.example/realms/emcp"
AUDIENCE = "emcp-gateway"
KID = "test-key-1"


class _JWKSHandler(BaseHTTPRequestHandler):
    jwks_document: dict[str, object] = {}

    def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's naming convention
        body = json.dumps(self.jwks_document).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 -- stdlib signature
        pass  # keep test output quiet


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(scope="module")
def jwks_server(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> Iterator[str]:
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


def _sign_token(
    private_key: rsa.RSAPrivateKey,
    *,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    client_id: str = "sales-read-agent",
    expires_in_seconds: int = 300,
    client_id_claim: str = "azp",
) -> str:
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": "service-account-sales-read-agent",
        client_id_claim: client_id,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})


def test_valid_token_resolves_the_authenticated_client_id(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], jwks_server: str
) -> None:
    private_key, _ = rsa_keypair
    token = _sign_token(private_key, client_id="sales-write-agent")

    validator = TokenValidator(jwks_url=jwks_server, issuer=ISSUER, audience=AUDIENCE)
    authenticated = validator.validate(token)

    assert authenticated.client_id == "sales-write-agent"
    assert authenticated.issuer == ISSUER


def test_client_id_claim_fallback_when_azp_absent(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], jwks_server: str
) -> None:
    private_key, _ = rsa_keypair
    token = _sign_token(private_key, client_id="sales-write-agent", client_id_claim="client_id")

    validator = TokenValidator(jwks_url=jwks_server, issuer=ISSUER, audience=AUDIENCE)
    authenticated = validator.validate(token)

    assert authenticated.client_id == "sales-write-agent"


def test_expired_token_is_rejected(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], jwks_server: str
) -> None:
    private_key, _ = rsa_keypair
    token = _sign_token(private_key, expires_in_seconds=-3600)

    validator = TokenValidator(jwks_url=jwks_server, issuer=ISSUER, audience=AUDIENCE)
    with pytest.raises(AuthenticationError):
        validator.validate(token)


def test_wrong_audience_is_rejected(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], jwks_server: str
) -> None:
    """README.md §45 Teste 8: a token issued for a different resource server must be rejected."""
    private_key, _ = rsa_keypair
    token = _sign_token(private_key, audience="some-other-resource-server")

    validator = TokenValidator(jwks_url=jwks_server, issuer=ISSUER, audience=AUDIENCE)
    with pytest.raises(AuthenticationError):
        validator.validate(token)


def test_wrong_issuer_is_rejected(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], jwks_server: str
) -> None:
    private_key, _ = rsa_keypair
    token = _sign_token(private_key, issuer="https://attacker.example/realms/fake")

    validator = TokenValidator(jwks_url=jwks_server, issuer=ISSUER, audience=AUDIENCE)
    with pytest.raises(AuthenticationError):
        validator.validate(token)


def test_token_signed_by_an_untrusted_key_is_rejected(jwks_server: str) -> None:
    """A different keypair than the one in the JWKS -- e.g. a stolen/forged token."""
    forged_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _sign_token(forged_key)

    validator = TokenValidator(jwks_url=jwks_server, issuer=ISSUER, audience=AUDIENCE)
    with pytest.raises(AuthenticationError):
        validator.validate(token)


def test_agent_declared_role_claim_is_never_consulted(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], jwks_server: str
) -> None:
    """README.md §35.1 anti-pattern / Axiom 2: a bonus claim on an otherwise
    valid token must have zero effect on the resolved client_id."""
    private_key, _ = rsa_keypair
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "service-account-sales-read-agent",
        "azp": "sales-read-agent",
        "role": "finance-admin",  # attacker-controlled-shaped claim, never trusted
        "iat": now,
        "exp": now + 300,
    }
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})

    validator = TokenValidator(jwks_url=jwks_server, issuer=ISSUER, audience=AUDIENCE)
    authenticated = validator.validate(token)

    assert authenticated.client_id == "sales-read-agent"
    assert not hasattr(authenticated, "role")
