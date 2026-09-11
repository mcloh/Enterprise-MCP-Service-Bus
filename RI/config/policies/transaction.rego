# Transaction policy (EP-03-T03, README.md §25 Passo 2, §6.5.B, §26).
#
#   permit quote.create if
#     amount <= client.transaction_limit
#     AND region IN client.allowed_regions
#     AND customer.classification != "restricted"
#
# Restricts a tool *already granted* by entitlement.rego -- this policy never
# adds a tool absent from the client's entitlement (README.md §25, "A
# Transaction Policy pode negar ou restringir. Ela não pode adicionar uma
# tool inexistente no Client Entitlement."). `allow` here is meaningless on
# its own; the PDP client (EP-03-T04) only consults it after entitlement.rego
# already allowed the same (client_profile, tool) pair.
#
# input: {
#   "client_profile": "Sales.Write",
#   "tool": "sales.quote.create",
#   "arguments": {"amount": 100000, "region": "BR-SP"},
#   "customer_classification": "standard"
# }
package emcp.transaction

import rego.v1

default allow := false

default require_approval := false

allow if {
	profile := data.emcp.client_profiles[input.client_profile]
	within_transaction_limit(profile)
	within_allowed_regions(profile)
	not restricted_customer
}

# README.md §26: above the profile's approval_threshold, a transaction that
# would otherwise be allowed instead requires human approval (EP-14) -- it is
# never silently allowed, and never silently upgraded to a hard deny either.
require_approval if {
	allow
	profile := data.emcp.client_profiles[input.client_profile]
	threshold := profile.restrictions.approval_threshold
	amount := object.get(input.arguments, "amount", 0)
	amount > threshold
}

within_transaction_limit(profile) if {
	not profile.restrictions.max_transaction_value
}

within_transaction_limit(profile) if {
	limit := profile.restrictions.max_transaction_value
	amount := object.get(input.arguments, "amount", 0)
	amount <= limit
}

within_allowed_regions(profile) if {
	not profile.restrictions.allowed_regions
}

within_allowed_regions(profile) if {
	region := object.get(input.arguments, "region", "")
	region in profile.restrictions.allowed_regions
}

restricted_customer if {
	input.customer_classification == "restricted"
}
