# Copyright (c) 2026 and contributors
# License: MIT. See LICENSE

from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BalanceScoreCard(Document):
	def validate(self):
		self.validate_one_bsc_per_employee_per_cycle()
		self.validate_weights()
		self.validate_kpi_weights()
		self._compute_kpi_scores()
		self.validate_employee_hierarchy()
		self.validate_cycle_status()
		self.calculate_total_weight()

	def before_submit(self):
		"""Only allow submission when status is Approved."""
		if self.status != "Approved":
			frappe.throw(
				_("Balance Score Card can only be submitted after it has been Approved. "
				  "Current status: {0}").format(frappe.bold(self.status))
			)

	def validate_one_bsc_per_employee_per_cycle(self):
		"""An employee can only have one Balance Score Card per appraisal cycle."""
		if not self.employee or not self.appraisal_cycle:
			return
		filters = {"employee": self.employee, "appraisal_cycle": self.appraisal_cycle}
		if not self.is_new():
			filters["name"] = ["!=", self.name]
		if frappe.db.exists("Balance Score Card", filters):
			frappe.throw(
				_("Employee {0} already has a Balance Score Card for appraisal cycle {1}.").format(
					frappe.bold(self.employee), frappe.bold(self.appraisal_cycle)
				)
			)

	def validate_weights(self):
		if not self.goal_kras:
			frappe.throw(_("At least one Goal & KRA row is required"))
		goal_weights = defaultdict(lambda: 0)
		for row in self.goal_kras:
			goal_weights[row.goal_name] += flt(row.weight)
		for goal_name, total_weight in goal_weights.items():
			if abs(total_weight - 100.0) > 0.01:
				frappe.throw(
					_("Goal '{0}' KRAs must sum to 100%. Current total: {1}%").format(
						goal_name, total_weight
					)
				)

	def validate_employee_hierarchy(self):
		"""Users may only create a BSC for themselves.
		HR Manager, System Manager, and Administrator can create for anyone."""
		if not self.is_new():
			return
		current_user = frappe.session.user
		if current_user == "Administrator":
			return
		privileged_roles = {"HR Manager", "System Manager"}
		if privileged_roles.intersection(set(frappe.get_roles(current_user))):
			return
		# Regular user: find their employee record
		employee = frappe.db.get_value("Employee", {"user_id": current_user}, "name")
		if not employee:
			frappe.throw(_("Only employees can create Balance Score Cards"))
		if self.employee != employee:
			frappe.throw(_("You can only create a Balance Score Card for yourself"))

	def validate_cycle_status(self):
		if not self.appraisal_cycle:
			return
		cycle_status = frappe.db.get_value("Appraisal Cycle", self.appraisal_cycle, "status")
		if cycle_status == "Completed":
			frappe.throw(_("Balance Score Card can only be created for cycles that are not Completed."))

	def validate_kpi_weights(self):
		"""For each KRA that has KPIs, the KPI weights within that KRA must sum to 100%."""
		if not self.kpi_rows:
			return
		kra_weights = defaultdict(float)
		for row in self.kpi_rows:
			key = f"{(row.goal_name or '').strip()}::{(row.kra_name or '').strip()}"
			kra_weights[key] += flt(row.weight)
		for key, total in kra_weights.items():
			if abs(total - 100.0) > 0.01:
				goal, kra = key.split("::", 1)
				frappe.throw(
					_("KRA '{0}' (Goal: '{1}') KPI weights must sum to 100%. Current total: {2}%").format(
						frappe.bold(kra), frappe.bold(goal or _("—")), round(total, 2)
					)
				)

	def _compute_kpi_scores(self):
		"""Recompute the read-only score field on every KPI row."""
		for kpi in self.kpi_rows or []:
			target = flt(kpi.target)
			actual = flt(kpi.actual)
			if target > 0 and actual > 0:
				kpi.score = min(actual / target * 5.0, 5.0)
			else:
				kpi.score = 0.0

	def calculate_total_weight(self):
		total = sum(flt(row.weight) for row in (self.goal_kras or []))
		self.total_weight = total

	def on_submit(self):
		"""Create draft Appraisal for the BSC owner, then cascade to direct reports."""
		self.create_draft_appraisals()
		# Auto-create a draft BSC for each direct report (if not already present)
		# and notify them that they need to fill it in.
		_create_draft_bsc_for_direct_reports(self)

	def on_update_after_submit(self):
		"""Recompute KPI scores and refresh BSC goal_completion whenever actuals are saved
		on a submitted BSC (supervisor fills actual values in the KPI table)."""
		self._compute_kpi_scores()
		# Persist the recomputed scores back to the DB
		for kpi in self.kpi_rows or []:
			frappe.db.set_value("Balance Score Card KPI", kpi.name, "score", kpi.score, update_modified=False)
		# Re-run appraisal → BSC sync if a submitted appraisal exists
		appraisal_name = frappe.db.get_value(
			"Appraisal", {"balance_score_card": self.name, "docstatus": 1}, "name"
		)
		if appraisal_name:
			appraisal_doc = frappe.get_doc("Appraisal", appraisal_name)
			update_bsc_goal_completion_from_appraisal(appraisal_doc)

	def create_draft_appraisals(self):
		try:
			from hrms.hr.doctype.appraisal.appraisal import Appraisal  # noqa: F401
		except ImportError:
			frappe.msgprint(
				_("HRMS Appraisal not found. Install hrms app to auto-create Appraisal from BSC."),
				indicator="orange",
			)
			return

		existing_name = frappe.db.get_value(
			"Appraisal", {"balance_score_card": self.name}, "name"
		)
		if existing_name:
			# Appraisal already exists — sync goals + self_ratings from current BSC KRAs
			_sync_appraisal_rows(self, existing_name)
			return

		cycle = frappe.db.get_value(
			"Appraisal Cycle", self.appraisal_cycle, ["start_date", "end_date", "company"], as_dict=True
		)
		if not cycle:
			return

		labeled_rows = _build_labeled_rows(self)
		template_name = _get_or_create_appraisal_template(self, labeled_rows)

		appraisal = frappe.new_doc("Appraisal")
		appraisal.employee = self.employee
		appraisal.appraisal_cycle = self.appraisal_cycle
		appraisal.company = cycle.company or frappe.db.get_value("Employee", self.employee, "company")
		appraisal.start_date = cycle.start_date
		appraisal.end_date = cycle.end_date
		appraisal.rate_goals_manually = 1
		appraisal.appraisal_template = template_name
		if hasattr(appraisal, "balance_score_card"):
			appraisal.balance_score_card = self.name

		for kra_text, norm_weight in labeled_rows:
			appraisal.append("goals", {
				"kra": kra_text,
				"per_weightage": norm_weight,
				"score": 0,
				"score_earned": 0,
			})
			appraisal.append("self_ratings", {
				"criteria": kra_text,
				"per_weightage": norm_weight,
				"rating": 0,
			})

		appraisal.flags.ignore_permissions = True
		appraisal.insert()
		# Initialise BSC goal-completion rows at 0 %
		_set_goal_completion_from_goals(self, completion_map=None)
		frappe.msgprint(
			_("Draft Appraisal {0} created.").format(frappe.utils.get_link_to_form("Appraisal", appraisal.name)),
			indicator="green",
		)


# ---------------------------------------------------------------------------
# Notification helper
# ---------------------------------------------------------------------------

def _send_notification(to_user, subject, message, doc_type, doc_name):
	"""Send an in-app Notification Log entry and an email to to_user."""
	if not to_user or not frappe.db.exists("User", to_user):
		return
	try:
		if frappe.db.table_exists("Notification Log"):
			notif = frappe.new_doc("Notification Log")
			notif.subject = subject[:140]
			notif.email_content = message
			notif.document_type = doc_type
			notif.document_name = doc_name
			notif.from_user = frappe.session.user
			notif.for_user = to_user
			notif.type = "Alert"
			notif.insert(ignore_permissions=True)
		frappe.sendmail(recipients=[to_user], subject=subject, message=message, now=False)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "BSC Notification Failed")


def _create_draft_bsc_for_direct_reports(supervisor_bsc):
	"""When a supervisor's BSC is approved+submitted:
	  1. Auto-create a blank Draft BSC for each direct report that doesn't have one yet,
	     pre-populated with supervisor and parent_bsc so the Approve/Reject buttons work.
	  2. Notify each direct report, pointing them at their own new BSC.
	Direct reports open their BSC, tick which supervisor KRAs they will contribute to
	via 'Load from Supervisor BSC', fill in their own goals, then submit for approval.
	"""
	direct_reports = frappe.get_all(
		"Employee",
		filters={"reports_to": supervisor_bsc.employee},
		fields=["name", "user_id", "employee_name"],
	)
	supervisor_name = (
		frappe.db.get_value("Employee", supervisor_bsc.employee, "employee_name")
		or supervisor_bsc.employee
	)

	for subordinate in direct_reports:
		# Check whether a BSC already exists for this subordinate + cycle
		existing_name = frappe.db.get_value(
			"Balance Score Card",
			{"employee": subordinate.name, "appraisal_cycle": supervisor_bsc.appraisal_cycle},
			"name",
		)

		if existing_name:
			# BSC already exists — backfill supervisor/parent_bsc if missing, then notify
			frappe.db.set_value(
				"Balance Score Card", existing_name, {
					"supervisor": frappe.db.get_value("Balance Score Card", existing_name, "supervisor")
						or supervisor_bsc.employee,
					"parent_bsc": frappe.db.get_value("Balance Score Card", existing_name, "parent_bsc")
						or supervisor_bsc.name,
				}, update_modified=False
			)
			bsc_link = existing_name
		else:
			# Auto-create a blank Draft BSC for the subordinate
			try:
				new_bsc = frappe.new_doc("Balance Score Card")
				new_bsc.employee = subordinate.name
				new_bsc.appraisal_cycle = supervisor_bsc.appraisal_cycle
				new_bsc.status = "Draft"
				new_bsc.supervisor = supervisor_bsc.employee
				new_bsc.parent_bsc = supervisor_bsc.name
				new_bsc.flags.ignore_permissions = True
				# Skip validate() — the BSC is intentionally blank; the employee fills it in
				new_bsc.flags.ignore_validate = True
				new_bsc.insert(ignore_permissions=True)
				bsc_link = new_bsc.name
			except Exception:
				frappe.log_error(
					frappe.get_traceback(),
					f"Auto-create BSC failed for {subordinate.name}",
				)
				continue

		if not subordinate.user_id:
			continue

		subject = _("Your BSC is ready — please fill in your goals ({0})").format(
			supervisor_bsc.appraisal_cycle
		)
		message = _(
			"Your supervisor {0}'s Balance Score Card for appraisal cycle {1} has been approved. "
			"A draft Balance Score Card has been created for you. "
			"Open it and click <b>Load from Supervisor BSC</b> to choose which of your "
			"supervisor's KRAs you will contribute to, fill in your goals, then submit for approval."
		).format(frappe.bold(supervisor_name), frappe.bold(supervisor_bsc.appraisal_cycle))

		_send_notification(
			subordinate.user_id,
			subject,
			message,
			"Balance Score Card",
			bsc_link,
		)


@frappe.whitelist()
def trigger_subordinate_bsc_creation(bsc_name):
	"""Manually trigger auto-creation of subordinate BSCs for an already-submitted BSC.
	Useful when the supervisor BSC was submitted before this feature existed."""
	bsc = frappe.get_doc("Balance Score Card", bsc_name)
	if bsc.docstatus != 1 or bsc.status != "Approved":
		frappe.throw(_("BSC must be Approved and submitted to trigger subordinate creation."))
	_check_is_employee_or_privileged(bsc)
	_create_draft_bsc_for_direct_reports(bsc)
	frappe.msgprint(_("Subordinate BSC creation triggered."), indicator="green")


# ---------------------------------------------------------------------------
# Whitelist: approval flow actions
# ---------------------------------------------------------------------------

@frappe.whitelist()
def request_approval(name):
	"""Employee clicks 'Submit for Approval'.
	- Validates weights.
	- If top-level (no supervisor): auto-approve immediately → submit.
	- Otherwise: set status='Pending Supervisor Approval', save, notify supervisor.
	"""
	bsc = frappe.get_doc("Balance Score Card", name)
	# Permission: only the employee themselves (or HR Manager / System Manager / Administrator)
	_check_is_employee_or_privileged(bsc)

	if bsc.docstatus != 0:
		frappe.throw(_("Only draft BSCs can be submitted for approval."))
	if bsc.status not in ("Draft", "Rejected"):
		frappe.throw(_("BSC must be in Draft or Rejected status to submit for approval."))

	# Validate weights before proceeding
	bsc.validate_weights()
	# Validate that every cascaded KRA names its supervisor KRA clearly
	_validate_cascaded_kra_links(bsc)

	supervisor = frappe.db.get_value("Employee", bsc.employee, "reports_to")
	if not supervisor:
		# Top-level employee: auto-approve and submit.
		# bypass workflow state-transition checks — there is no supervisor to approve,
		# so the normal Draft → Pending → Approved path does not apply.
		bsc.status = "Approved"
		bsc.flags.ignore_permissions = True
		bsc.flags.ignore_workflow = True
		bsc.save(ignore_permissions=True)
		bsc.flags.ignore_workflow = True
		bsc.submit()
		frappe.msgprint(_("BSC auto-approved (no supervisor) and submitted."), indicator="green")
		return {"auto_approved": True}

	# Has a supervisor: set pending
	bsc.db_set("status", "Pending Supervisor Approval", update_modified=True)

	# Notify supervisor
	supervisor_user = frappe.db.get_value("Employee", supervisor, "user_id")
	employee_name = frappe.db.get_value("Employee", bsc.employee, "employee_name") or bsc.employee
	subject = _("BSC Awaiting Your Approval — {0}").format(employee_name)
	message = _(
		"{0}'s Balance Score Card for appraisal cycle {1} is awaiting your approval."
	).format(frappe.bold(employee_name), frappe.bold(bsc.appraisal_cycle))
	_send_notification(supervisor_user, subject, message, "Balance Score Card", bsc.name)

	frappe.msgprint(_("BSC submitted for supervisor approval."), indicator="blue")
	return {"pending": True}


@frappe.whitelist()
def approve_bsc(name):
	"""Supervisor (or HR Manager / System Manager) approves the BSC.
	Sets status='Approved', saves, then calls doc.submit() → triggers on_submit.
	Notifies the employee and their direct reports.
	"""
	bsc = frappe.get_doc("Balance Score Card", name)
	_check_is_supervisor_or_privileged(bsc)

	if bsc.docstatus != 0:
		frappe.throw(_("Only draft BSCs can be approved."))
	if bsc.status != "Pending Supervisor Approval":
		frappe.throw(_("BSC must be in 'Pending Supervisor Approval' status to approve."))

	bsc.status = "Approved"
	bsc.flags.ignore_permissions = True
	bsc.flags.ignore_workflow = True
	bsc.save(ignore_permissions=True)
	bsc.flags.ignore_workflow = True
	bsc.submit()

	# Notify employee
	employee_user = frappe.db.get_value("Employee", bsc.employee, "user_id")
	employee_name = frappe.db.get_value("Employee", bsc.employee, "employee_name") or bsc.employee
	subject = _("Your BSC has been Approved — {0}").format(bsc.appraisal_cycle)
	message = _(
		"Your Balance Score Card for appraisal cycle {0} has been approved."
	).format(frappe.bold(bsc.appraisal_cycle))
	_send_notification(employee_user, subject, message, "Balance Score Card", bsc.name)

	frappe.msgprint(_("BSC approved and submitted."), indicator="green")
	return {"approved": True}


@frappe.whitelist()
def reject_bsc(name, reason=""):
	"""Supervisor rejects the BSC. Sets status='Rejected', saves, notifies employee."""
	bsc = frappe.get_doc("Balance Score Card", name)
	_check_is_supervisor_or_privileged(bsc)

	if bsc.docstatus != 0:
		frappe.throw(_("Only draft BSCs can be rejected."))
	if bsc.status != "Pending Supervisor Approval":
		frappe.throw(_("BSC must be in 'Pending Supervisor Approval' status to reject."))

	bsc.db_set("status", "Rejected", update_modified=True)

	# Notify employee
	employee_user = frappe.db.get_value("Employee", bsc.employee, "user_id")
	employee_name = frappe.db.get_value("Employee", bsc.employee, "employee_name") or bsc.employee
	subject = _("Your BSC has been Rejected — {0}").format(bsc.appraisal_cycle)
	message = _(
		"Your Balance Score Card for appraisal cycle {0} has been rejected."
	).format(frappe.bold(bsc.appraisal_cycle))
	if reason:
		message += _(" Reason: {0}").format(reason)
	_send_notification(employee_user, subject, message, "Balance Score Card", bsc.name)

	frappe.msgprint(_("BSC rejected."), indicator="orange")
	return {"rejected": True}


@frappe.whitelist()
def get_supervisor_bsc_kras(employee, cycle):
	"""Return list of KRAs from the supervisor's approved BSC for the given cycle.
	Called from JS 'Load from Supervisor BSC' button."""
	supervisor = frappe.db.get_value("Employee", employee, "reports_to")
	if not supervisor:
		return []

	supervisor_bsc_name = frappe.db.get_value(
		"Balance Score Card",
		{"employee": supervisor, "appraisal_cycle": cycle, "docstatus": 1, "status": "Approved"},
		"name",
	)
	if not supervisor_bsc_name:
		return []

	supervisor_bsc = frappe.get_doc("Balance Score Card", supervisor_bsc_name)
	result = []
	for row in supervisor_bsc.goal_kras or []:
		result.append({
			"goal_name": row.goal_name or "",
			"kra_name": row.kra_name or "",
			"description": row.description or "",
			"weight": flt(row.weight),
			"bsc_name": supervisor_bsc_name,
		})
	return result


# ---------------------------------------------------------------------------
# Submission validation helpers
# ---------------------------------------------------------------------------

def _validate_cascaded_kra_links(bsc):
	"""Before submission: every KRA row marked 'Cascaded from Supervisor' must explicitly
	name the supervisor KRA it contributes to (linked_to_supervisor_kra).
	This ensures the contribution chain is unambiguous when reviewing performance.
	"""
	for row in bsc.goal_kras or []:
		if row.is_cascaded and not (row.linked_to_supervisor_kra or "").strip():
			frappe.throw(
				_(
					"KRA <b>{0}</b> (Goal: <b>{1}</b>) is marked as contributing to the supervisor's BSC "
					"but no supervisor KRA is linked. Open <b>Load from Supervisor BSC</b>, "
					"select this KRA with <em>Link</em> mode, or uncheck "
					"<em>Cascaded from Supervisor</em>."
				).format(
					row.kra_name or _("(unnamed)"),
					row.goal_name or _("(unnamed)"),
				)
			)


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def _check_is_employee_or_privileged(bsc):
	"""Raise if the current user is not the BSC's employee, or HR Manager / System Manager / Admin."""
	current_user = frappe.session.user
	if current_user == "Administrator":
		return
	privileged_roles = {"HR Manager", "System Manager"}
	if privileged_roles.intersection(set(frappe.get_roles(current_user))):
		return
	employee = frappe.db.get_value("Employee", {"user_id": current_user}, "name")
	if employee != bsc.employee:
		frappe.throw(_("Only the BSC owner can perform this action."))


def _check_is_supervisor_or_privileged(bsc):
	"""Raise if the current user is not the supervisor of the BSC's employee, or HR Manager / System Manager / Admin."""
	current_user = frappe.session.user
	if current_user == "Administrator":
		return
	privileged_roles = {"HR Manager", "System Manager"}
	if privileged_roles.intersection(set(frappe.get_roles(current_user))):
		return
	supervisor_employee = frappe.db.get_value("Employee", bsc.employee, "reports_to")
	if not supervisor_employee:
		frappe.throw(_("This employee has no supervisor."))
	supervisor_user = frappe.db.get_value("Employee", supervisor_employee, "user_id")
	if supervisor_user != current_user:
		frappe.throw(_("Only the employee's supervisor can perform this action."))


# ---------------------------------------------------------------------------
# Build helpers (unchanged from original)
# ---------------------------------------------------------------------------

def _build_labeled_rows(bsc):
	"""Return list of (kra_text, norm_weight) for every KRA in the BSC, in order.
	Also ensures an Employee Feedback Criteria record exists for each label.
	Labels:  single-goal  → "KRA Name: Description"
	         multi-goal   → "Goal Name — KRA Name: Description"
	Weights are normalised so the total across ALL rows sums to exactly 100%.
	"""
	goals_ordered = []
	goals_map = {}
	for row in bsc.goal_kras or []:
		g = (row.goal_name or "").strip()
		if g not in goals_map:
			goals_map[g] = []
			goals_ordered.append(g)
		goals_map[g].append(row)

	num_goals = len(goals_ordered)
	flat_rows = [(g, row) for g in goals_ordered for row in goals_map[g]]

	running_total = flt(0)
	result = []
	for i, (goal_name, row) in enumerate(flat_rows):
		# Build label
		kra_text = (row.kra_name or "").strip()
		if num_goals > 1:
			kra_text = f"{goal_name} \u2014 {kra_text}"
		if (row.description or "").strip():
			kra_text = f"{kra_text}: {row.description.strip()}"

		# Normalized weight; last row absorbs rounding remainder
		if i == len(flat_rows) - 1:
			w = flt(100.0 - running_total, 2)
		else:
			w = flt(flt(row.weight) / num_goals, 2)
		running_total += w

		# Ensure Employee Feedback Criteria record exists (autoname = field:criteria)
		if not frappe.db.exists("Employee Feedback Criteria", kra_text):
			frappe.get_doc({
				"doctype": "Employee Feedback Criteria",
				"criteria": kra_text,
			}).insert(ignore_permissions=True)

		# Ensure KRA record exists (autoname = field:title) — needed for Appraisal Template goals
		if not frappe.db.exists("KRA", kra_text):
			frappe.get_doc({
				"doctype": "KRA",
				"title": kra_text,
			}).insert(ignore_permissions=True)

		frappe.db.commit()
		result.append((kra_text, w))
	return result


def _get_or_create_appraisal_template(bsc, labeled_rows):
	"""Create or update an Appraisal Template matching the BSC KRAs.

	The template is named after the BSC (e.g. 'BSC-2026-00001') and contains:
	  • goals         → one row per KRA (key_result_area Link to KRA record)
	  • rating_criteria → one row per KRA (criteria Link to Employee Feedback Criteria)

	Both tables are cleared and rebuilt on every sync so they always match the BSC.
	Returns the template name (== bsc.name).
	"""
	template_title = bsc.name

	if frappe.db.exists("Appraisal Template", template_title):
		template = frappe.get_doc("Appraisal Template", template_title)
		template.set("goals", [])
		template.set("rating_criteria", [])
	else:
		template = frappe.new_doc("Appraisal Template")
		template.template_title = template_title

	for kra_text, norm_weight in labeled_rows:
		template.append("goals", {
			"key_result_area": kra_text,
			"per_weightage": norm_weight,
		})
		template.append("rating_criteria", {
			"criteria": kra_text,
			"per_weightage": norm_weight,
		})

	template.flags.ignore_permissions = True
	if template.is_new():
		template.insert()
	else:
		template.save()
	frappe.db.commit()
	return template_title


def _sync_appraisal_rows(bsc, appraisal_name):
	"""Rebuild goals, self_ratings, and appraisal_template on an existing DRAFT appraisal."""
	appraisal = frappe.get_doc("Appraisal", appraisal_name)
	if appraisal.docstatus != 0:
		# Only touch draft appraisals
		return

	labeled_rows = _build_labeled_rows(bsc)
	template_name = _get_or_create_appraisal_template(bsc, labeled_rows)

	appraisal.appraisal_template = template_name
	appraisal.set("goals", [])
	appraisal.set("self_ratings", [])

	for kra_text, norm_weight in labeled_rows:
		appraisal.append("goals", {
			"kra": kra_text,
			"per_weightage": norm_weight,
			"score": 0,
			"score_earned": 0,
		})
		appraisal.append("self_ratings", {
			"criteria": kra_text,
			"per_weightage": norm_weight,
			"rating": 0,
		})

	appraisal.flags.ignore_permissions = True
	appraisal.save()
	frappe.msgprint(
		_("Appraisal {0} updated with latest KRAs from BSC.").format(
			frappe.utils.get_link_to_form("Appraisal", appraisal_name)
		),
		indicator="green",
	)


@frappe.whitelist()
def sync_appraisal_criteria(bsc_name):
	"""Whitelist: re-sync goals + self_ratings on the linked draft Appraisal from BSC KRAs."""
	bsc = frappe.get_doc("Balance Score Card", bsc_name)
	existing_name = frappe.db.get_value("Appraisal", {"balance_score_card": bsc_name}, "name")
	if not existing_name:
		frappe.msgprint(_("No linked Appraisal found for this BSC."), indicator="orange")
		return
	_sync_appraisal_rows(bsc, existing_name)


def _get_goals_grouped(bsc):
	"""Return list of (goal_name, list of kra_names) from BSC goal_kras (consecutive grouping)."""
	rows = bsc.goal_kras or []
	groups = []
	for row in rows:
		g = (row.goal_name or "").strip()
		if not groups or (groups[-1][0] != g):
			groups.append([g, []])
		groups[-1][1].append((row.kra_name or "").strip())
	return [(goal_name, kras) for goal_name, kras in groups]


def _set_goal_completion_from_goals(bsc_doc, completion_map=None):
	"""Set BSC goal_completion child table: one row per goal.
	completion_map = { goal_name: completion_percent } or None (all 0).
	Also sets BSC goal_progression (overall %) as weighted average of completion_map when provided.
	If cycle has enable_energy_points, awards energy points based on progression.
	"""
	goals_grouped = _get_goals_grouped(bsc_doc)
	frappe.db.sql(
		"DELETE FROM `tabBalance Score Card Goal Completion` WHERE parent = %s AND parenttype = 'Balance Score Card'",
		(bsc_doc.name,),
	)
	total_weight = 0
	weighted_sum = 0
	for goal_name, _kras in goals_grouped:
		pct = flt(completion_map.get(goal_name, 0)) if completion_map else 0
		goal_weight = sum(flt(r.weight) for r in (bsc_doc.goal_kras or []) if (r.goal_name or "").strip() == goal_name)
		total_weight += goal_weight
		weighted_sum += pct * goal_weight
		row = frappe.get_doc(
			{
				"doctype": "Balance Score Card Goal Completion",
				"parent": bsc_doc.name,
				"parenttype": "Balance Score Card",
				"parentfield": "goal_completion",
				"goal_name": goal_name or _("(Unnamed goal)"),
				"completion_percent": pct,
				"goal_progression": pct,
			}
		)
		row.insert(ignore_permissions=True)
	if completion_map is not None and total_weight:
		overall_progression = flt(weighted_sum / total_weight, 2)
		bsc_doc.db_set("goal_progression", overall_progression, update_modified=True)
		# Award energy points if configured
		_award_energy_points(bsc_doc, overall_progression)
	frappe.db.commit()
	frappe.clear_cache(doctype="Balance Score Card")


def _award_energy_points(bsc_doc, goal_progression):
	"""Award energy points to the BSC employee based on goal progression, if cycle is configured."""
	cycle = frappe.db.get_value(
		"Appraisal Cycle",
		bsc_doc.appraisal_cycle,
		["enable_energy_points", "energy_points_per_point"],
		as_dict=True,
	)
	if not cycle or not cycle.enable_energy_points:
		return
	user_id = frappe.db.get_value("Employee", bsc_doc.employee, "user_id")
	if not user_id:
		return
	points = int(flt(goal_progression) * flt(cycle.energy_points_per_point or 1))
	if points <= 0:
		return
	if not frappe.db.table_exists("Energy Point Log"):
		return
	# Remove old energy points for this BSC first to avoid duplicates
	frappe.db.delete(
		"Energy Point Log",
		{
			"reference_doctype": "Balance Score Card",
			"reference_name": bsc_doc.name,
			"user": user_id,
		},
	)
	frappe.get_doc({
		"doctype": "Energy Point Log",
		"user": user_id,
		"points": points,
		"type": "Auto",
		"reference_doctype": "Balance Score Card",
		"reference_name": bsc_doc.name,
		"reason": f"BSC Performance: {goal_progression:.1f}%",
	}).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Subordinate contribution blending
# ---------------------------------------------------------------------------

def _blend_subordinate_contribution(bsc, own_completion_map):
	"""Blend supervisor's own KRA scores with their subordinates' linked KRA scores.

	If bsc.subordinate_contribution_pct == 0, returns own_completion_map unchanged.

	For each supervisor goal that has subordinate BSC KRAs linked via linked_to_supervisor_kra:
	  blended = own_pct * (1 - sub_pct/100) + team_avg * (sub_pct/100)

	Returns a new completion_map dict.
	"""
	sub_pct = flt(bsc.subordinate_contribution_pct)
	if sub_pct == 0:
		return own_completion_map

	# Find all submitted subordinate BSCs for the same cycle
	subordinate_bsc_names = frappe.get_all(
		"Balance Score Card",
		filters={
			"appraisal_cycle": bsc.appraisal_cycle,
			"docstatus": 1,
		},
		fields=["name", "employee"],
	)
	# Filter to direct reports only
	direct_report_employees = frappe.get_all(
		"Employee", filters={"reports_to": bsc.employee}, pluck="name"
	)
	subordinate_bscs = [b for b in subordinate_bsc_names if b.employee in direct_report_employees]

	if not subordinate_bscs:
		return own_completion_map

	# For each subordinate BSC, find their submitted appraisal scores
	# grouped by linked_to_supervisor_kra
	supervisor_kra_sub_scores = defaultdict(list)

	for sub_bsc_rec in subordinate_bscs:
		sub_bsc = frappe.get_doc("Balance Score Card", sub_bsc_rec.name)
		# Find submitted appraisal for this subordinate
		sub_appraisal_name = frappe.db.get_value(
			"Appraisal",
			{"balance_score_card": sub_bsc_rec.name, "docstatus": 1},
			"name",
		)
		if not sub_appraisal_name:
			continue
		sub_appraisal = frappe.get_doc("Appraisal", sub_appraisal_name)

		# Build a score map from the subordinate's appraisal (kra_text → score 0-100%)
		sub_score_map = {}
		goals_grouped_sub = _get_goals_grouped(sub_bsc)
		num_goals_sub = len(goals_grouped_sub)
		for goal_name_sub, _kras_sub in goals_grouped_sub:
			goal_key_sub = goal_name_sub or _("(Unnamed goal)")
			total_earned = flt(0)
			total_possible = flt(0)
			for ag in sub_appraisal.goals or []:
				kra_text = (ag.kra or "").strip()
				if num_goals_sub == 1:
					belongs = True
				else:
					belongs = kra_text.startswith(f"{goal_name_sub} \u2014 ")
				if belongs:
					supervisor_score = flt(ag.score)
					total_earned += flt(supervisor_score * flt(ag.per_weightage) / 100)
					total_possible += flt(5 * flt(ag.per_weightage) / 100)
			if total_possible > 0:
				sub_score_map[goal_key_sub] = flt(total_earned / total_possible * 100, 2)
			else:
				sub_score_map[goal_key_sub] = 0

		# Map subordinate KRAs to supervisor KRA names via linked_to_supervisor_kra
		for sub_kra_row in sub_bsc.goal_kras or []:
			linked = (sub_kra_row.linked_to_supervisor_kra or "").strip()
			if not linked:
				continue
			# Find the goal this KRA belongs to, get its score
			sub_goal_key = (sub_kra_row.goal_name or "").strip() or _("(Unnamed goal)")
			score = sub_score_map.get(sub_goal_key, 0)
			supervisor_kra_sub_scores[linked].append(score)

	if not supervisor_kra_sub_scores:
		return own_completion_map

	# Build blended map: blend per supervisor goal
	blended_map = {}
	goals_grouped = _get_goals_grouped(bsc)
	for goal_name, kras in goals_grouped:
		goal_key = goal_name or _("(Unnamed goal)")
		own_score = flt(own_completion_map.get(goal_key, 0))
		# Collect sub scores for all KRAs in this supervisor goal that have linked sub scores
		linked_sub_scores = []
		for supervisor_kra_name in kras:
			if supervisor_kra_name in supervisor_kra_sub_scores:
				linked_sub_scores.extend(supervisor_kra_sub_scores[supervisor_kra_name])
		if linked_sub_scores:
			team_avg = flt(sum(linked_sub_scores) / len(linked_sub_scores), 2)
			blended = own_score * (1 - sub_pct / 100) + team_avg * (sub_pct / 100)
			blended_map[goal_key] = flt(blended, 2)
		else:
			blended_map[goal_key] = own_score

	return blended_map


def _trigger_supervisor_bsc_update(subordinate_bsc):
	"""After updating a subordinate BSC, re-run the supervisor's BSC update if applicable."""
	supervisor = frappe.db.get_value("Employee", subordinate_bsc.employee, "reports_to")
	if not supervisor:
		return
	supervisor_bsc_name = frappe.db.get_value(
		"Balance Score Card",
		{"employee": supervisor, "appraisal_cycle": subordinate_bsc.appraisal_cycle, "docstatus": 1},
		"name",
	)
	if not supervisor_bsc_name:
		return
	supervisor_bsc = frappe.get_doc("Balance Score Card", supervisor_bsc_name)
	if flt(supervisor_bsc.subordinate_contribution_pct) == 0:
		return
	# Find supervisor's submitted appraisal
	supervisor_appraisal_name = frappe.db.get_value(
		"Appraisal",
		{"balance_score_card": supervisor_bsc_name, "docstatus": 1},
		"name",
	)
	if not supervisor_appraisal_name:
		return
	supervisor_appraisal = frappe.get_doc("Appraisal", supervisor_appraisal_name)
	update_bsc_goal_completion_from_appraisal(supervisor_appraisal)


# ---------------------------------------------------------------------------
# KPI scoring helpers
# ---------------------------------------------------------------------------

def _extract_kra_name_from_label(kra_text, goal_name, num_goals):
	"""Reverse _build_labeled_rows: extract the raw kra_name from the appraisal goal label."""
	text = kra_text
	if num_goals > 1:
		prefix = f"{goal_name} \u2014 "
		if text.startswith(prefix):
			text = text[len(prefix):]
	# Strip description (everything after the first ":")
	if ":" in text:
		text = text.split(":", 1)[0]
	return text.strip()


def _get_kra_kpi_score(bsc, goal_name, kra_name):
	"""Return (score_0_to_5, has_kpis) for the given KRA using its KPI actuals.

	Returns (None, False)  — KRA has no KPIs defined.
	Returns (None, True)   — KPIs defined but no actuals entered yet.
	Returns (float, True)  — KPI-derived score ready to use.
	"""
	kpis = [
		row for row in (bsc.kpi_rows or [])
		if (row.goal_name or "").strip() == (goal_name or "").strip()
		and (row.kra_name or "").strip() == (kra_name or "").strip()
	]
	if not kpis:
		return None, False

	has_actuals = any(flt(k.actual) > 0 for k in kpis)
	if not has_actuals:
		return None, True

	# Weighted average of individual KPI scores (each already 0-5)
	total = sum(flt(k.score) * flt(k.weight) / 100.0 for k in kpis)
	return flt(total, 4), True


# ---------------------------------------------------------------------------
# Main appraisal → BSC update function
# ---------------------------------------------------------------------------

def update_bsc_goal_completion_from_appraisal(appraisal_doc):
	"""Update the linked BSC goal_completion table and goal_progression from submitted appraisal scores.

	Each appraisal goal row was created with label:
	  - Single goal  → "KRA Name: Description"
	  - Multi-goal   → "Goal Name — KRA Name: Description"
	We match rows back to BSC goals by the "Goal Name — " prefix (multi) or assign all rows to
	the single goal, then derive completion % from score_earned vs the maximum achievable score.

	If bsc.subordinate_contribution_pct > 0, blends in subordinate linked KRA scores.
	After updating, triggers supervisor BSC update if applicable.
	"""
	bsc_name = getattr(appraisal_doc, "balance_score_card", None)
	if not bsc_name or not frappe.db.exists("Balance Score Card", bsc_name):
		return

	bsc = frappe.get_doc("Balance Score Card", bsc_name)
	goals_grouped = _get_goals_grouped(bsc)
	num_goals = len(goals_grouped)

	# Build lookup: criteria label → employee self-rating (0-1 scale → convert to 0-5)
	self_rating_map = {}
	for sr in appraisal_doc.self_ratings or []:
		criteria_key = (sr.criteria or "").strip()
		if criteria_key:
			# Rating field stores 0-1; multiply by 5 to get same 0-5 scale as supervisor score
			self_rating_map[criteria_key] = flt(sr.rating) * 5

	own_completion_map = {}
	for goal_name, _kras in goals_grouped:
		goal_key = goal_name or _("(Unnamed goal)")

		# Collect appraisal goal rows that belong to this BSC goal
		total_earned = flt(0)
		total_possible = flt(0)  # sum of (5 * per_weightage / 100) = max achievable

		for appraisal_goal in appraisal_doc.goals or []:
			kra_text = (appraisal_goal.kra or "").strip()

			if num_goals == 1:
				# All appraisal goal rows belong to the single BSC goal
				belongs = True
			else:
				# Multi-goal: row starts with "Goal Name — "
				belongs = kra_text.startswith(f"{goal_name} \u2014 ")

			if belongs:
				# ── KPI path: if this KRA has KPIs with actuals, derive score from them ──
				raw_kra_name = _extract_kra_name_from_label(kra_text, goal_name, num_goals)
				kpi_score, has_kpis = _get_kra_kpi_score(bsc, goal_name, raw_kra_name)

				if kpi_score is not None:
					# KPI actuals entered → use KPI-derived 0-5 score directly
					effective_score = kpi_score
				else:
					# No KPIs (or actuals not yet entered) → normal appraisal score path
					supervisor_score = flt(appraisal_goal.score)
					self_score_5 = self_rating_map.get(kra_text, 0)
					if self_score_5 > 0:
						effective_score = (supervisor_score + self_score_5) / 2.0
					else:
						effective_score = supervisor_score

				total_earned += flt(effective_score * flt(appraisal_goal.per_weightage) / 100)
				total_possible += flt(5 * flt(appraisal_goal.per_weightage) / 100)

		if total_possible > 0:
			own_completion_map[goal_key] = flt(total_earned / total_possible * 100, 2)
		else:
			own_completion_map[goal_key] = 0

	# Blend subordinate contributions if configured
	completion_map = _blend_subordinate_contribution(bsc, own_completion_map)

	# _set_goal_completion_from_goals already computes and saves goal_progression
	# as a weighted average of completion_map (which uses averaged supervisor+self scores).
	_set_goal_completion_from_goals(bsc, completion_map)

	# Trigger supervisor BSC update (cascading up the hierarchy)
	_trigger_supervisor_bsc_update(bsc)


# ---------------------------------------------------------------------------
# Permission query
# ---------------------------------------------------------------------------

def get_permission_query_conditions(user):
	"""Restrict employees to only see their own Balance Score Cards.
	HR Managers, System Managers, and Supervisors can see all records.
	"""
	if not user:
		user = frappe.session.user
	privileged_roles = {"HR Manager", "System Manager", "Supervisor", "Administrator"}
	if privileged_roles.intersection(set(frappe.get_roles(user))):
		return None
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if employee:
		return "`tabBalance Score Card`.`employee` = {0}".format(frappe.db.escape(employee))
	return "1=0"


@frappe.whitelist()
def compare_bsc_with_appraisal(bsc_name, employee, cycle):
	"""Compare Balance Score Card targets with actual appraisal achievements."""
	bsc = frappe.get_doc("Balance Score Card", bsc_name)
	bsc_kras = {row.kra_name: row.weight for row in (bsc.goal_kras or [])}
	appraisal_name = frappe.db.get_value(
		"Appraisal",
		filters={
			"employee": employee,
			"appraisal_cycle": cycle,
			"docstatus": 1,
		},
		fieldname="name",
	)
	comparison_data = []
	if appraisal_name:
		appraisal = frappe.get_doc("Appraisal", appraisal_name)
		for goal in appraisal.goals:
			target_weight = bsc_kras.get(goal.kra, 0)
			achieved_weight = flt(goal.score_earned) or 0
			variance = achieved_weight - target_weight
			comparison_data.append({
				"kra": goal.kra,
				"target": target_weight,
				"achieved": achieved_weight,
				"variance": variance,
			})
	return comparison_data
