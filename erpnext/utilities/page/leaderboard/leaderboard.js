frappe.pages["leaderboard"].on_page_load = function (wrapper) {
	frappe.leaderboard = new frappe.Leaderboard(wrapper);
}

frappe.Leaderboard = Class.extend({

	init: function (parent) {
		frappe.ui.make_app_page({
			parent: parent,
			title: "Leaderboard",
			single_column: false
		});

		this.parent = parent;
		this.page = this.parent.page;
		this.page.sidebar.html(`<ul class="module-sidebar-nav overlay-sidebar nav nav-pills nav-stacked"></ul>`);
		this.$sidebar_list = this.page.sidebar.find('ul');

		// const list of doctypes
		this.doctypes = ["Customer", "Item", "Supplier", "Sales Partner"];
		this.timespans = ["Week", "Month", "Quarter", "Year"];
		this.desc_fields = ["total_amount", "total_request", "annual_billing", "commission_rate"];
		this.filters = {
			"Customer": this.map_array(["total_amount", "total_item_purchased"]),
			"Item": this.map_array(["total_request", "total_purchase", "avg_price"]),
			"Supplier": this.map_array(["annual_billing", "total_unpaid"]),
			"Sales Partner": this.map_array(["commission_rate", "target_qty", "target_amount"]),
		};

		// for saving current selected filters
		// TODO: revert to 0 index for doctype and timespan, and remove preset down
		const _initial_doctype = this.doctypes[1];
		const _initial_timespan = this.timespans[1];
		const _initial_filter = this.filters[_initial_doctype];

		this.options = {
			selected_doctype: _initial_doctype,
			selected_filter: _initial_filter,
			selected_filter_item: _initial_filter[0],
			selected_timespan: _initial_timespan,
		};

		this.message = null;
		this.make();
	},

	make: function () {
		var me = this;

		var $container = $(`<div class="leaderboard page-main-content">
			<div class="leaderboard-graph"></div>
			<div class="leaderboard-list"></div>
		</div>`).appendTo(this.page.main);

		this.$graph_area = $container.find('.leaderboard-graph');

		this.doctypes.map(doctype => {
			this.get_sidebar_item(doctype).appendTo(this.$sidebar_list);
		});

		// this.doctype_select = this.page.add_select(__("Doctype"),
		// 	this.doctypes.map(d => {
		// 		return {"label": __(d), value: d }
		// 	})
		// );

		this.timespan_select = this.page.add_select(__("Timespan"),
			this.timespans.map(d => {
				return {"label": __(d), value: d }
			})
		);

		this.doctype_select.val(this.doctypes[1]);
		this.timespan_select.val(this.timespans[1]);

		this.type_select = this.page.add_select(__("Type"),
			me.options.selected_filter.map(d => d.field).map(d => {
				return {"label": __(frappe.model.unscrub(d)), value: d }
			})
		);

		this.$sidebar_list.on('click', 'li', (e) => {
			let doctype = $(e.target).find('span').html();

			me.options.selected_doctype = doctype;
			me.options.selected_filter = me.filters[doctype];
			me.options.selected_filter_item = me.filters[doctype][1];

			this.$sidebar_list.find('li').removeClass('active');
			$(e.target).addClass('active');

			me.make_request($container);
		});

		this.doctype_select.on("change", function() {
			me.options.selected_doctype = this.value;
			me.options.selected_filter = me.filters[this.value];
			me.options.selected_filter_item = me.filters[this.value][1];

			me.type_select.empty().add_options(
				me.options.selected_filter.map(d => d.field).map(d => {
					return {"label": __(frappe.model.unscrub(d)), value: d }
				})
			);
			me.make_request($container);
		});

		this.timespan_select.on("change", function() {
			me.options.selected_timespan = this.value;
			me.make_request($container);
		});

		this.type_select.on("change", function() {
			me.options.selected_filter_item = {
				field: this.value,
				value: ""
			};
			me.make_request($container);
		});

		// now get leaderboard
		this.$sidebar_list.find('li')[0].trigger('click');
	},

	make_request: function ($container) {
		var me = this;

		frappe.model.with_doctype(me.options.selected_doctype, function () {
			me.get_leaderboard(me.get_leaderboard_data, $container);
		});
	},

	get_leaderboard: function (notify, $container) {
		var me = this;

		frappe.call({
			method: "erpnext.utilities.page.leaderboard.leaderboard.get_leaderboard",
			args: {
				obj: JSON.stringify(me.options)
			},
			callback: function (res) {
				// console.log(res);

				me.$graph_area.empty().removeClass('hidden');
				let args = {
					parent: me.$graph_area,
					y: [
						{
							color: 'light-green',
							values: res.message.map(d=>d.value),
							formatted: res.message.map(d=>d[me.options.selected_filter_item.field])
						}
					],
					x: {
						values: res.message.map(d=>d.title)
					},
					mode: 'bar',
					height: 140
				};
				new frappe.ui.Graph(args);

				notify(me, res, $container);
			}
		});
	},

	get_leaderboard_data: function (me, res, $container) {
		if (res && res.message) {
			me.message = null;
			$container.find(".leaderboard-list").html(me.render_list_view(res.message));
		} else {
			me.message = "No items found.";
			$container.find(".leaderboard-list").html(me.render_list_view());
		}
	},

	render_list_view: function (items = []) {
		var me = this;

		var html =
			`${me.render_message()}
			 <div class="result" style="${me.message ? "display:none;" : ""}">
			 	${me.render_result(items)}
			 </div>`;

		return $(html);
	},

	render_result: function (items) {
		var me = this;

		var html =
			`${me.render_list_header()}
			${me.render_list_result(items)}`;

		return html;
	},

	render_list_header: function () {
		var me = this;
		const _selected_filter = me.options.selected_filter
			.map(i => frappe.model.unscrub(i.field));
		// const fields = [{field:"title", value:""}].concat(me.options.selected_filter);
		const fields = [{field:"title", value:""}, me.options.selected_filter_item];

		const html =
			`<div class="list-headers">
				<div class="list-item list-item--head" data-list-renderer="${"List"}">
					${
					fields.map(filter => {
							const col = frappe.model.unscrub(filter.field);
							return (
								`<div class="leaderboard-item list-item_content ellipsis text-muted list-item__content--flex-2
									header-btn-base
									${(col && _selected_filter.indexOf(col) !== -1) ? "text-right" : ""}">
									<span class="list-col-title ellipsis">
										${col}
									</span>
								</div>`);
						}).join("")
					}
				</div>
			</div>`;
		return html;
	},

	render_list_result: function (items) {
		var me = this;

		let _html = items.map((item, index) => {
			const $value = $(me.get_item_html(item));

			let item_class = "";
			if(index == 0) {
				item_class = "first";
			} else if (index == 1) {
				item_class = "second";
			} else if(index == 2) {
				item_class = "third";
			}
			const $item_container = $(`<div class="list-item-container  ${item_class}">`).append($value);
			return $item_container[0].outerHTML;
		}).join("");

		let html =
			`<div class="result-list">
				<div class="list-items">
					${_html}
				</div>
			</div>`;

		return html;
	},

	render_message: function () {
		var me = this;

		let html =
			`<div class="no-result text-center" style="${me.message ? "" : "display:none;"}">
				<div class="msg-box no-border">
					<p>No Item found</p>
				</div>
			</div>`;

		return html;
	},

	get_item_html: function (item) {
		var me = this;
		const _selected_filter = me.options.selected_filter
			.map(i => frappe.model.unscrub(i.field));
		// const fields = [{field:"title", value:""}].concat(me.options.selected_filter);
		const fields = [{field:"title", value:""}, me.options.selected_filter_item];

		const html =
			`<div class="list-item">
				${
			fields.map(filter => {
					const col = frappe.model.unscrub(filter.field);
					let val = item[filter.field];
					if (col === "Modified") {
						val = comment_when(val);
					}
					return (
						`<div class="list-item_content ellipsis list-item__content--flex-2
							${(col !== "Title" && col !== "Modified") ? "hidden-xs" : ""}
							${(col && _selected_filter.indexOf(col) !== -1) ? "text-right" : ""}">
							${
								col === "Title"
									? `<a class="grey list-id ellipsis" href="${item["href"]}"> ${val} </a>`
									: `<span class="text-muted ellipsis"> ${val}</span>`
							}
						</div>`);
					}).join("")
				}
			</div>`;

		return html;
	},

	map_array: function (_array) {
		var me = this;
		return _array.map((str) => {
			let value = me.desc_fields.indexOf(str) > -1 ? "DESC" : "ASC";
			return {
				field: str,
				// label: ,
				value: value
			};
		});
	},

	get_sidebar_item: function(item) {
		return $(`<li class="strong module-sidebar-item">
			<a class="module-link">
			<span>${ item }</span></a>
		</li>`);
	}
});
