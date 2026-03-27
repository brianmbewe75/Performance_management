# Copyright (c) 2026 and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class BalanceScoreCardGoal(Document):
	def validate(self):
		# Validate KRAs under this goal sum to 100%
		if self.kras:
			total = sum(frappe.utils.flt(k.weight) for k in self.kras)
			if total and abs(total - 100.0) > 0.01:
				frappe.throw(
					_("Goal '{0}' KRAs must sum to 100%. Current total: {1}%").format(
						self.goal_name or "", total
					)
				)
