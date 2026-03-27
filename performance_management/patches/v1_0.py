# Copyright (c) 2026 and contributors
# License: MIT. See LICENSE

"""Patches for performance_management. Balance Score Card is workflow-compatible; user-defined workflows are not deactivated."""

import frappe


def execute():
	"""Patch entry point (required by Frappe patch handler). No-op: user-defined workflows for Balance Score Card remain active."""
	pass
