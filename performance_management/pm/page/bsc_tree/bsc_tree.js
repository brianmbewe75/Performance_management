/* eslint-disable */
/* BSC Performance Tree Page */
frappe.pages["bsc-tree"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("BSC Performance Tree"),
		single_column: true,
	});

	// Add appraisal cycle link field in the toolbar
	var cycle_field = page.add_field({
		fieldtype: "Link",
		fieldname: "appraisal_cycle",
		label: __("Appraisal Cycle"),
		options: "Appraisal Cycle",
		change: function () {
			var cycle = cycle_field.get_value();
			if (cycle) {
				load_tree(cycle);
			} else {
				render_empty();
			}
		},
	});

	var $content = $("<div class='bsc-tree-content' style='padding:20px'></div>").appendTo(page.main);

	function render_empty() {
		$content.html(
			"<div class='text-muted text-center' style='margin-top:40px'>" +
			"<i class='fa fa-sitemap fa-3x' style='opacity:0.3'></i>" +
			"<p class='mt-3'>" + __("Select an Appraisal Cycle to view the BSC Performance Tree.") + "</p>" +
			"</div>"
		);
	}

	function render_loading() {
		$content.html(
			"<div class='text-center' style='margin-top:40px'>" +
			"<i class='fa fa-spinner fa-spin fa-2x'></i>" +
			"<p class='mt-2 text-muted'>" + __("Loading...") + "</p>" +
			"</div>"
		);
	}

	function load_tree(cycle) {
		render_loading();
		frappe.call({
			method: "performance_management.pm.page.bsc_tree.bsc_tree.get_bsc_tree_data",
			args: { cycle: cycle },
			callback: function (r) {
				var tree = (r && r.message) ? r.message : [];
				render_tree(tree, cycle);
			},
			error: function () {
				$content.html(
					"<div class='alert alert-danger'>" +
					__("Failed to load BSC tree data.") +
					"</div>"
				);
			},
		});
	}

	function get_status_color(node) {
		if (!node.bsc_name) return "#aaa";
		var status = node.status;
		if (status === "Approved") return "#28a745";
		if (status === "Pending Supervisor Approval") return "#007bff";
		if (status === "Rejected") return "#dc3545";
		return "#6c757d"; // Draft or unknown
	}

	function get_progression_color(pct) {
		if (pct === null || pct === undefined) return "#aaa";
		if (pct >= 75) return "#28a745";
		if (pct >= 50) return "#ffc107";
		return "#dc3545";
	}

	function get_status_badge(node) {
		if (!node.bsc_name) {
			return "<span class='badge' style='background:#aaa;color:#fff'>" + __("No BSC") + "</span>";
		}
		var color_map = {
			"Draft": "#6c757d",
			"Pending Supervisor Approval": "#007bff",
			"Approved": "#28a745",
			"Rejected": "#dc3545",
		};
		var color = color_map[node.status] || "#6c757d";
		return "<span class='badge' style='background:" + color + ";color:#fff'>" + (node.status || __("Draft")) + "</span>";
	}

	function get_progression_badge(node) {
		if (!node.bsc_name || node.goal_progression === null || node.goal_progression === undefined) {
			return "<span class='text-muted small'>" + __("N/A") + "</span>";
		}
		var pct = node.goal_progression;
		var color = get_progression_color(pct);
		return "<span style='color:" + color + ";font-weight:bold'>" + pct.toFixed(1) + "%</span>";
	}

	function render_node(node) {
		var $li = $("<li style='list-style:none;margin-bottom:8px'></li>");
		var has_children = node.children && node.children.length > 0;

		var card_style = "display:inline-block;min-width:220px;border:1px solid #ddd;border-radius:6px;" +
			"padding:10px 14px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,0.06);cursor:" +
			(node.bsc_name ? "pointer" : "default") + ";vertical-align:top;";

		var left_border_color = get_status_color(node);
		card_style += "border-left:4px solid " + left_border_color + ";";

		var bsc_link_html = "";
		if (node.bsc_name) {
			bsc_link_html = "<a href='/app/balance-score-card/" + encodeURIComponent(node.bsc_name) + "' " +
				"onclick='event.stopPropagation()' class='text-muted small'>" +
				node.bsc_name + "</a>";
		} else {
			bsc_link_html = "<span class='text-muted small'>" + __("No BSC") + "</span>";
		}

		var toggle_btn = "";
		if (has_children) {
			toggle_btn = "<button class='btn btn-xs btn-default bsc-tree-toggle' style='margin-right:6px;padding:0 6px;font-size:12px'>&#9660;</button>";
		}

		var $card = $("<div style='" + card_style + "'></div>");
		$card.html(
			"<div style='display:flex;align-items:center;margin-bottom:4px'>" +
			toggle_btn +
			"<strong style='font-size:14px'>" + frappe.utils.escape_html(node.employee_name) + "</strong>" +
			"</div>" +
			"<div style='margin-bottom:4px'>" + bsc_link_html + "</div>" +
			"<div style='display:flex;align-items:center;gap:8px'>" +
			get_status_badge(node) +
			"<span class='text-muted small'>" + __("Progression") + ": " + get_progression_badge(node) + "</span>" +
			"</div>"
		);

		if (node.bsc_name) {
			$card.on("click", function () {
				frappe.set_route("Form", "Balance Score Card", node.bsc_name);
			});
		}

		$li.append($card);

		if (has_children) {
			var $children_ul = $("<ul style='padding-left:40px;margin-top:4px;border-left:2px dashed #ddd;margin-left:20px'></ul>");
			node.children.forEach(function (child) {
				$children_ul.append(render_node(child));
			});
			$li.append($children_ul);

			// Toggle collapse
			$li.find(".bsc-tree-toggle").on("click", function (e) {
				e.stopPropagation();
				var $btn = $(this);
				var $ul = $li.children("ul");
				if ($ul.is(":visible")) {
					$ul.hide();
					$btn.html("&#9654;");
				} else {
					$ul.show();
					$btn.html("&#9660;");
				}
			});
		}

		return $li;
	}

	function render_tree(tree, cycle) {
		if (!tree || !tree.length) {
			$content.html(
				"<div class='text-muted text-center' style='margin-top:40px'>" +
				"<i class='fa fa-info-circle'></i> " +
				__("No employee data found for this appraisal cycle.") +
				"</div>"
			);
			return;
		}

		$content.empty();

		// Legend
		var $legend = $("<div style='margin-bottom:16px;display:flex;gap:16px;flex-wrap:wrap;align-items:center'>" +
			"<strong>" + __("Legend") + ":</strong>" +
			"<span><span style='display:inline-block;width:14px;height:14px;background:#28a745;border-radius:2px;vertical-align:middle'></span> " + __("Approved") + "</span>" +
			"<span><span style='display:inline-block;width:14px;height:14px;background:#007bff;border-radius:2px;vertical-align:middle'></span> " + __("Pending Supervisor Approval") + "</span>" +
			"<span><span style='display:inline-block;width:14px;height:14px;background:#dc3545;border-radius:2px;vertical-align:middle'></span> " + __("Rejected") + "</span>" +
			"<span><span style='display:inline-block;width:14px;height:14px;background:#6c757d;border-radius:2px;vertical-align:middle'></span> " + __("Draft") + "</span>" +
			"<span><span style='display:inline-block;width:14px;height:14px;background:#aaa;border-radius:2px;vertical-align:middle'></span> " + __("No BSC") + "</span>" +
			"</div>" +
			"<div style='margin-bottom:6px;font-size:12px;color:#888'>" +
			__("Progression colours") + ": " +
			"<span style='color:#28a745;font-weight:bold'>" + __("&#8805;75% green") + "</span>, " +
			"<span style='color:#ffc107;font-weight:bold'>" + __("50-74% yellow") + "</span>, " +
			"<span style='color:#dc3545;font-weight:bold'>" + __("&lt;50% red") + "</span>" +
			"</div>");
		$content.append($legend);

		var $root_ul = $("<ul style='padding-left:0;margin:0'></ul>");
		tree.forEach(function (node) {
			$root_ul.append(render_node(node));
		});
		$content.append($root_ul);
	}

	// Initial render
	render_empty();
};
