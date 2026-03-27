#!/usr/bin/env python3
"""Run with: bench --site all execute performance_management.scripts.sync_pm_doctypes.run"""
import os
import frappe
from frappe.modules.import_file import import_file_by_path
from frappe.modules.patch_handler import _patch_mode


def run():
	frappe.connect()
	app_path = os.path.dirname(frappe.get_module_path("performance_management"))
	doctype_path = os.path.join(app_path, "pm", "doctype")
	if not os.path.isdir(doctype_path):
		print("Doctype path not found:", doctype_path)
		return
	_patch_mode(True)
	for docname in sorted(os.listdir(doctype_path)):
		doc_dir = os.path.join(doctype_path, docname)
		doc_json = os.path.join(doc_dir, docname + ".json")
		if os.path.isfile(doc_json):
			print("Importing", docname)
			import_file_by_path(doc_json, force=True, ignore_version=True)
			frappe.db.commit()
	_patch_mode(False)
	frappe.clear_cache()
	print("Done. PM DocTypes synced.")
