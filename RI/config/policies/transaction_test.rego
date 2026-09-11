package emcp.transaction_test

import rego.v1
import data.emcp.transaction

sales_write_profile := {"restrictions": {
	"max_transaction_value": 500000,
	"allowed_regions": ["BR-SP", "BR-RJ"],
	"approval_threshold": 100000,
}}

test_allow_within_limit_and_region if {
	transaction.allow with input as {
		"client_profile": "Sales.Write",
		"tool": "sales.quote.create",
		"arguments": {"amount": 50000, "region": "BR-SP"},
		"customer_classification": "standard",
	} with data.emcp.client_profiles as {"Sales.Write": sales_write_profile}
}

test_deny_above_transaction_limit if {
	not transaction.allow with input as {
		"client_profile": "Sales.Write",
		"tool": "sales.quote.create",
		"arguments": {"amount": 600000, "region": "BR-SP"},
		"customer_classification": "standard",
	} with data.emcp.client_profiles as {"Sales.Write": sales_write_profile}
}

test_deny_outside_allowed_region if {
	not transaction.allow with input as {
		"client_profile": "Sales.Write",
		"tool": "sales.quote.create",
		"arguments": {"amount": 50000, "region": "BR-MG"},
		"customer_classification": "standard",
	} with data.emcp.client_profiles as {"Sales.Write": sales_write_profile}
}

test_deny_restricted_customer if {
	not transaction.allow with input as {
		"client_profile": "Sales.Write",
		"tool": "sales.quote.create",
		"arguments": {"amount": 50000, "region": "BR-SP"},
		"customer_classification": "restricted",
	} with data.emcp.client_profiles as {"Sales.Write": sales_write_profile}
}

test_require_approval_above_threshold if {
	# README.md §26: allowed, but only with human approval, above threshold.
	transaction.allow with input as {
		"client_profile": "Sales.Write",
		"tool": "sales.quote.create",
		"arguments": {"amount": 150000, "region": "BR-SP"},
		"customer_classification": "standard",
	} with data.emcp.client_profiles as {"Sales.Write": sales_write_profile}

	transaction.require_approval with input as {
		"client_profile": "Sales.Write",
		"tool": "sales.quote.create",
		"arguments": {"amount": 150000, "region": "BR-SP"},
		"customer_classification": "standard",
	} with data.emcp.client_profiles as {"Sales.Write": sales_write_profile}
}

test_no_approval_required_below_threshold if {
	not transaction.require_approval with input as {
		"client_profile": "Sales.Write",
		"tool": "sales.quote.create",
		"arguments": {"amount": 50000, "region": "BR-SP"},
		"customer_classification": "standard",
	} with data.emcp.client_profiles as {"Sales.Write": sales_write_profile}
}
