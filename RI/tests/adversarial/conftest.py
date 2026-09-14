"""Re-exports the e2e suite's real-OPA/real-JWKS Gateway fixtures (EP-15-T03/
T04 exercise the exact same governed stack as EP-15-T02/`tests/e2e` -- the
same security boundary, just probed with adversarial inputs instead of
straightforward ones -- so there is nothing adversarial-specific to build a
new stack for).
"""

from __future__ import annotations

from tests.e2e.conftest import (  # noqa: F401 -- imported for pytest fixture discovery
    RunningServer,
    free_port,
    gateway_url,
    governed_stack,
    governed_stack_with_finance,
    jwks_url,
    opa_url,
    rsa_keypair,
    run_against_gateway,
    set_current_gateway_port,
    sign_token,
)
