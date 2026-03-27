# Copyright (c) 2026 and contributors
# License: MIT. See LICENSE

"""Ensure Appraisal has balance_score_card column (Custom Field + schema)."""

import frappe


def execute():
	"""Add balance_score_card to Appraisal if missing (custom field and table column)."""
	if not frappe.db.table_exists("Appraisal"):
		return
	# Create Custom Field if not present (so form shows the field)
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
	# Ensure table has the column (in case Custom Field existed but schema wasn't synced)
	try:
		frappe.db.updatedb("Appraisal")
		frappe.db.commit()
	except Exception:
		frappe.log_error("Failed to updatedb Appraisal for balance_score_card")
