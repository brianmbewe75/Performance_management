# Copyright (c) 2026 and contributors
# License: MIT. See LICENSE

import frappe


def after_install():
	"""Add custom fields required by performance_management to HRMS doctypes."""
	# 1. balance_score_card link on Appraisal
	if not frappe.db.exists("Custom Field", {"dt": "Appraisal", "fieldname": "balance_score_card"}):
		try:
			frappe.get_doc(
				{
					"doctype": "Custom Field",
					"dt": "Appraisal",
					"fieldname": "balance_score_card",
					"label": "Balance Score Card",
					"fieldtype": "Link",
					"options": "Balance Score Card",
					"insert_after": "appraisal_cycle",
					"read_only": 1,
				}
			).insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			frappe.log_error("Failed to add balance_score_card custom field to Appraisal")

	# 2. self_score on Appraisal Goal (child table) — employee's self-assessment (0–5 scale)
	if not frappe.db.exists("Custom Field", {"dt": "Appraisal Goal", "fieldname": "self_score"}):
		try:
			frappe.get_doc(
				{
					"doctype": "Custom Field",
					"dt": "Appraisal Goal",
					"fieldname": "self_score",
					"label": "Self Score",
					"fieldtype": "Float",
					"insert_after": "score",
					"description": "Employee self-assessment score (0–5). BSC goal progress uses average of supervisor score and this self score.",
					"default": "0",
				}
			).insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			frappe.log_error("Failed to add self_score custom field to Appraisal Goal")
	# Deactivate Balance Score Card workflow if present (user configures workflow themselves)
	try:
		if frappe.db.table_exists("Workflow") and frappe.db.exists("Workflow", "Balance Score Card Workflow"):
			frappe.db.set_value("Workflow", "Balance Score Card Workflow", "is_active", 0)
			frappe.db.commit()
	except Exception:
		frappe.log_error("Failed to deactivate BSC workflow")
