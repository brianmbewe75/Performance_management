# Copyright (c) 2026 and contributors
# License: MIT. See LICENSE

"""Ensure a default outgoing Email Account exists so Balance Score Card (and other) submit does not block."""

import frappe


def execute():
	"""Create a placeholder default outgoing Email Account if none exists."""
	if not frappe.db.table_exists("Email Account"):
		return
	# Skip if already have a default outgoing account
	existing = frappe.db.get_value(
		"Email Account",
		{"enable_outgoing": 1, "default_outgoing": 1},
		"name",
	)
	if existing:
		return
	# Create placeholder so find_outgoing() returns and submit/notifications don't throw.
	# User should replace with real SMTP via Tools > Email Account.
	placeholder_name = "Default Outgoing (Setup Required)"
	if frappe.db.exists("Email Account", placeholder_name):
		# Set as default if it exists but wasn't default
		frappe.db.set_value("Email Account", placeholder_name, "default_outgoing", 1)
		frappe.db.commit()
		return
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_account_name": placeholder_name,
				"email_id": frappe.conf.get("mail_login") or "notifications@example.com",
				"enable_outgoing": 1,
				"default_outgoing": 1,
				"smtp_server": "localhost",
				"smtp_port": 25,
				"no_smtp_authentication": 1,
				"awaiting_password": 0,
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error("Failed to create placeholder default Email Account")
