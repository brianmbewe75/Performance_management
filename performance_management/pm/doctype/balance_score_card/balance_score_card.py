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
		self.validate_employee_hierarchy()
		self.validate_cycle_status()
		self.calculate_total_weight()

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

	def on_submit(self):
		"""Create draft Appraisal as soon as BSC reaches submitted state."""
		self.create_draft_appraisals()

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
	"""Set BSC goal_completion child table: one row per goal. completion_map = { goal_name: completion_percent } or None (all 0).
	Also sets BSC goal_progression (overall %) as weighted average of completion_map when provided."""
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
	frappe.db.commit()
	frappe.clear_cache(doctype="Balance Score Card")


def update_bsc_goal_completion_from_appraisal(appraisal_doc):
	"""Update the linked BSC goal_completion table and goal_progression from submitted appraisal scores.

	Each appraisal goal row was created with label:
	  - Single goal  → "KRA Name: Description"
	  - Multi-goal   → "Goal Name — KRA Name: Description"
	We match rows back to BSC goals by the "Goal Name — " prefix (multi) or assign all rows to
	the single goal, then derive completion % from score_earned vs the maximum achievable score.
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

	completion_map = {}
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
				supervisor_score = flt(appraisal_goal.score)
				# Look up matching self-rating by the same KRA label
				self_score_5 = self_rating_map.get(kra_text, 0)
				# Average supervisor + employee self-score; fall back to supervisor only if self-rating not entered
				if self_score_5 > 0:
					effective_score = (supervisor_score + self_score_5) / 2.0
				else:
					effective_score = supervisor_score
				# Effective contribution = effective_score × per_weightage / 100
				total_earned += flt(effective_score * flt(appraisal_goal.per_weightage) / 100)
				# Max possible = 5 (max score) × per_weightage / 100
				total_possible += flt(5 * flt(appraisal_goal.per_weightage) / 100)

		if total_possible > 0:
			completion_map[goal_key] = flt(total_earned / total_possible * 100, 2)
		else:
			completion_map[goal_key] = 0

	# _set_goal_completion_from_goals already computes and saves goal_progression
	# as a weighted average of completion_map (which uses averaged supervisor+self scores).
	_set_goal_completion_from_goals(bsc, completion_map)


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
