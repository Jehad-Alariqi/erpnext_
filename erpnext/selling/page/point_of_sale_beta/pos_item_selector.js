erpnext.PointOfSale.ItemSelector = class {
    constructor({ frm, wrapper, events, pos_profile }) {
		this.wrapper = wrapper;
		this.events = events;
        this.pos_profile = pos_profile;
        
        this.intialize_component();
    }
    
    intialize_component() {
        this.prepare_dom();
        this.make_search_bar();
        this.load_items_data();
        this.bind_events();
    }

    prepare_dom() {
		this.wrapper.append(
            `<section class="col-span-6 flex shadow rounded items-selector bg-white mx-h-70 h-100">
                <div class="flex flex-col rounded w-full scroll">
                    <div class="filter-section flex p-8 pb-2 bg-white sticky z-100">
                        <div class="search-field flex f-grow-3 mr-8 items-center text-grey"></div>
                        <div class="item-group-field flex f-grow-1 items-center text-grey text-bold"></div>
                    </div>
                    <div class="flex flex-1 flex-col p-8 pt-2">
                        <div class="text-grey mb-6">ALL ITEMS</div>
                        <div class="items-container grid grid-cols-4 gap-8">
                        </div>					
                    </div>
                </div>
            </section>`
        );
        
        this.$component = this.wrapper.find('.items-selector');
    }

    async load_items_data() {
        if (!this.item_group) {
            const res = await frappe.db.get_value("Item Group", {lft: 1, is_group: 1}, "name")
            this.item_group = res.message.name;
        };

        this.get_items({}).then(({message}) => {
            this.render_item_list(message.items);
        });
    }

    get_items({start = 0, page_length = 40, search_value=''}) {
        const price_list = this.events.get_frm().doc?.selling_price_list || 'Standard Selling';
        const { item_group, pos_profile } = this;
        
		return frappe.call({
			method: "erpnext.selling.page.point_of_sale.point_of_sale.get_items",
			freeze: true,
            args: { start, page_length, price_list, item_group, search_value, pos_profile },
        });
	}


	render_item_list(items) {
        this.$items_container = this.$component.find('.items-container');
        this.$items_container.html('');

        items.forEach(item => {
            const item_html = this.get_item_html(item);
            this.$items_container.append(item_html);
        })
    }

    get_item_html(item) {
		return (
            `<div class="item-wrapper rounded shadow pointer no-select" data-item-code="${escape(item.item_code)}">
                <div class="flex items-center justify-center h-32 bg-light-grey text-6xl text-grey-100">${frappe.get_abbr(item.item_name)}</div>
                <div class="flex items-center pr-4 pl-4 h-10 justify-between">
                    <div class="f-shrink-1 text-dark-grey overflow-hidden whitespace-nowrap">${frappe.ellipsis(item.item_name, 18)}</div>
                    <div class="f-shrink-0 text-dark-grey text-bold ml-4">${format_currency(item.price_list_rate, item.currency, 0) || 0}</div>
                </div>
            </div>`
        )
    }

    make_search_bar() {
        const me = this;
		this.search_field = frappe.ui.form.make_control({
			df: {
				label: __('Search'),
				fieldtype: 'Data',
				placeholder: __('Search by item code, serial number, batch no or barcode')
			},
			parent: this.$component.find('.search-field'),
			render_input: true,
        });
		this.item_group_field = frappe.ui.form.make_control({
			df: {
				label: __('Item Group'),
				fieldtype: 'Link',
				options: 'Item Group',
                placeholder: __('Select item group'),
                onchange: function() {
                    me.item_group = this.value;
                    me.filter_items();
                },
                get_query: () => {
                    return {
                        query: 'erpnext.selling.page.point_of_sale.point_of_sale.item_group_query',
                        filters: {
                            pos_profile: this.events.get_frm().doc?.pos_profile
                        }
                    };
                },
			},
            parent: this.$component.find('.item-group-field'),
			render_input: true,
        });
        this.search_field.toggle_label(false);
		this.item_group_field.toggle_label(false);
	}

    bind_events() {
		const me = this;
		this.$component.on('click', '.item-wrapper', function() {
			const $item = $(this);
			const item_code = unescape($item.attr('data-item-code'));
            let batch_no = unescape($item.attr('data-batch-no'));
            batch_no = batch_no === "undefined" ? undefined : batch_no;

            me.events.item_selected({ field: 'qty', value: 1, item: { item_code, batch_no }});
        })

        this.search_field.$input.on('input', (e) => {
			clearTimeout(this.last_search);
			this.last_search = setTimeout(() => {
				const search_term = e.target.value;
				this.filter_items({ search_term });
			}, 300);
		});
    }
    
    filter_items({ search_term='' }={}) {
		if (search_term) {
			search_term = search_term.toLowerCase();

			// memoize
			this.search_index = this.search_index || {};
			if (this.search_index[search_term]) {
				const items = this.search_index[search_term];
				this.items = items;
				this.render_item_list(items);
				return;
            }
		}

		this.get_items({ search_value: search_term })
            .then(({ message }) => {
                const { items, serial_no, batch_no, barcode } = message;
				if (search_term && !barcode) {
					this.search_index[search_term] = items;
				}
				this.items = items;
				this.render_item_list(items);
			});
	}
    
    resize_selector(minimize) {
        minimize ? 
        this.$component.find('.search-field').removeClass('mr-8') : 
        this.$component.find('.search-field').addClass('mr-8');

        minimize ? 
        this.$component.find('.filter-section').addClass('flex-col') : 
        this.$component.find('.filter-section').removeClass('flex-col');

        minimize ?
        this.$component.removeClass('col-span-6').addClass('col-span-2') :
        this.$component.removeClass('col-span-2').addClass('col-span-6')

        minimize ?
        this.$items_container.removeClass('grid-cols-4').addClass('grid-cols-1') :
        this.$items_container.removeClass('grid-cols-1').addClass('grid-cols-4')
    }

    disable_selector() {
        this.$component.addClass('d-none');
    }
}