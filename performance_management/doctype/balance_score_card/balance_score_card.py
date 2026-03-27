# Copyright (c) 2026 and contributors
# License: MIT. See LICENSE

from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class BalanceScoreCard(Document):
	def validate(self):
		self.validate_weights()
		self.validate_employee_hierarchy()
		self.validate_cycle_status()
		self.calculate_total_weight()

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
		if not self.is_new() or frappe.session.user == "Administrator":
			return
		current_user = frappe.session.user
		employee = frappe.db.get_value("Employee", {"user_id": current_user}, "name")
		if not employee and current_user != "Administrator":
			frappe.throw(_("Only employees can create Balance Score Cards"))
		if current_user == "Administrator":
			return
		reports_to = frappe.db.get_value("Employee", employee, "reports_to")
		is_top_supervisor = not reports_to
		if is_top_supervisor:
			subordinates = frappe.get_all(
				"Employee", filters={"reports_to": employee}, pluck="name"
			)
			allowed = [employee] + list(subordinates)
			if self.employee not in allowed:
				frappe.throw(_("You can only create Balance Score Cards for yourself or your subordinates"))
		else:
			subordinates = frappe.get_all(
				"Employee", filters={"reports_to": employee}, pluck="name"
			)
			if self.employee not in subordinates:
				if self.employee == employee:
					frappe.throw(_("Supervisors cannot create Balance Score Cards for themselves"))
				else:
					frappe.throw(_("You can only create Balance Score Cards for your subordinates"))

	def validate_cycle_status(self):
		if not self.appraisal_cycle:
			return
		cycle_status = frappe.db.get_value("Appraisal Cycle", self.appraisal_cycle, "status")
		if cycle_status == "Completed":
			frappe.throw(_("Balance Score Card can only be created for cycles that are not Completed."))

	def calculate_total_weight(self):
		total = sum(flt(row.weight) for row in (self.goal_kras or []))
		self.total_weight = total

	def before_submit(self):
		from frappe.model.workflow import get_workflow_name
		if get_workflow_name("Balance Score Card"):
			return
		if self.docstatus == 1 and self.status == "Draft":
			self.status = "Pending Employee Approval"
			self.send_for_employee_approval()

	def on_submit(self):
		"""Create draft Appraisal as soon as BSC is submitted (so it exists for the cycle)."""
		self.create_draft_appraisals()

	def on_update_after_submit(self):
		if self._is_workflow_approved_state():
			self.create_draft_appraisals()
			return
		if self.status == "Pending Employee Approval":
			if self.employee_approved == "Approved":
				self.status = "Approved"
				self.db_set("status", "Approved")
				self.create_draft_appraisals()
			elif self.employee_approved == "Rejected":
				self.status = "Rejected by Employee"
				self.db_set("status", "Rejected by Employee")
				self.send_back_to_supervisor()
		elif self.status == "Approved":
			self.create_draft_appraisals()

	def _is_workflow_approved_state(self):
		from frappe.model.workflow import get_workflow_name
		workflow_name = get_workflow_name("Balance Score Card")
		if not workflow_name:
			return False
		workflow = frappe.get_cached_doc("Workflow", workflow_name)
		field = workflow.workflow_state_field
		value = self.get(field)
		if not value:
			return False
		if field == "status" and value == "Approved":
			return True
		if value == "Approved":
			return True
		for state in workflow.states or []:
			if state.state == value and cint(state.doc_status) == 1:
				if state.update_field == "status" and (state.update_value or "").strip() == "Approved":
					return True
		return False

	def send_for_employee_approval(self):
		user_id = frappe.db.get_value("Employee", self.employee, "user_id")
		if user_id:
			frappe.sendmail(
				recipients=[user_id],
				subject=_("Balance Score Card Pending Your Approval"),
				message=_("Your supervisor has created a Balance Score Card for you. Please review and approve/reject."),
			)

	def send_back_to_supervisor(self):
		if not self.supervisor:
			return
		user_id = frappe.db.get_value("Employee", self.supervisor, "user_id")
		if user_id:
			frappe.sendmail(
				recipients=[user_id],
				subject=_("Balance Score Card Rejected"),
				message=_("Your subordinate has rejected the Balance Score Card. Please make adjustments."),
			)

	def create_draft_appraisals(self):
		# Create only once per BSC
		if frappe.db.exists("Appraisal", {"balance_score_card": self.name}):
			return
		try:
			from hrms.hr.doctype.appraisal.appraisal import Appraisal
		except ImportError:
			frappe.msgprint(
				_("HRMS Appraisal not found. Install hrms app to auto-create Appraisal from BSC."),
				indicator="orange",
			)
			return
		cycle = frappe.db.get_value(
			"Appraisal Cycle", self.appraisal_cycle, ["start_date", "end_date", "company"], as_dict=True
		)
		if not cycle:
			return
		appraisal = frappe.new_doc("Appraisal")
		appraisal.employee = self.employee
		appraisal.appraisal_cycle = self.appraisal_cycle
		appraisal.company = cycle.company or frappe.db.get_value("Employee", self.employee, "company")
		appraisal.start_date = cycle.start_date
		appraisal.end_date = cycle.end_date
		appraisal.rate_goals_manually = 1
		if hasattr(appraisal, "balance_score_card"):
			appraisal.balance_score_card = self.name
		for row in self.goal_kras:
			appraisal.append(
				"goals",
				{"kra": row.kra_name, "per_weightage": flt(row.weight), "score": 0, "score_earned": 0},
			)
		appraisal.flags.ignore_permissions = True
		appraisal.insert()
		# Set goal completion tracking: one row per goal at 0%
		_set_goal_completion_from_goals(self, completion_map=None)
		frappe.msgprint(
			_("Draft Appraisal {0} created.").format(frappe.utils.get_link_to_form("Appraisal", appraisal.name)),
			indicator="green",
		)


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
	"""Set BSC goal_completion child table: one row per goal. completion_map = { goal_name: completion_percent } or None (all 0)."""
	goals_grouped = _get_goals_grouped(bsc_doc)
	frappe.db.sql(
		"DELETE FROM `tabBalance Score Card Goal Completion` WHERE parent = %s AND parenttype = 'Balance Score Card'",
		(bsc_doc.name,),
	)
	for goal_name, _kras in goals_grouped:
		pct = flt(completion_map.get(goal_name, 0)) if completion_map else 0
		row = frappe.get_doc(
			{
				"doctype": "Balance Score Card Goal Completion",
				"parent": bsc_doc.name,
				"parenttype": "Balance Score Card",
				"parentfield": "goal_completion",
				"goal_name": goal_name or _("(Unnamed goal)"),
				"completion_percent": pct,
			}
		)
		row.insert(ignore_permissions=True)
	frappe.db.commit()
	frappe.clear_cache(doctype="Balance Score Card")


def update_bsc_goal_completion_from_appraisal(appraisal_doc):
	"""Update the linked BSC's goal_completion table from appraisal scores (call from Appraisal on_submit)."""
	bsc_name = getattr(appraisal_doc, "balance_score_card", None)
	if not bsc_name or not frappe.db.exists("Balance Score Card", bsc_name):
		return
	bsc = frappe.get_doc("Balance Score Card", bsc_name)
	goals_grouped = _get_goals_grouped(bsc)
	# Build kra -> score_earned from appraisal
	appraisal_kra_earned = {}
	for g in appraisal_doc.goals or []:
		kra = (g.kra or "").strip()
		appraisal_kra_earned[kra] = flt(g.score_earned)
	completion_map = {}
	for goal_name, kras in goals_grouped:
		total_earned = sum(appraisal_kra_earned.get(k, 0) for k in kras)
		completion_map[goal_name or _("(Unnamed goal)")] = total_earned
	_set_goal_completion_from_goals(bsc, completion_map)


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
