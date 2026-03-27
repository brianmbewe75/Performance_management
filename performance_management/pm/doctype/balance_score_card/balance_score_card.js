/* eslint-disable */
/* Balance Score Card - Goals & KRAs UI (like Bulk Budget Planner): add goals, then per goal add multiple KRAs */
(function () {
	function flt(val) {
		var n = parseFloat(val);
		return isNaN(n) ? 0 : n;
	}
	function escape_html(s) {
		if (s == null || s === undefined) return "";
		return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
	}

	// Determine if the goals/KRAs section is editable.
	// When a workflow is active, only the "Draft" state allows editing goals.
	// When submitted (docstatus=1), goals are always read-only.
	function is_goals_editable(frm) {
		if (frm.doc.__islocal) return true;
		if (frm.doc.docstatus === 1) return false;
		var state_fieldname = frappe.workflow.get_state_fieldname(frm.doctype);
		if (state_fieldname) {
			var state = frm.doc[state_fieldname];
			return !state || state === "Draft";
		}
		return frm.doc.docstatus === 0;
	}

	// Build grouped data from frm.doc.goal_kras: consecutive rows with same goal_name = one goal
	function get_goals_data(frm) {
		var rows = frm.doc.goal_kras || [];
		var groups = [];
		for (var i = 0; i < rows.length; i++) {
			var r = rows[i];
			var g = (r && r.goal_name) != null ? String(r.goal_name).trim() : "";
			var prev = groups.length ? groups[groups.length - 1] : null;
			if (!prev || (prev.goal_name !== g)) {
				groups.push({ goal_name: g, kras: [] });
				prev = groups[groups.length - 1];
			}
			prev.kras.push({
				kra_name: (r && r.kra_name) != null ? String(r.kra_name).trim() : "",
				description: (r && r.description) != null ? String(r.description).trim() : "",
				weight: r && r.weight != null ? flt(r.weight) : 0,
			});
		}
		return groups;
	}

	// Sync collected goals/kras into frm.doc.goal_kras (clear table and add rows)
	function sync_goal_kras_to_doc(frm, goals_data) {
		frm.clear_table("goal_kras");
		goals_data.forEach(function (g) {
			var goal_name = (g && g.goal_name) ? String(g.goal_name).trim() : "";
			var kras = (g && g.kras) || [];
			if (kras.length === 0) kras = [{ kra_name: "", description: "", weight: 0 }];
			kras.forEach(function (k) {
				frm.add_child("goal_kras", {
					goal_name: goal_name,
					kra_name: (k && k.kra_name) ? String(k.kra_name).trim() : "",
					description: (k && k.description) ? String(k.description).trim() : "",
					weight: k && k.weight != null ? flt(k.weight) : 0,
				});
			});
		});
		frm.refresh_field("goal_kras");
		frm.dirty();
	}

	function render_goals_kras_ui(frm) {
		var wrapper = frm.fields_dict.goals_kras_ui && frm.fields_dict.goals_kras_ui.$wrapper;
		if (!wrapper) return;

		var editable = is_goals_editable(frm);
		var dis = editable ? "" : " disabled='disabled'";
		var btn_hide = editable ? "" : " style='display:none'";

		var goals_data = get_goals_data(frm);
		if (!goals_data.length) goals_data = [{ goal_name: "", kras: [{ kra_name: "", description: "", weight: 0 }] }];

		var html = "<div id='bsc-goals-kras-root' class='bsc-goals-kras'></div>";
		wrapper.html(html);
		var root = document.getElementById("bsc-goals-kras-root");
		if (!root) return;

		goals_data.forEach(function (goal, goalIdx) {
			var goalDiv = document.createElement("div");
			goalDiv.className = "card mb-3 bsc-goal-block";
			goalDiv.dataset.goalIdx = goalIdx;
			var kras = (goal.kras || []).length ? goal.kras : [{ kra_name: "", description: "", weight: 0 }];
			var krasRows = kras
				.map(
					function (k, kIdx) {
						return (
							"<tr data-kra-idx='" +
							kIdx +
							"'>" +
							"<td><input type='text' class='form-control form-control-sm kra-name' data-goal-idx='" +
							goalIdx +
							"' data-kra-idx='" +
							kIdx +
							"' placeholder='" +
							escape_html(__("KRA Name")) +
							"' value='" +
							escape_html((k && k.kra_name) || "") +
							"'" + dis + " /></td>" +
							"<td><input type='text' class='form-control form-control-sm kra-desc' data-goal-idx='" +
							goalIdx +
							"' data-kra-idx='" +
							kIdx +
							"' placeholder='" +
							escape_html(__("Description")) +
							"' value='" +
							escape_html((k && k.description) || "") +
							"'" + dis + " /></td>" +
							"<td style='width:100px'><input type='number' class='form-control form-control-sm kra-weight' step='0.01' min='0' max='100' data-goal-idx='" +
							goalIdx +
							"' data-kra-idx='" +
							kIdx +
							"' value='" +
							(k && k.weight != null ? flt(k.weight) : "") +
							"'" + dis + " /></td>" +
							"<td style='width:50px'><button type='button' class='btn btn-sm btn-default remove-kra' data-goal-idx='" +
							goalIdx +
							"' data-kra-idx='" +
							kIdx +
							"'" + btn_hide + ">×</button></td>" +
							"</tr>"
						);
					}
				)
				.join("");
			goalDiv.innerHTML =
				"<div class='card-body'>" +
				"<div class='row align-items-center mb-2'>" +
				"<div class='col-md-6'>" +
				"<label class='small'>" +
				__("Goal Name") +
				"</label>" +
				"<input type='text' class='form-control form-control-sm goal-name' data-goal-idx='" +
				goalIdx +
				"' placeholder='" +
				escape_html(__("Goal name")) +
				"' value='" +
				escape_html((goal.goal_name || "")) +
				"'" + dis + " />" +
				"</div>" +
				"<div class='col-auto'>" +
				"<button type='button' class='btn btn-sm btn-danger remove-goal' data-goal-idx='" +
				goalIdx +
				"'" + btn_hide + ">" +
				__("Remove goal") +
				"</button>" +
				"</div>" +
				"</div>" +
				"<label class='small'>" +
				__("KRAs (weights per goal must total 100%)") +
				"</label>" +
				"<table class='table table-sm table-bordered kra-table' data-goal-idx='" +
				goalIdx +
				"'><thead><tr><th>" +
				__("KRA Name") +
				"</th><th>" +
				__("Description") +
				"</th><th>" +
				__("Weight (%)") +
				"</th><th width='50'></th></tr></thead><tbody>" +
				krasRows +
				"</tbody></table>" +
				"<button type='button' class='btn btn-sm btn-secondary add-kra' data-goal-idx='" +
				goalIdx +
				"'" + btn_hide + ">" +
				__("+ Add KRA") +
				"</button>" +
				"</div>";
			root.appendChild(goalDiv);
		});

		if (editable) {
			var addGoalBtn = document.createElement("button");
			addGoalBtn.type = "button";
			addGoalBtn.className = "btn btn-sm btn-primary mt-2";
			addGoalBtn.textContent = __("+ Add goal");
			addGoalBtn.onclick = function () {
				var data = collect_goals_from_dom(frm);
				data.push({ goal_name: "", kras: [{ kra_name: "", description: "", weight: 0 }] });
				sync_goal_kras_to_doc(frm, data);
				render_goals_kras_ui(frm);
				bind_bsc_events(frm);
			};
			root.appendChild(addGoalBtn);
		}

		if (editable) {
			bind_bsc_events(frm);
		}
	}

	function add_kra_row(tbody, goalIdx, kraIdx, kra_name, description, weight, editable) {
		var dis = editable ? "" : " disabled='disabled'";
		var btn_hide = editable ? "" : " style='display:none'";
		var tr = document.createElement("tr");
		tr.dataset.kraIdx = kraIdx;
		tr.innerHTML =
			"<td><input type='text' class='form-control form-control-sm kra-name' data-goal-idx='" +
			goalIdx +
			"' data-kra-idx='" +
			kraIdx +
			"' placeholder='" +
			escape_html(__("KRA Name")) +
			"' value='" +
			escape_html(kra_name || "") +
			"'" + dis + " /></td>" +
			"<td><input type='text' class='form-control form-control-sm kra-desc' data-goal-idx='" +
			goalIdx +
			"' data-kra-idx='" +
			kraIdx +
			"' placeholder='" +
			escape_html(__("Description")) +
			"' value='" +
			escape_html(description || "") +
			"'" + dis + " /></td>" +
			"<td style='width:100px'><input type='number' class='form-control form-control-sm kra-weight' step='0.01' min='0' max='100' data-goal-idx='" +
			goalIdx +
			"' data-kra-idx='" +
			kraIdx +
			"' value='" +
			(weight != null ? flt(weight) : "") +
			"'" + dis + " /></td>" +
			"<td style='width:50px'><button type='button' class='btn btn-sm btn-default remove-kra' data-goal-idx='" +
			goalIdx +
			"' data-kra-idx='" +
			kraIdx +
			"'" + btn_hide + ">×</button></td>";
		tbody.appendChild(tr);
	}

	function collect_goals_from_dom(frm) {
		var root = document.getElementById("bsc-goals-kras-root");
		if (!root) return get_goals_data(frm);

		var data = [];
		root.querySelectorAll(".bsc-goal-block").forEach(function (card) {
			var goalIdx = parseInt(card.dataset.goalIdx, 10);
			var goalInp = card.querySelector("input.goal-name");
			var goal_name = (goalInp && goalInp.value) ? String(goalInp.value).trim() : "";
			var kras = [];
			card.querySelectorAll(".kra-table tbody tr").forEach(function (tr) {
				var nameInp = tr.querySelector("input.kra-name");
				var descInp = tr.querySelector("input.kra-desc");
				var weightInp = tr.querySelector("input.kra-weight");
				kras.push({
					kra_name: (nameInp && nameInp.value) ? String(nameInp.value).trim() : "",
					description: (descInp && descInp.value) ? String(descInp.value).trim() : "",
					weight: weightInp ? flt(weightInp.value) : 0,
				});
			});
			if (!kras.length) kras = [{ kra_name: "", description: "", weight: 0 }];
			data.push({ goal_name: goal_name, kras: kras });
		});
		return data;
	}

	function sync_dom_to_goal_kras(frm) {
		var root = document.getElementById("bsc-goals-kras-root");
		if (!root) return;
		var data = collect_goals_from_dom(frm);
		sync_goal_kras_to_doc(frm, data);
	}

	function bind_bsc_events(frm) {
		var root = document.getElementById("bsc-goals-kras-root");
		if (!root) return;

		root.querySelectorAll("input.goal-name").forEach(function (inp) {
			inp.onchange = inp.onblur = function () {
				sync_dom_to_goal_kras(frm);
			};
		});
		root.querySelectorAll("input.kra-name, input.kra-desc").forEach(function (inp) {
			inp.onchange = inp.onblur = function () {
				sync_dom_to_goal_kras(frm);
			};
		});
		root.querySelectorAll("input.kra-weight").forEach(function (inp) {
			inp.onchange = inp.onblur = function () {
				var v = flt(inp.value);
				if (v < 0 || v > 100) {
					frappe.msgprint(__("Weight must be between 0 and 100"));
					inp.value = "";
				}
				sync_dom_to_goal_kras(frm);
			};
		});

		root.querySelectorAll(".remove-goal").forEach(function (btn) {
			btn.onclick = function () {
				var goalIdx = parseInt(btn.dataset.goalIdx, 10);
				var data = collect_goals_from_dom(frm);
				data.splice(goalIdx, 1);
				if (!data.length) data = [{ goal_name: "", kras: [{ kra_name: "", description: "", weight: 0 }] }];
				sync_goal_kras_to_doc(frm, data);
				render_goals_kras_ui(frm);
				bind_bsc_events(frm);
			};
		});

		root.querySelectorAll(".add-kra").forEach(function (btn) {
			btn.onclick = function () {
				var goalIdx = parseInt(btn.dataset.goalIdx, 10);
				var card = root.querySelector(".bsc-goal-block[data-goal-idx='" + goalIdx + "']");
				if (!card) return;
				var tbody = card.querySelector(".kra-table tbody");
				if (!tbody) return;
				var nextIdx = tbody.querySelectorAll("tr").length;
				add_kra_row(tbody, goalIdx, nextIdx, "", "", 0, true);
				sync_dom_to_goal_kras(frm);
				bind_bsc_events(frm);
			};
		});

		root.querySelectorAll(".remove-kra").forEach(function (btn) {
			btn.onclick = function () {
				var tr = btn.closest ? btn.closest("tr") : null;
				if (tr) tr.remove();
				sync_dom_to_goal_kras(frm);
			};
		});
	}

	frappe.ui.form.on("Balance Score Card", {
		refresh: function (frm) {
			render_goals_kras_ui(frm);

			// Detect if a workflow is active for this doctype
			var state_fieldname = frappe.workflow.get_state_fieldname(frm.doctype);
			var wf_state = state_fieldname ? frm.doc[state_fieldname] : null;

			// "Approved" can be driven by the workflow_state field OR the legacy status field
			var is_approved = frm.doc.status === "Approved" || wf_state === "Approved";

			// Custom Approve/Reject buttons: only shown when NO workflow is active.
			// When a workflow IS active, Frappe renders workflow action buttons automatically
			// in the Actions menu — no need for custom buttons.
			if (!state_fieldname) {
				if (
					frm.doc.status == "Pending Employee Approval" &&
					frm.doc.employee
				) {
					// Use callback form of get_value — the synchronous form returns a Promise, not a value
					frappe.db.get_value("Employee", frm.doc.employee, "user_id", function (r) {
						if (r && r.user_id && r.user_id === frappe.session.user) {
							frm.add_custom_button(__("Approve"), function () {
								frm.set_value("employee_approved", "Approved");
								frm.save();
							}).addClass("btn-primary");
							frm.add_custom_button(__("Reject"), function () {
								frm.set_value("employee_approved", "Rejected");
								frm.save();
							}).addClass("btn-danger");
						}
					});
				}
			}

			// "Sync KRAs to Appraisal" button — available on submitted BSC to re-push KRAs
			// into the linked draft Appraisal (useful if appraisal was created before KRAs were set)
			if (frm.doc.docstatus === 1 && frm.doc.name) {
				frm.add_custom_button(__("Sync KRAs to Appraisal"), function () {
					frappe.confirm(
						__("This will clear and re-populate the Goals and Self Ratings on the linked draft Appraisal from the current BSC KRAs. Continue?"),
						function () {
							frappe.call({
								method: "performance_management.pm.doctype.balance_score_card.balance_score_card.sync_appraisal_criteria",
								args: { bsc_name: frm.doc.name },
								callback: function () { frm.reload_doc(); },
							});
						}
					);
				}).addClass("btn-warning");
			}

			// "Compare with Appraisal" button — show when the BSC is in Approved state
			// (works for both workflow-driven and legacy status-driven approval)
			if (is_approved && frm.doc.name) {
				frm.add_custom_button(__("Compare with Appraisal"), function () {
					frappe.call({
						method: "performance_management.pm.doctype.balance_score_card.balance_score_card.compare_bsc_with_appraisal",
						args: {
							bsc_name: frm.doc.name,
							employee: frm.doc.employee,
							cycle: frm.doc.appraisal_cycle,
						},
						callback: function (r) {
							if (r.message && r.message.length) {
								var html =
									"<table class='table table-bordered'><thead><tr><th>" +
									__("KRA") +
									"</th><th>" +
									__("Target %") +
									"</th><th>" +
									__("Achieved %") +
									"</th><th>" +
									__("Variance") +
									"</th></tr></thead><tbody>";
								r.message.forEach(function (row) {
									var cls = row.variance < 0 ? "text-danger" : "text-success";
									html +=
										"<tr><td>" +
										(row.kra || "") +
										"</td><td>" +
										(row.target || 0) +
										"</td><td>" +
										(row.achieved || 0) +
										"</td><td class='" +
										cls +
										"'>" +
										(row.variance || 0) +
										"</td></tr>";
								});
								html += "</tbody></table>";
								frappe.msgprint({ title: __("BSC vs Appraisal"), message: html, wide: true });
							} else {
								frappe.msgprint(__("No appraisal data found for comparison."));
							}
						},
					});
				}).addClass("btn-info");
			}
		},
	});

	// Before save: sync DOM -> goal_kras so server receives the table
	frappe.ui.form.on("Balance Score Card", {
		before_save: function (frm) {
			var root = document.getElementById("bsc-goals-kras-root");
			if (root) {
				var data = collect_goals_from_dom(frm);
				sync_goal_kras_to_doc(frm, data);
			}
		},
	});
})();
