package emcp.entitlement_test

import rego.v1
import data.emcp.entitlement

test_allow_when_tool_in_entitlement if {
	entitlement.allow with input as {"client_profile": "Sales.Read", "tool": "sales.customer.get"}
		with data.emcp.client_profiles as {"Sales.Read": {"allowed_tools": ["sales.customer.get"]}}
}

test_deny_when_tool_not_in_entitlement if {
	# README.md §45 Teste 1/2: finance.createPayment must never be reachable
	# by a Sales.Read client, discovered or not.
	not entitlement.allow with input as {"client_profile": "Sales.Read", "tool": "finance.createPayment"}
		with data.emcp.client_profiles as {"Sales.Read": {"allowed_tools": ["sales.customer.get"]}}
}

test_deny_when_client_profile_unknown if {
	not entitlement.allow with input as {"client_profile": "NoSuchProfile", "tool": "sales.customer.get"}
		with data.emcp.client_profiles as {"Sales.Read": {"allowed_tools": ["sales.customer.get"]}}
}
