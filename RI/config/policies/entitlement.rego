# Entitlement policy (EP-03-T02, README.md §25 Passo 1, §6.5.A).
#
#   permit if requested_tool IN entitlement(authenticated_client)
#
# `input.client_profile` is the client profile *name* the Gateway already
# resolved from the authenticated client_id (EP-01-T03 -> identity/models.py
# ClientRegistration.profile) -- never a value read from the request body.
# `data.emcp.client_profiles` is pushed into OPA by the Entitlement Manager
# (EP-04-T02) from the validated ClientProfile YAML (EP-04-T01); this policy
# never parses YAML itself.
package emcp.entitlement

import rego.v1

default allow := false

allow if {
	profile := data.emcp.client_profiles[input.client_profile]
	input.tool in profile.allowed_tools
}
