# Copyright (c) 2026 and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class AppraisalCycle(Document):
	"""Named appraisal period (e.g. FY2025-H1) with start/end dates and phase status."""

	def validate(self):
		if self.start_date and self.end_date and self.start_date > self.end_date:
			frappe.throw(
				_("End Date must be on or after Start Date."),
				title=_("Invalid Dates"),
			)
