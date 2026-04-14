# Copyright (c) 2026 and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _


def appraisal_validate_bsc(doc, method=None):
	"""On Appraisal submit: sync BSC goal_completion and goal_progression from appraisal scores.
	Uses average of supervisor score and employee self-score per KRA row.
	Also blends subordinate contributions if configured and triggers cascading supervisor update."""
	if not getattr(doc, "balance_score_card", None):
		return
	from performance_management.pm.doctype.balance_score_card.balance_score_card import (
		update_bsc_goal_completion_from_appraisal,
	)
	update_bsc_goal_completion_from_appraisal(doc)


# ---------------------------------------------------------------------------
# Supervisor role auto-sync
# ---------------------------------------------------------------------------
# Frappe workflow buttons are only shown to users whose role list (frappe.user_roles)
# contains the role named in the transition's "Allowed" field.
# We keep the built-in "Supervisor" role in sync with the actual employee hierarchy:
#   • A Frappe user gets the Supervisor role  → when at least one Employee's reports_to
#     points to their Employee record.
#   • The Supervisor role is removed           → when they no longer have any direct reports.
# ---------------------------------------------------------------------------

def sync_supervisor_role(doc, method=None):
	"""Employee on_update: keep the Supervisor Frappe-role in sync with the org hierarchy."""
	# Re-evaluate the employee being saved (their subordinate count may have changed)
	_evaluate_supervisor_role(doc.name)

	# If reports_to changed, re-evaluate the OLD supervisor too
	try:
		before = doc.get_doc_before_save()
		old_reports_to = before.get("reports_to") if before else None
	except Exception:
		old_reports_to = None

	if old_reports_to and old_reports_to != doc.reports_to:
		_evaluate_supervisor_role(old_reports_to)

	# Re-evaluate whoever this employee now reports to
	if doc.reports_to:
		_evaluate_supervisor_role(doc.reports_to)


def _evaluate_supervisor_role(employee_name):
	"""Assign or remove the Supervisor role for the Frappe user linked to employee_name."""
	if not employee_name:
		return
	user_id = frappe.db.get_value("Employee", employee_name, "user_id")
	if not user_id or not frappe.db.exists("User", user_id):
		return

	has_subordinates = bool(
		frappe.db.get_value("Employee", {"reports_to": employee_name}, "name")
	)

	existing_roles = frappe.get_roles(user_id)
	has_role = "Supervisor" in existing_roles

	if has_subordinates == has_role:
		return  # nothing to change

	user_doc = frappe.get_doc("User", user_id)
	if has_subordinates and not has_role:
		user_doc.append("roles", {"role": "Supervisor"})
	elif not has_subordinates and has_role:
		user_doc.roles = [r for r in user_doc.roles if r.role != "Supervisor"]

	user_doc.flags.ignore_permissions = True
	user_doc.flags.ignore_validate = True
	user_doc.save(ignore_permissions=True)


@frappe.whitelist()
def bulk_sync_supervisor_roles():
	"""Whitelist: assign the Supervisor role to every Frappe user who has direct reports,
	and remove it from users who no longer do. Safe to run multiple times."""
	# All employees who have at least one direct report
	supervisors = frappe.db.sql(
		"SELECT DISTINCT reports_to FROM `tabEmployee` WHERE reports_to IS NOT NULL AND reports_to != ''",
		pluck="reports_to",
	) or []

	assigned = []
	removed = []

	# All employees with a linked user
	all_employees = frappe.db.get_all(
		"Employee", filters={"user_id": ["!=", ""]}, fields=["name", "user_id"]
	)

	for emp in all_employees:
		if not emp.user_id or not frappe.db.exists("User", emp.user_id):
			continue
		is_supervisor = emp.name in supervisors
		existing_roles = frappe.get_roles(emp.user_id)
		has_role = "Supervisor" in existing_roles

		if is_supervisor == has_role:
			continue

		user_doc = frappe.get_doc("User", emp.user_id)
		if is_supervisor and not has_role:
			user_doc.append("roles", {"role": "Supervisor"})
			assigned.append(emp.user_id)
		elif not is_supervisor and has_role:
			user_doc.roles = [r for r in user_doc.roles if r.role != "Supervisor"]
			removed.append(emp.user_id)

		user_doc.flags.ignore_permissions = True
		user_doc.flags.ignore_validate = True
		user_doc.save(ignore_permissions=True)

	frappe.db.commit()
	msg = []
	if assigned:
		msg.append(_("Supervisor role assigned to: {0}").format(", ".join(assigned)))
	if removed:
		msg.append(_("Supervisor role removed from: {0}").format(", ".join(removed)))
	if not msg:
		msg.append(_("All Supervisor roles are already in sync."))
	frappe.msgprint("<br>".join(msg), title=_("Supervisor Role Sync"), indicator="green")
