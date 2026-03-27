# Copyright (c) 2026 and contributors
# License: MIT. See LICENSE

import os

import frappe


def sync_pm_doctypes():
	"""Import all DocType JSON files from the pm/doctype folder (used when migrate does not discover them)."""
	from frappe.modules.import_file import import_file_by_path
	from frappe.modules.patch_handler import _patch_mode

	app_path = os.path.dirname(frappe.get_module_path("performance_management"))
	doctype_path = os.path.join(app_path, "pm", "doctype")
	if not os.path.isdir(doctype_path):
		return
	_patch_mode(True)
	for docname in os.listdir(doctype_path):
		doc_dir = os.path.join(doctype_path, docname)
		doc_json = os.path.join(doc_dir, docname + ".json")
		if os.path.isfile(doc_json):
			import_file_by_path(doc_json, force=True, ignore_version=True)
			frappe.db.commit()
	_patch_mode(False)
	frappe.clear_cache()


def after_install():
	"""Add balance_score_card custom field to Appraisal if not present."""
	if not frappe.db.exists("Custom Field", {"dt": "Appraisal", "fieldname": "balance_score_card"}):
		try:
			custom_field = frappe.get_doc(
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
			)
			custom_field.insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			frappe.log_error("Failed to add balance_score_card custom field to Appraisal")
	# Deactivate Balance Score Card workflow if present (user configures workflow themselves)
	try:
		if frappe.db.table_exists("Workflow") and frappe.db.exists("Workflow", "Balance Score Card Workflow"):
			frappe.db.set_value("Workflow", "Balance Score Card Workflow", "is_active", 0)
			frappe.db.commit()
	except Exception:
		frappe.log_error("Failed to deactivate BSC workflow")
