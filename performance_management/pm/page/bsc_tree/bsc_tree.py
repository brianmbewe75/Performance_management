# Copyright (c) 2026 and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_bsc_tree_data(cycle):
	"""Return a hierarchical tree of employees and their BSC data for the given appraisal cycle.

	Each node:
	  {
	    employee, employee_name, bsc_name, status, goal_progression, docstatus,
	    children: [...]
	  }

	Top-level nodes are employees with no supervisor (reports_to is null/empty).
	Children are employees whose reports_to matches the parent.
	Only employees that have a BSC for the cycle OR who appear in the org hierarchy are included.
	"""
	if not cycle:
		return []

	# Fetch all BSCs for this cycle
	bsc_records = frappe.get_all(
		"Balance Score Card",
		filters={"appraisal_cycle": cycle},
		fields=["name", "employee", "employee_name", "status", "goal_progression", "docstatus"],
	)

	# Build a map: employee → bsc record
	bsc_map = {}
	for bsc in bsc_records:
		bsc_map[bsc.employee] = bsc

	# Fetch all employees (to build the full org tree)
	all_employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "reports_to"],
	)

	# Build lookup: employee_name → employee record
	emp_map = {e.name: e for e in all_employees}

	# Collect employees that are relevant: have a BSC OR are in the hierarchy of those who do
	# For simplicity: include all active employees in the tree (hierarchy-driven)
	# Build children map
	children_map = {}
	for emp in all_employees:
		parent = emp.reports_to or "__root__"
		if parent not in children_map:
			children_map[parent] = []
		children_map[parent].append(emp.name)

	def build_node(employee_name):
		emp = emp_map.get(employee_name)
		if not emp:
			return None
		bsc = bsc_map.get(employee_name)
		node = {
			"employee": employee_name,
			"employee_name": emp.employee_name or employee_name,
			"bsc_name": bsc.name if bsc else None,
			"status": bsc.status if bsc else None,
			"goal_progression": flt(bsc.goal_progression) if bsc else None,
			"docstatus": bsc.docstatus if bsc else None,
			"children": [],
		}
		for child_emp in (children_map.get(employee_name) or []):
			child_node = build_node(child_emp)
			if child_node:
				node["children"].append(child_node)
		return node

	# Top-level: employees with no reports_to
	top_level_employees = children_map.get("__root__", [])
	tree = []
	for emp_name in top_level_employees:
		node = build_node(emp_name)
		if node:
			tree.append(node)

	return tree
