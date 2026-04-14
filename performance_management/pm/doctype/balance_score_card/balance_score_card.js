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
	// Editable when: docstatus==0 AND status in ["Draft", "Rejected"]
	// Read-only when: status == "Pending Supervisor Approval" OR docstatus == 1
	function is_goals_editable(frm) {
		if (frm.doc.__islocal) return true;
		if (frm.doc.docstatus === 1) return false;
		var status = frm.doc.status;
		if (status === "Pending Supervisor Approval" || status === "Approved") return false;
		return frm.doc.docstatus === 0 && (status === "Draft" || status === "Rejected");
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
				linked_to_supervisor_kra: (r && r.linked_to_supervisor_kra) ? String(r.linked_to_supervisor_kra).trim() : "",
				is_cascaded: r && r.is_cascaded ? 1 : 0,
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
			if (kras.length === 0) kras = [{ kra_name: "", description: "", weight: 0, linked_to_supervisor_kra: "", is_cascaded: 0 }];
			kras.forEach(function (k) {
				frm.add_child("goal_kras", {
					goal_name: goal_name,
					kra_name: (k && k.kra_name) ? String(k.kra_name).trim() : "",
					description: (k && k.description) ? String(k.description).trim() : "",
					weight: k && k.weight != null ? flt(k.weight) : 0,
					linked_to_supervisor_kra: (k && k.linked_to_supervisor_kra) ? String(k.linked_to_supervisor_kra).trim() : "",
					is_cascaded: k && k.is_cascaded ? 1 : 0,
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
		if (!goals_data.length) goals_data = [{ goal_name: "", kras: [{ kra_name: "", description: "", weight: 0, linked_to_supervisor_kra: "", is_cascaded: 0 }] }];

		var html = "<div id='bsc-goals-kras-root' class='bsc-goals-kras'></div>";
		wrapper.html(html);
		var root = document.getElementById("bsc-goals-kras-root");
		if (!root) return;

		goals_data.forEach(function (goal, goalIdx) {
			var goalDiv = document.createElement("div");
			goalDiv.className = "card mb-3 bsc-goal-block";
			goalDiv.dataset.goalIdx = goalIdx;
			var kras = (goal.kras || []).length ? goal.kras : [{ kra_name: "", description: "", weight: 0, linked_to_supervisor_kra: "", is_cascaded: 0 }];
			var krasRows = kras
				.map(
					function (k, kIdx) {
						var linked_indicator = "";
						if (k && k.linked_to_supervisor_kra) {
							linked_indicator = "<div class='text-muted small mt-1' style='color:#888;font-style:italic'>" +
								"&#128279; " + __("Linked to supervisor KRA") + ": " +
								escape_html(k.linked_to_supervisor_kra) +
								(k.is_cascaded ? " <span class='badge badge-secondary'>" + __("Cascaded") + "</span>" : "") +
								"</div>";
						}
						return (
							"<tr data-kra-idx='" +
							kIdx +
							"'>" +
							"<td>" +
							"<input type='text' class='form-control form-control-sm kra-name' data-goal-idx='" +
							goalIdx +
							"' data-kra-idx='" +
							kIdx +
							"' placeholder='" +
							escape_html(__("KRA Name")) +
							"' value='" +
							escape_html((k && k.kra_name) || "") +
							"'" + dis + " />" +
							linked_indicator +
							"</td>" +
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
				data.push({ goal_name: "", kras: [{ kra_name: "", description: "", weight: 0, linked_to_supervisor_kra: "", is_cascaded: 0 }] });
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

	function add_kra_row(tbody, goalIdx, kraIdx, kra_name, description, weight, editable, linked_to_supervisor_kra, is_cascaded) {
		var dis = editable ? "" : " disabled='disabled'";
		var btn_hide = editable ? "" : " style='display:none'";
		var linked_indicator = "";
		if (linked_to_supervisor_kra) {
			linked_indicator = "<div class='text-muted small mt-1' style='color:#888;font-style:italic'>" +
				"&#128279; " + __("Linked to supervisor KRA") + ": " +
				escape_html(linked_to_supervisor_kra) +
				(is_cascaded ? " <span class='badge badge-secondary'>" + __("Cascaded") + "</span>" : "") +
				"</div>";
		}
		var tr = document.createElement("tr");
		tr.dataset.kraIdx = kraIdx;
		tr.innerHTML =
			"<td>" +
			"<input type='text' class='form-control form-control-sm kra-name' data-goal-idx='" +
			goalIdx +
			"' data-kra-idx='" +
			kraIdx +
			"' placeholder='" +
			escape_html(__("KRA Name")) +
			"' value='" +
			escape_html(kra_name || "") +
			"'" + dis + " />" +
			linked_indicator +
			"</td>" +
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

		// Build a map of existing kra metadata (linked_to_supervisor_kra, is_cascaded) from frm.doc.goal_kras
		// keyed by goalIdx+kraIdx so we can preserve them since DOM inputs don't track them
		var existing_rows = frm.doc.goal_kras || [];
		var meta_map = {};
		var goal_groups = [];
		existing_rows.forEach(function (r) {
			var g = (r && r.goal_name) ? String(r.goal_name).trim() : "";
			var found = false;
			for (var gi = 0; gi < goal_groups.length; gi++) {
				if (goal_groups[gi] === g) { found = true; break; }
			}
			if (!found) goal_groups.push(g);
		});
		var goal_kra_counters = {};
		existing_rows.forEach(function (r) {
			var g = (r && r.goal_name) ? String(r.goal_name).trim() : "";
			var gi = goal_groups.indexOf(g);
			if (!goal_kra_counters[gi]) goal_kra_counters[gi] = 0;
			var ki = goal_kra_counters[gi]++;
			meta_map[gi + "_" + ki] = {
				linked_to_supervisor_kra: (r && r.linked_to_supervisor_kra) ? String(r.linked_to_supervisor_kra).trim() : "",
				is_cascaded: r && r.is_cascaded ? 1 : 0,
			};
		});

		var data = [];
		root.querySelectorAll(".bsc-goal-block").forEach(function (card) {
			var goalIdx = parseInt(card.dataset.goalIdx, 10);
			var goalInp = card.querySelector("input.goal-name");
			var goal_name = (goalInp && goalInp.value) ? String(goalInp.value).trim() : "";
			var kras = [];
			var kraIdx = 0;
			card.querySelectorAll(".kra-table tbody tr").forEach(function (tr) {
				var nameInp = tr.querySelector("input.kra-name");
				var descInp = tr.querySelector("input.kra-desc");
				var weightInp = tr.querySelector("input.kra-weight");
				var meta = meta_map[goalIdx + "_" + kraIdx] || {};
				kras.push({
					kra_name: (nameInp && nameInp.value) ? String(nameInp.value).trim() : "",
					description: (descInp && descInp.value) ? String(descInp.value).trim() : "",
					weight: weightInp ? flt(weightInp.value) : 0,
					linked_to_supervisor_kra: meta.linked_to_supervisor_kra || "",
					is_cascaded: meta.is_cascaded || 0,
				});
				kraIdx++;
			});
			if (!kras.length) kras = [{ kra_name: "", description: "", weight: 0, linked_to_supervisor_kra: "", is_cascaded: 0 }];
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
				if (!data.length) data = [{ goal_name: "", kras: [{ kra_name: "", description: "", weight: 0, linked_to_supervisor_kra: "", is_cascaded: 0 }] }];
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
				add_kra_row(tbody, goalIdx, nextIdx, "", "", 0, true, "", 0);
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

	// Show the "Load from Supervisor BSC" dialog
	function show_load_supervisor_kras_dialog(frm) {
		frappe.call({
			method: "performance_management.pm.doctype.balance_score_card.balance_score_card.get_supervisor_bsc_kras",
			args: {
				employee: frm.doc.employee,
				cycle: frm.doc.appraisal_cycle,
			},
			callback: function (r) {
				var kras = (r && r.message) ? r.message : [];
				if (!kras || !kras.length) {
					frappe.msgprint(__("No approved supervisor BSC found for this cycle, or supervisor has no KRAs."));
					return;
				}

				// Build table rows for the dialog
				var rows_html = kras.map(function (k, idx) {
					return "<tr data-idx='" + idx + "'>" +
						"<td style='text-align:center'><input type='checkbox' class='sup-kra-check' data-idx='" + idx + "' checked /></td>" +
						"<td>" + escape_html(k.goal_name || "") + "</td>" +
						"<td>" + escape_html(k.kra_name || "") + "</td>" +
						"<td>" + escape_html(k.description || "") + "</td>" +
						"<td>" + (k.weight || 0) + "</td>" +
						"<td style='text-align:center'>" +
						"<label class='mr-2'><input type='radio' name='link_mode_" + idx + "' value='link' checked /> " + __("Link") + "</label>" +
						"<label><input type='radio' name='link_mode_" + idx + "' value='copy' /> " + __("Copy") + "</label>" +
						"</td>" +
						"</tr>";
				}).join("");

				var dialog_content = "<p class='text-muted'>" + __("Select which KRAs to import from your supervisor's BSC. 'Link' will link the KRA to the supervisor KRA for subordinate contribution blending. 'Copy' will import a standalone copy.") + "</p>" +
					"<div style='overflow-x:auto'>" +
					"<table class='table table-sm table-bordered'>" +
					"<thead><tr>" +
					"<th style='width:40px'><input type='checkbox' id='sup-kra-select-all' checked /></th>" +
					"<th>" + __("Goal") + "</th>" +
					"<th>" + __("KRA Name") + "</th>" +
					"<th>" + __("Description") + "</th>" +
					"<th>" + __("Weight %") + "</th>" +
					"<th>" + __("Mode") + "</th>" +
					"</tr></thead>" +
					"<tbody>" + rows_html + "</tbody>" +
					"</table>" +
					"</div>";

				var d = new frappe.ui.Dialog({
					title: __("Load KRAs from Supervisor BSC"),
					fields: [
						{
							fieldtype: "HTML",
							fieldname: "kra_table",
							options: dialog_content,
						},
					],
					primary_action_label: __("Import Selected"),
					primary_action: function () {
						var selected = [];
						d.$wrapper.find(".sup-kra-check:checked").each(function () {
							var idx = parseInt($(this).data("idx"), 10);
							var mode = d.$wrapper.find("input[name='link_mode_" + idx + "']:checked").val();
							selected.push({ kra: kras[idx], mode: mode });
						});

						if (!selected.length) {
							frappe.msgprint(__("No KRAs selected."));
							return;
						}

						// Collect current goals data
						var current_data = collect_goals_from_dom(frm);

						// Add selected KRAs: group by goal_name
						selected.forEach(function (item) {
							var k = item.kra;
							var mode = item.mode;
							var goal_name = k.goal_name || "";
							// Find existing goal group or create new
							var goal_group = null;
							for (var gi = 0; gi < current_data.length; gi++) {
								if (current_data[gi].goal_name === goal_name) {
									goal_group = current_data[gi];
									break;
								}
							}
							if (!goal_group) {
								goal_group = { goal_name: goal_name, kras: [] };
								current_data.push(goal_group);
							}
							goal_group.kras.push({
								kra_name: k.kra_name || "",
								description: k.description || "",
								weight: flt(k.weight) || 0,
								linked_to_supervisor_kra: mode === "link" ? (k.kra_name || "") : "",
								is_cascaded: mode === "link" ? 1 : 0,
							});
						});

						// Remove empty default row if present (goal_name="" with empty kra)
						current_data = current_data.filter(function (g) {
							if (g.goal_name === "" && g.kras.length === 1 && g.kras[0].kra_name === "") return false;
							return true;
						});
						if (!current_data.length) {
							current_data = [{ goal_name: "", kras: [{ kra_name: "", description: "", weight: 0, linked_to_supervisor_kra: "", is_cascaded: 0 }] }];
						}

						sync_goal_kras_to_doc(frm, current_data);
						render_goals_kras_ui(frm);
						bind_bsc_events(frm);
						d.hide();
						frappe.show_alert({ message: __("KRAs imported from supervisor BSC."), indicator: "green" });
					},
				});

				d.show();

				// Select all toggle
				d.$wrapper.find("#sup-kra-select-all").on("change", function () {
					var checked = $(this).prop("checked");
					d.$wrapper.find(".sup-kra-check").prop("checked", checked);
				});
			},
		});
	}

	// Status badge helper
	function get_status_badge_html(status) {
		var color_map = {
			"Draft": "grey",
			"Pending Supervisor Approval": "blue",
			"Approved": "green",
			"Rejected": "red",
		};
		var color = color_map[status] || "grey";
		return "<span class='indicator-pill " + color + "'><span>" + (status || "") + "</span></span>";
	}

	frappe.ui.form.on("Balance Score Card", {
		refresh: function (frm) {
			render_goals_kras_ui(frm);
			render_kpis_ui(frm);

			// Status badge
			if (frm.doc.status) {
				frm.page.set_indicator(frm.doc.status, ({
					"Draft": "grey",
					"Pending Supervisor Approval": "blue",
					"Approved": "green",
					"Rejected": "red",
				}[frm.doc.status] || "grey"));
			}

			var status = frm.doc.status;
			var docstatus = frm.doc.docstatus;

			// --- "Submit for Approval" button: Draft state, employee's own BSC ---
			if (docstatus === 0 && (status === "Draft" || status === "Rejected")) {
				frm.add_custom_button(__("Submit for Approval"), function () {
					frappe.confirm(
						__("Submit this BSC for supervisor approval?"),
						function () {
							frappe.call({
								method: "performance_management.pm.doctype.balance_score_card.balance_score_card.request_approval",
								args: { name: frm.doc.name },
								callback: function (r) {
									frm.reload_doc();
								},
							});
						}
					);
				}).addClass("btn-primary");
			}

			// --- "Recall for Editing" button: Pending or Rejected, for the employee ---
			if (docstatus === 0 && (status === "Pending Supervisor Approval" || status === "Rejected")) {
				frm.add_custom_button(__("Recall for Editing"), function () {
					frappe.confirm(
						__("Recall this BSC for editing? It will be set back to Draft."),
						function () {
							frappe.db.set_value("Balance Score Card", frm.doc.name, "status", "Draft").then(function () {
								frm.reload_doc();
							});
						}
					);
				}).addClass("btn-warning");
			}

			// --- Supervisor Approve/Reject buttons: Pending Supervisor Approval ---
			if (docstatus === 0 && status === "Pending Supervisor Approval" && frm.doc.supervisor) {
				frappe.db.get_value("Employee", frm.doc.supervisor, "user_id", function (r) {
					if (r && r.user_id && r.user_id === frappe.session.user) {
						frm.add_custom_button(__("Approve BSC"), function () {
							frappe.confirm(
								__("Approve this BSC? This will submit the document and create a draft Appraisal."),
								function () {
									frappe.call({
										method: "performance_management.pm.doctype.balance_score_card.balance_score_card.approve_bsc",
										args: { name: frm.doc.name },
										callback: function (r) {
											frm.reload_doc();
										},
									});
								}
							);
						}).addClass("btn-success");

						frm.add_custom_button(__("Reject BSC"), function () {
							var reject_dialog = new frappe.ui.Dialog({
								title: __("Reject BSC"),
								fields: [
									{
										fieldtype: "Small Text",
										fieldname: "reason",
										label: __("Reason for Rejection (optional)"),
									},
								],
								primary_action_label: __("Reject"),
								primary_action: function (values) {
									frappe.call({
										method: "performance_management.pm.doctype.balance_score_card.balance_score_card.reject_bsc",
										args: { name: frm.doc.name, reason: values.reason || "" },
										callback: function (r) {
											reject_dialog.hide();
											frm.reload_doc();
										},
									});
								},
							});
							reject_dialog.show();
						}).addClass("btn-danger");
					}
				});
			}

			// --- "Load from Supervisor BSC" button: Draft state ---
			if (docstatus === 0 && (status === "Draft" || status === "Rejected") && frm.doc.employee && frm.doc.appraisal_cycle) {
				frm.add_custom_button(__("Load from Supervisor BSC"), function () {
					show_load_supervisor_kras_dialog(frm);
				}).addClass("btn-default");
			}

			// --- "Create Subordinate BSCs" button: approved BSC, re-trigger cascade ---
			if (docstatus === 1 && status === "Approved") {
				frm.add_custom_button(__("Create Subordinate BSCs"), function () {
					frappe.confirm(
						__("Auto-create draft BSCs for all direct reports who don't have one yet for this cycle?"),
						function () {
							frappe.call({
								method: "performance_management.pm.doctype.balance_score_card.balance_score_card.trigger_subordinate_bsc_creation",
								args: { bsc_name: frm.doc.name },
								callback: function () { frm.reload_doc(); },
							});
						}
					);
				}).addClass("btn-secondary");
			}

			// "Sync KRAs to Appraisal" button — available on submitted BSC to re-push KRAs
			// into the linked draft Appraisal (useful if appraisal was created before KRAs were set)
			if (docstatus === 1 && frm.doc.name) {
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
			var is_approved = status === "Approved";
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
			sync_kpi_dom_to_doc(frm);
		},
	});

	// =========================================================================
	// KPI section — renders below the Goals section
	// =========================================================================

	/**
	 * Is the KPI definition editable? True only in Draft/Rejected (docstatus 0).
	 * Actuals (actual, self_actual) are always editable when docstatus == 1.
	 */
	function is_kpi_definition_editable(frm) {
		return frm.doc.docstatus === 0 && ["Draft", "Rejected"].indexOf(frm.doc.status) !== -1;
	}

	/** Group kpi_rows by goal_name → kra_name → [kpis] */
	function get_kpis_grouped(frm) {
		var rows = frm.doc.kpi_rows || [];
		var goals = []; // [{goal_name, kras: [{kra_name, kpis: [...]}]}]
		var goal_map = {};
		rows.forEach(function (r) {
			var g = (r.goal_name || "").trim();
			var k = (r.kra_name || "").trim();
			if (!goal_map[g]) {
				goal_map[g] = {};
				goals.push({ goal_name: g, kras: [] });
			}
			var goal_entry = goals.find(function (x) { return x.goal_name === g; });
			if (!goal_entry._kra_map) goal_entry._kra_map = {};
			if (!goal_entry._kra_map[k]) {
				goal_entry._kra_map[k] = [];
				goal_entry.kras.push({ kra_name: k, kpis: goal_entry._kra_map[k] });
			}
			goal_entry._kra_map[k].push(r);
		});
		return goals;
	}

	function render_kpis_ui(frm) {
		var wrapper = frm.fields_dict.kpis_ui && frm.fields_dict.kpis_ui.$wrapper;
		if (!wrapper) return;

		var def_editable = is_kpi_definition_editable(frm);
		var actuals_editable = frm.doc.docstatus === 1;
		var any_editable = def_editable || actuals_editable;
		var grouped = get_kpis_grouped(frm);

		var html = "<div id='bsc-kpis-root'>";

		if (!grouped.length) {
			if (def_editable) {
				html += "<p class='text-muted small'>No KPIs defined yet. Use <b>+ Add KPI</b> to define measurable indicators for your KRAs.</p>";
			} else {
				html += "<p class='text-muted small'>No KPIs defined for this BSC.</p>";
			}
		}

		grouped.forEach(function (goal, gi) {
			goal.kras.forEach(function (kra, ki) {
				var total_weight = kra.kpis.reduce(function (s, k) { return s + flt(k.weight); }, 0);
				var weight_ok = Math.abs(total_weight - 100) < 0.01;
				var weight_badge = kra.kpis.length
					? ("<span class='badge " + (weight_ok ? "badge-success" : "badge-warning") + " ml-2'>" + total_weight.toFixed(1) + "% / 100%</span>")
					: "";

				html += "<div class='card mb-2 bsc-kpi-block' data-goal='" + escape_html(goal.goal_name) + "' data-kra='" + escape_html(kra.kra_name) + "'>";
				html += "<div class='card-body py-2'>";
				html += "<div class='d-flex justify-content-between align-items-center mb-1'>";
				html += "<strong class='small'>" + escape_html(goal.goal_name ? goal.goal_name + " — " + kra.kra_name : kra.kra_name) + "</strong>";
				html += weight_badge;
				if (def_editable) {
					html += "<button class='btn btn-xs btn-default ml-auto add-kpi-row' data-goal='" + escape_html(goal.goal_name) + "' data-kra='" + escape_html(kra.kra_name) + "'>+ Add KPI</button>";
				}
				html += "</div>";

				if (kra.kpis.length) {
					html += "<table class='table table-sm table-bordered mb-0' style='font-size:12px'><thead><tr>";
					html += "<th>KPI</th><th>Target</th><th>Unit</th><th>Weight%</th>";
					if (actuals_editable || kra.kpis.some(function(k){ return flt(k.actual) > 0; })) {
						html += "<th>Actual (Sup.)</th><th>Actual (Self)</th>";
					}
					html += "<th>Score</th>";
					if (def_editable) html += "<th></th>";
					html += "</tr></thead><tbody>";

					kra.kpis.forEach(function (kpi, pi) {
						var score = flt(kpi.score);
						var score_color = score >= 4 ? "text-success" : score >= 2.5 ? "text-warning" : score > 0 ? "text-danger" : "text-muted";
						html += "<tr data-kpi-name='" + escape_html(kpi.name || "") + "' data-kpi-idx='" + pi + "'>";
						// KPI name
						if (def_editable) {
							html += "<td><input type='text' class='form-control form-control-sm kpi-name-inp' data-goal='" + escape_html(goal.goal_name) + "' data-kra='" + escape_html(kra.kra_name) + "' data-idx='" + pi + "' value='" + escape_html(kpi.kpi_name || "") + "' /></td>";
							html += "<td><input type='number' class='form-control form-control-sm kpi-target-inp' data-goal='" + escape_html(goal.goal_name) + "' data-kra='" + escape_html(kra.kra_name) + "' data-idx='" + pi + "' value='" + flt(kpi.target) + "' min='0' step='any' /></td>";
							html += "<td><input type='text' class='form-control form-control-sm kpi-unit-inp' data-goal='" + escape_html(goal.goal_name) + "' data-kra='" + escape_html(kra.kra_name) + "' data-idx='" + pi + "' value='" + escape_html(kpi.unit || "") + "' /></td>";
							html += "<td><input type='number' class='form-control form-control-sm kpi-weight-inp' data-goal='" + escape_html(goal.goal_name) + "' data-kra='" + escape_html(kra.kra_name) + "' data-idx='" + pi + "' value='" + flt(kpi.weight) + "' min='0' max='100' step='0.01' /></td>";
						} else {
							html += "<td>" + escape_html(kpi.kpi_name || "") + "</td>";
							html += "<td>" + flt(kpi.target) + "</td>";
							html += "<td>" + escape_html(kpi.unit || "") + "</td>";
							html += "<td>" + flt(kpi.weight) + "%</td>";
						}
						// Actuals — editable when submitted
						if (actuals_editable || kra.kpis.some(function(k){ return flt(k.actual) > 0; })) {
							if (actuals_editable) {
								html += "<td><input type='number' class='form-control form-control-sm kpi-actual-inp' data-kpiname='" + escape_html(kpi.name || "") + "' data-goal='" + escape_html(goal.goal_name) + "' data-kra='" + escape_html(kra.kra_name) + "' data-idx='" + pi + "' value='" + flt(kpi.actual) + "' min='0' step='any' /></td>";
								html += "<td><input type='number' class='form-control form-control-sm kpi-self-actual-inp' data-kpiname='" + escape_html(kpi.name || "") + "' data-goal='" + escape_html(goal.goal_name) + "' data-kra='" + escape_html(kra.kra_name) + "' data-idx='" + pi + "' value='" + flt(kpi.self_actual) + "' min='0' step='any' /></td>";
							} else {
								html += "<td>" + (flt(kpi.actual) || "—") + "</td><td>" + (flt(kpi.self_actual) || "—") + "</td>";
							}
						}
						html += "<td class='" + score_color + " font-weight-bold'>" + (score > 0 ? score.toFixed(2) : "—") + "</td>";
						if (def_editable) {
							html += "<td><button class='btn btn-xs btn-danger remove-kpi-row' data-goal='" + escape_html(goal.goal_name) + "' data-kra='" + escape_html(kra.kra_name) + "' data-idx='" + pi + "'>×</button></td>";
						}
						html += "</tr>";
					});
					html += "</tbody></table>";
				}
				html += "</div></div>";
			});
		});

		if (def_editable) {
			// Add KPI button for KRAs defined in goals_kras
			html += "<div class='mt-2' id='bsc-kpi-add-for-kra'>";
			var kra_list = _get_kra_list_from_goals(frm);
			if (kra_list.length) {
				html += "<select class='form-control form-control-sm d-inline-block' style='width:auto' id='kpi-kra-selector'>";
				kra_list.forEach(function (item) {
					html += "<option value='" + escape_html(item.goal + "::" + item.kra) + "'>" + escape_html((item.goal ? item.goal + " — " : "") + item.kra) + "</option>";
				});
				html += "</select> ";
				html += "<button class='btn btn-sm btn-primary ml-2' id='kpi-add-for-selected-kra'>+ Add KPI to selected KRA</button>";
			}
			html += "</div>";
		}

		html += "</div>";
		wrapper.html(html);
		_bind_kpi_events(frm);
	}

	function _get_kra_list_from_goals(frm) {
		var result = [];
		var seen = {};
		(frm.doc.goal_kras || []).forEach(function (r) {
			var key = (r.goal_name || "") + "::" + (r.kra_name || "");
			if (!seen[key] && (r.kra_name || "").trim()) {
				seen[key] = true;
				result.push({ goal: (r.goal_name || "").trim(), kra: (r.kra_name || "").trim() });
			}
		});
		return result;
	}

	function _bind_kpi_events(frm) {
		var root = document.getElementById("bsc-kpis-root");
		if (!root) return;

		// Definition field changes
		root.querySelectorAll(".kpi-name-inp, .kpi-target-inp, .kpi-unit-inp, .kpi-weight-inp").forEach(function (inp) {
			inp.onchange = inp.onblur = function () { sync_kpi_dom_to_doc(frm); };
		});

		// Actual field changes — save immediately via whitelist (submitted doc)
		root.querySelectorAll(".kpi-actual-inp, .kpi-self-actual-inp").forEach(function (inp) {
			inp.onchange = inp.onblur = function () { sync_kpi_dom_to_doc(frm); };
		});

		// Remove KPI row
		root.querySelectorAll(".remove-kpi-row").forEach(function (btn) {
			btn.onclick = function () {
				var goal = btn.getAttribute("data-goal");
				var kra = btn.getAttribute("data-kra");
				var idx = parseInt(btn.getAttribute("data-idx"), 10);
				var rows = frm.doc.kpi_rows || [];
				// Find and remove the matching row
				var count = -1;
				frm.doc.kpi_rows = rows.filter(function (r) {
					if ((r.goal_name || "").trim() === goal && (r.kra_name || "").trim() === kra) {
						count++;
						if (count === idx) return false;
					}
					return true;
				});
				frm.refresh_field("kpi_rows");
				frm.dirty();
				render_kpis_ui(frm);
			};
		});

		// Add KPI to a block (card-level add button)
		root.querySelectorAll(".add-kpi-row").forEach(function (btn) {
			btn.onclick = function () {
				var goal = btn.getAttribute("data-goal");
				var kra = btn.getAttribute("data-kra");
				_add_kpi_row(frm, goal, kra);
			};
		});

		// Add KPI from the global selector
		var addBtn = document.getElementById("kpi-add-for-selected-kra");
		if (addBtn) {
			addBtn.onclick = function () {
				var sel = document.getElementById("kpi-kra-selector");
				if (!sel) return;
				var parts = sel.value.split("::");
				_add_kpi_row(frm, parts[0] || "", parts[1] || "");
			};
		}
	}

	function _add_kpi_row(frm, goal_name, kra_name) {
		frm.add_child("kpi_rows", {
			goal_name: goal_name,
			kra_name: kra_name,
			kpi_name: "",
			target: 0,
			unit: "",
			weight: 0,
			actual: 0,
			self_actual: 0,
			score: 0,
		});
		frm.refresh_field("kpi_rows");
		frm.dirty();
		render_kpis_ui(frm);
	}

	function sync_kpi_dom_to_doc(frm) {
		var root = document.getElementById("bsc-kpis-root");
		if (!root) return;

		var def_editable = is_kpi_definition_editable(frm);
		var actuals_editable = frm.doc.docstatus === 1;

		if (def_editable) {
			// Rebuild kpi_rows from DOM
			var new_rows = [];
			root.querySelectorAll(".bsc-kpi-block").forEach(function (block) {
				var goal = block.getAttribute("data-goal") || "";
				var kra = block.getAttribute("data-kra") || "";
				block.querySelectorAll("tbody tr").forEach(function (tr, idx) {
					var existing_rows = (frm.doc.kpi_rows || []).filter(function (r) {
						return (r.goal_name || "").trim() === goal && (r.kra_name || "").trim() === kra;
					});
					var existing = existing_rows[idx] || {};
					var name_inp = tr.querySelector(".kpi-name-inp");
					var tgt_inp = tr.querySelector(".kpi-target-inp");
					var unit_inp = tr.querySelector(".kpi-unit-inp");
					var wt_inp = tr.querySelector(".kpi-weight-inp");
					var act_inp = tr.querySelector(".kpi-actual-inp");
					var self_inp = tr.querySelector(".kpi-self-actual-inp");
					new_rows.push({
						name: existing.name || null,
						goal_name: goal,
						kra_name: kra,
						kpi_name: name_inp ? name_inp.value.trim() : (existing.kpi_name || ""),
						target: tgt_inp ? flt(tgt_inp.value) : flt(existing.target),
						unit: unit_inp ? unit_inp.value.trim() : (existing.unit || ""),
						weight: wt_inp ? flt(wt_inp.value) : flt(existing.weight),
						actual: act_inp ? flt(act_inp.value) : flt(existing.actual),
						self_actual: self_inp ? flt(self_inp.value) : flt(existing.self_actual),
						score: flt(existing.score),
					});
				});
			});
			frm.doc.kpi_rows = new_rows;
			frm.refresh_field("kpi_rows");
		} else if (actuals_editable) {
			// Only sync actual / self_actual
			root.querySelectorAll(".kpi-actual-inp, .kpi-self-actual-inp").forEach(function (inp) {
				var goal = inp.getAttribute("data-goal") || "";
				var kra = inp.getAttribute("data-kra") || "";
				var idx = parseInt(inp.getAttribute("data-idx"), 10);
				var is_actual = inp.classList.contains("kpi-actual-inp");
				var count = -1;
				(frm.doc.kpi_rows || []).forEach(function (r) {
					if ((r.goal_name || "").trim() === goal && (r.kra_name || "").trim() === kra) {
						count++;
						if (count === idx) {
							if (is_actual) r.actual = flt(inp.value);
							else r.self_actual = flt(inp.value);
						}
					}
				});
			});
			frm.refresh_field("kpi_rows");
		}
		frm.dirty();
	}

})();
