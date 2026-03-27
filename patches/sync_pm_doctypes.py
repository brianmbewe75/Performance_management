# Copyright (c) 2026 and contributors
# License: MIT. See LICENSE
"""Patch: Import PM doctypes if not discovered by sync (post_model_sync)."""

import os

import frappe


def execute():
	"""Import all DocType JSON files from pm/doctype."""
	from frappe.modules.import_file import import_file_by_path

	app_path = os.path.dirname(frappe.get_module_path("performance_management"))
	for base in [app_path, os.path.join(app_path, "performance_management")]:
		doctype_path = os.path.join(base, "pm", "doctype")
		if not os.path.isdir(doctype_path):
			continue
		for docname in sorted(os.listdir(doctype_path)):
			doc_dir = os.path.join(doctype_path, docname)
			doc_json = os.path.join(doc_dir, docname + ".json")
			if os.path.isfile(doc_json):
				import_file_by_path(doc_json, force=True, ignore_version=True)
				frappe.db.commit()
		break
