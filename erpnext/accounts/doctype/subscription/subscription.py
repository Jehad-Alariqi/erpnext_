# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.data import (
	add_days,
	add_to_date,
	cint,
	cstr,
	date_diff,
	flt,
	get_last_day,
	getdate,
	nowdate,
)

import erpnext
from erpnext import get_default_company
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
)
from erpnext.accounts.doctype.subscription_plan.subscription_plan import get_plan_rate
from erpnext.accounts.party import get_party_account_currency


class Subscription(Document):
	def before_insert(self):
		# update start just before the subscription doc is created
		self.update_subscription_period(self.start_date)

	def update_subscription_period(self, date=None, return_date=False):
		"""
		Subscription period is the period to be billed. This method updates the
		beginning of the billing period and end of the billing period.

		The beginning of the billing period is represented in the doctype as
		`current_invoice_start` and the end of the billing period is represented
		as `current_invoice_end`.

		If return_date is True, it wont update the start and end dates.
		This is implemented to get the dates to check if is_current_invoice_generated
		"""
		_current_invoice_start = self.get_current_invoice_start(date)
		_current_invoice_end = self.get_current_invoice_end(_current_invoice_start)

		if return_date:
			return _current_invoice_start, _current_invoice_end

		self.current_invoice_start = _current_invoice_start
		self.current_invoice_end = _current_invoice_end

	def get_current_invoice_start(self, date=None):
		"""
		This returns the date of the beginning of the current billing period.
		If the `date` parameter is not given , it will be automatically set as today's
		date.
		"""
		_current_invoice_start = None

		if (
			self.is_new_subscription()
			and self.trial_period_end
			and getdate(self.trial_period_end) > getdate(self.start_date)
		):
			_current_invoice_start = add_days(self.trial_period_end, 1)
		elif self.trial_period_start and self.is_trialling():
			_current_invoice_start = self.trial_period_start
		elif date:
			_current_invoice_start = date
		else:
			_current_invoice_start = nowdate()

		return _current_invoice_start

	def get_current_invoice_end(self, date=None):
		"""
		This returns the date of the end of the current billing period.

		If the subscription is in trial period, it will be set as the end of the
		trial period.

		If is not in a trial period, it will be `x` days from the beginning of the
		current billing period where `x` is the billing interval from the
		`Subscription Plan` in the `Subscription`.
		"""
		_current_invoice_end = None

		if self.is_trialling() and getdate(date) < getdate(self.trial_period_end):
			_current_invoice_end = self.trial_period_end
		else:
			billing_cycle_info = self.get_billing_cycle_data()
			if billing_cycle_info:
				if self.is_new_subscription() and getdate(self.start_date) < getdate(date):
					_current_invoice_end = add_to_date(self.start_date, **billing_cycle_info)

					# For cases where trial period is for an entire billing interval
					if getdate(self.current_invoice_end) < getdate(date):
						_current_invoice_end = add_to_date(date, **billing_cycle_info)
				else:
					_current_invoice_end = add_to_date(date, **billing_cycle_info)
			else:
				_current_invoice_end = get_last_day(date)

			if self.follow_calendar_months:
				billing_info = self.get_billing_cycle_and_interval()
				billing_interval_count = billing_info[0]["billing_interval_count"]
				calendar_months = get_calendar_months(billing_interval_count)
				calendar_month = 0
				current_invoice_end_month = getdate(_current_invoice_end).month
				current_invoice_end_year = getdate(_current_invoice_end).year

				for month in calendar_months:
					if month <= current_invoice_end_month:
						calendar_month = month

				if cint(calendar_month - billing_interval_count) <= 0 and getdate(date).month != 1:
					calendar_month = 12
					current_invoice_end_year -= 1

				_current_invoice_end = get_last_day(
					cstr(current_invoice_end_year) + "-" + cstr(calendar_month) + "-01"
				)

			if self.end_date and getdate(_current_invoice_end) > getdate(self.end_date):
				_current_invoice_end = self.end_date

		return _current_invoice_end

	@staticmethod
	def validate_plans_billing_cycle(billing_cycle_data):
		"""
		Makes sure that all `Subscription Plan` in the `Subscription` have the
		same billing interval
		"""
		if billing_cycle_data and len(billing_cycle_data) != 1:
			frappe.throw(
				_("You can only have Plans with the same billing cycle in a Subscription")
			)

	def get_billing_cycle_and_interval(self):
		"""
		Returns a dict representing the billing interval and cycle for this `Subscription`.

		You shouldn't need to call this directly. Use `get_billing_cycle` instead.
		"""
		plan_names = [plan.plan for plan in self.plans]

		return frappe.get_all(
			"Subscription Plan",
			filters={"name": ["in", plan_names]},
			fields=["billing_interval", "billing_interval_count"],
			distinct=True,
		)

	def get_billing_cycle_data(self):
		"""
		Returns dict contain the billing cycle data.

		You shouldn't need to call this directly. Use `get_billing_cycle` instead.
		"""
		billing_info = self.get_billing_cycle_and_interval()
		if not billing_info:
			return None

		data = dict()
		interval = billing_info[0]["billing_interval"]
		interval_count = billing_info[0]["billing_interval_count"]

		if interval not in ["Day", "Week"]:
			data["days"] = -1

		if interval == "Day":
			data["days"] = interval_count - 1
		elif interval == "Week":
			data["days"] = interval_count * 7 - 1
		elif interval == "Month":
			data["months"] = interval_count
		elif interval == "Year":
			data["years"] = interval_count

		return data

	def set_status_grace_period(self):
		"""
		Sets the `Subscription` `status` based on the preference set in `Subscription Settings`.

		Used when the `Subscription` needs to decide what to do after the current generated
		invoice is past it's due date and grace period.
		"""
		subscription_settings = frappe.get_single("Subscription Settings")
		if self.status == "Past Due Date" and self.is_past_grace_period():
			self.status = (
				"Cancelled" if subscription_settings.cancel_after_grace else "Unpaid"
			)

	def set_subscription_status(self):
		"""
		Sets the status of the `Subscription`
		"""
		if self.is_trialling():
			self.status = "Trialling"
		elif self.status == "Active" and self.end_date and getdate() > getdate(self.end_date):
			self.status = "Completed"
		elif self.is_past_grace_period():
			subscription_settings = frappe.get_single("Subscription Settings")
			self.status = (
				"Cancelled" if subscription_settings.cancel_after_grace else "Unpaid"
			)
		elif self.current_invoice_is_past_due() and not self.is_past_grace_period():
			self.status = "Past Due Date"
		elif not self.has_outstanding_invoice():
			self.status = "Active"
		elif self.is_new_subscription():
			self.status = "Active"

		self.save()

	def is_trialling(self):
		"""
		Returns `True` if the `Subscription` is in trial period.
		"""
		return not self.period_has_passed(self.trial_period_end) and self.is_new_subscription()

	@staticmethod
	def period_has_passed(end_date):
		"""
		Returns true if the given `end_date` has passed
		"""
		# todo: test for illegal time
		if not end_date:
			return True

		return getdate() > getdate(end_date)

	def is_past_grace_period(self):
		"""
		Returns `True` if the grace period for the `Subscription` has passed
		"""
		if not self.current_invoice_is_past_due():
			return

		subscription_settings = frappe.get_single("Subscription Settings")
		grace_period = cint(subscription_settings.grace_period)

		return getdate() > add_days(self.current_invoice.due_date, grace_period)

	def current_invoice_is_past_due(self):
		"""
		Returns `True` if the current generated invoice is overdue
		"""
		if not self.current_invoice or self.is_paid(self.current_invoice):
			return False

		return getdate() > getdate(self.current_invoice.due_date)

	@property
	def invoice_document_type(self):
		return "Sales Invoice" if self.party_type == "Customer" else "Purchase Invoice"

	def get_current_invoice(self):
		"""
		Returns the most recent generated invoice.
		"""
		invoice = frappe.get_all(
			self.invoice_document_type,
			{
				"subscription": self.name,
			},
			limit=1,
			order_by="to_date desc",
			pluck="name",
		)

		if invoice:
			return frappe.get_doc(self.invoice_document_type, invoice[0])

	def is_new_subscription(self):
		"""
		Returns `True` if `Subscription` has never generated an invoice
		"""
		return not frappe.db.exists(
			{"doctype": self.invoice_document_type, "subscription": self.name}
		)

	def validate(self):
		self.validate_trial_period()
		self.validate_plans_billing_cycle(self.get_billing_cycle_and_interval())
		self.validate_end_date()
		self.validate_to_follow_calendar_months()
		self.cost_center = erpnext.get_default_cost_center(self.get("company"))

	def validate_trial_period(self):
		"""
		Runs sanity checks on trial period dates for the `Subscription`
		"""
		if self.trial_period_start and self.trial_period_end:
			if getdate(self.trial_period_end) < getdate(self.trial_period_start):
				frappe.throw(_("Trial Period End Date Cannot be before Trial Period Start Date"))

		if self.trial_period_start and not self.trial_period_end:
			frappe.throw(_("Both Trial Period Start Date and Trial Period End Date must be set"))

		if self.trial_period_start and getdate(self.trial_period_start) > getdate(self.start_date):
			frappe.throw(_("Trial Period Start date cannot be after Subscription Start Date"))

	def validate_end_date(self):
		billing_cycle_info = self.get_billing_cycle_data()
		end_date = add_to_date(self.start_date, **billing_cycle_info)

		if self.end_date and getdate(self.end_date) <= getdate(end_date):
			frappe.throw(
				_("Subscription End Date must be after {0} as per the subscription plan").format(
					end_date
				)
			)

	def validate_to_follow_calendar_months(self):
		if self.follow_calendar_months:
			billing_info = self.get_billing_cycle_and_interval()

			if not self.end_date:
				frappe.throw(_("Subscription End Date is mandatory to follow calendar months"))

			if billing_info[0]["billing_interval"] != "Month":
				frappe.throw(
					_(
						"Billing Interval in Subscription Plan must be Month to follow calendar months"
					)
				)

	def after_insert(self):
		# todo: deal with users who collect prepayments. Maybe a new Subscription Invoice doctype?
		self.set_subscription_status()

	def generate_invoice(self, from_date=None, to_date=None):
		"""
		Creates a `Invoice` for the `Subscription`, updates `self.invoices` and
		saves the `Subscription`.

		Backwards compatibility
		"""
		return self.create_invoice(from_date=from_date, to_date=to_date)

	def create_invoice(self, from_date=None, to_date=None):
		"""
		Creates a `Invoice`, submits it and returns it
		"""
		# For backward compatibility
		# Earlier subscription didn't had any company field
		company = self.get("company") or get_default_company()
		if not company:
			frappe.throw(
				_(
					"Company is mandatory was generating invoice. Please set default company in Global Defaults"
				)
			)

		invoice = frappe.new_doc(self.invoice_document_type)
		invoice.company = company
		invoice.set_posting_time = 1
		invoice.posting_date = (
			self.current_invoice_start
			if self.generate_invoice_at_period_start
			else self.current_invoice_end
		)

		invoice.cost_center = self.cost_center

		if self.invoice_document_type == "Sales Invoice":
			invoice.customer = self.party
		else:
			invoice.supplier = self.party
			if frappe.db.get_value("Supplier", self.party, "tax_withholding_category"):
				invoice.apply_tds = 1

		# Add party currency to invoice
		invoice.currency = get_party_account_currency(self.party_type, self.party, self.company)

		# Add dimensions in invoice for subscription:
		accounting_dimensions = get_accounting_dimensions()

		for dimension in accounting_dimensions:
			if self.get(dimension):
				invoice.update({dimension: self.get(dimension)})

		# Subscription is better suited for service items. I won't update `update_stock`
		# for that reason
		items_list = self.get_items_from_plans(self.plans, is_prorate())
		for item in items_list:
			item["cost_center"] = self.cost_center
			invoice.append("items", item)

		# Taxes
		tax_template = ""

		if self.invoice_document_type == "Sales Invoice" and self.sales_tax_template:
			tax_template = self.sales_tax_template
		if self.invoice_document_type == "Purchase Invoice" and self.purchase_tax_template:
			tax_template = self.purchase_tax_template

		if tax_template:
			invoice.taxes_and_charges = tax_template
			invoice.set_taxes()

		# Due date
		if self.days_until_due:
			invoice.append(
				"payment_schedule",
				{
					"due_date": add_days(invoice.posting_date, cint(self.days_until_due)),
					"invoice_portion": 100,
				},
			)

		# Discounts
		if self.is_trialling():
			invoice.additional_discount_percentage = 100
		else:
			if self.additional_discount_percentage:
				invoice.additional_discount_percentage = self.additional_discount_percentage

			if self.additional_discount_amount:
				invoice.discount_amount = self.additional_discount_amount

			if self.additional_discount_percentage or self.additional_discount_amount:
				discount_on = self.apply_additional_discount
				invoice.apply_discount_on = discount_on if discount_on else "Grand Total"

		# Subscription period
		invoice.subscription = self.name
		invoice.from_date = from_date or self.current_invoice_start
		invoice.to_date = to_date or self.current_invoice_end

		invoice.flags.ignore_mandatory = True

		invoice.set_missing_values()
		invoice.save()

		if self.submit_invoice:
			invoice.submit()

		return invoice

	def get_items_from_plans(self, plans, prorate=None):
		"""
		Returns the `Item`s linked to `Subscription Plan`
		"""
		if prorate is None:
			prorate = False

		if prorate:
			prorate_factor = get_prorata_factor(
				self.current_invoice_end,
				self.current_invoice_start,
				self.generate_invoice_at_period_start,
			)

		items = []
		party = self.party
		for plan in plans:
			plan_doc = frappe.get_doc("Subscription Plan", plan.plan)

			item_code = plan_doc.item

			if self.party == "Customer":
				deferred_field = "enable_deferred_revenue"
			else:
				deferred_field = "enable_deferred_expense"

			deferred = frappe.db.get_value("Item", item_code, deferred_field)

			if not prorate:
				item = {
					"item_code": item_code,
					"qty": plan.qty,
					"rate": get_plan_rate(
						plan.plan,
						plan.qty,
						party,
						self.current_invoice_start,
						self.current_invoice_end,
					),
					"cost_center": plan_doc.cost_center,
				}
			else:
				item = {
					"item_code": item_code,
					"qty": plan.qty,
					"rate": get_plan_rate(
						plan.plan,
						plan.qty,
						party,
						self.current_invoice_start,
						self.current_invoice_end,
						prorate_factor,
					),
					"cost_center": plan_doc.cost_center,
				}

			if deferred:
				item.update(
					{
						deferred_field: deferred,
						"service_start_date": self.current_invoice_start,
						"service_end_date": self.current_invoice_end,
					}
				)

			accounting_dimensions = get_accounting_dimensions()

			for dimension in accounting_dimensions:
				if plan_doc.get(dimension):
					item.update({dimension: plan_doc.get(dimension)})

			items.append(item)

		return items

	def process(self):
		"""
		To be called by task periodically. It checks the subscription and takes appropriate action
		as need be. It calls either of these methods depending the `Subscription` status:
		1. `process_for_active`
		2. `process_for_past_due`
		"""
		# self.validate_existing_invoices()

		# if self.status == 'Active':
		#	self.process_for_active()
		# elif self.status in ['Past Due Date', 'Unpaid']:
		#	self.process_for_past_due_date()

		if (
			not self.is_current_invoice_generated(
				self.current_invoice_start, self.current_invoice_end
			)
			and self.can_generate_new_invoice()
		):
			self.generate_invoice()
			self.update_subscription_period(add_days(self.current_invoice_end, 1))

		if (
			self.cancel_at_period_end
			and getdate() > getdate(self.current_invoice_end)
			and getdate() > getdate(self.end_date)
		):
			self.cancel_subscription_at_period_end()

		self.set_subscription_status()

		self.save()

	def can_generate_new_invoice(self):
		if self.cancelation_date:
			return False
		elif self.generate_invoice_at_period_start and (
			getdate(frappe.flags.current_date) == getdate(self.current_invoice_start)
			or self.is_new_subscription()
		):
			return True
		elif getdate(frappe.flags.current_date) == getdate(self.current_invoice_end):
			if self.has_outstanding_invoice() and not self.generate_new_invoices_past_due_date:
				return False

			return True

	def is_current_invoice_generated(self, _current_start_date=None, _current_end_date=None):
		if not (_current_start_date and _current_end_date):
			_current_start_date, _current_end_date = self.update_subscription_period(
				date=add_days(self.current_invoice_end, 1), return_date=True
			)

		if self.current_invoice and getdate(_current_start_date) <= getdate(self.current_invoice.posting_date) <= getdate(
			_current_end_date
		):
			return True

		return False

	@property
	def current_invoice(self):
		return self.get_current_invoice()

	# def process_for_active(self):
	#	"""
	#	Called by `process` if the status of the `Subscription` is 'Active'.

	#	The possible outcomes of this method are:
	#	1. Generate a new invoice
	#	2. Change the `Subscription` status to 'Past Due Date'
	#	3. Change the `Subscription` status to 'Cancelled'
	#	"""

	#	if (
	#		not self.is_current_invoice_generated(
	#			self.current_invoice_start, self.current_invoice_end
	#		)
	#		and self.can_generate_new_invoice_for_active_subscription()
	#	):
	#		self.generate_invoice()
	#		self.update_subscription_period(add_days(self.current_invoice_end, 1))

	#	if (
	#		self.cancel_at_period_end
	#		and getdate() > getdate(self.current_invoice_end)
	#		and getdate() > getdate(self.end_date)
	#	):
	#		self.cancel_subscription_at_period_end()

	def cancel_subscription_at_period_end(self):
		"""
		Called when `Subscription.cancel_at_period_end` is truthy
		"""
		self.status = "Cancelled"
		self.cancelation_date = nowdate()

	# def can_generate_new_invoice_for_active_subscription(self):
	#	if self.generate_invoice_at_period_start and getdate() >= getdate(self.current_invoice_start):
	#		return True
	#	elif self.is_new_subscription() and getdate() >= getdate(self.current_invoice_start):
	#		return True
	#	else:
	#		return getdate() >= getdate(self.current_invoice_start)

	# def process_for_past_due_date(self):
	#	"""
	#	Called by `process` if the status of the `Subscription` is 'Past Due Date'.

	#	The possible outcomes of this method are:
	#	1. Change the `Subscription` status to 'Active'
	#	2. Change the `Subscription` status to 'Cancelled'
	#	3. Change the `Subscription` status to 'Unpaid'
	#	"""
	#	if not self.has_outstanding_invoice():
	#		self.status = "Active"
	#	else:
	#		self.set_status_grace_period()

	#	# Generate invoices periodically even if current invoice are unpaid
	#	if (
	#		not self.is_current_invoice_generated(
	#			self.current_invoice_start, self.current_invoice_end
	#		)
	#		and self.can_generate_new_invoice_for_past_due_date_subscription()
	#	):
	#		self.generate_invoice()
	#		self.update_subscription_period(add_days(self.current_invoice_end, 1))

	@property
	def invoices(self):
		return frappe.get_all(self.invoice_document_type, filters={"subscription": self.name})

	# def can_generate_new_invoice_for_past_due_date_subscription(self):
	#	if self.generate_new_invoices_past_due_date and getdate() >= getdate(self.current_invoice_start):
	#		return True
	#	elif self.is_new_subscription() and getdate() >= getdate(self.current_invoice_start):
	#		return True
	#	else:
	#		return getdate() >= getdate(self.current_invoice_start)

	@staticmethod
	def is_paid(invoice):
		"""
		Return `True` if the given invoice is paid
		"""
		return invoice.status == "Paid"

	def has_outstanding_invoice(self):
		"""
		Returns `True` if the most recent invoice for the `Subscription` is not paid
		"""
		return frappe.db.exists(
			{
				"doctype": self.invoice_document_type,
				"subscription": self.name,
				"status": ["!=", "Paid"],
			}
		)

	def cancel_subscription(self):
		"""
		This sets the subscription as cancelled. It will stop invoices from being generated
		but it will not affect already created invoices.
		"""
		if self.status == "Cancelled":
			return

		to_generate_invoice = (
			True
			if self.status == "Active" and not self.generate_invoice_at_period_start
			else False
		)
		self.status = "Cancelled"
		self.cancelation_date = nowdate()

		if to_generate_invoice:
			self.generate_invoice(self.current_invoice_start, self.cancelation_date)

		self.save()

	def restart_subscription(self):
		"""
		This sets the subscription as active. The subscription will be made to be like a new
		subscription and the `Subscription` will lose all the history of generated invoices
		it has.
		"""
		if not self.status == "Cancelled":
			frappe.throw(_("You cannot restart a Subscription that is not cancelled."))

		self.status = "Active"
		self.db_set("start_date", nowdate())
		self.update_subscription_period(frappe.flags.current_date or nowdate())
		self.save()

	def validate_existing_invoices(self):
		_current_start_date = self.get_current_invoice_start(self.start_date)
		_current_end_date = self.get_current_invoice_end(_current_start_date)

		while not (
			getdate(_current_start_date) == getdate(self.current_invoice_start)
			and getdate(_current_end_date) == getdate(self.current_invoice_end)
		):
			if not frappe.db.exists(
				{
					"doctype": self.invoice_document_type,
					"from_date": _current_start_date,
					"to_date": _current_end_date,
				}
			):
				self.generate_invoice(_current_start_date, _current_end_date)

			_current_start_date, _current_end_date = self.update_subscription_period(
				date=add_days(_current_end_date, 1), return_date=True
			)


def get_calendar_months(billing_interval):
	calendar_months = []
	start = 0
	while start < 12:
		start += billing_interval
		calendar_months.append(start)

	return calendar_months


def is_prorate():
	return frappe.db.get_single_value("Subscription Settings", "prorate")


def get_prorata_factor(period_end, period_start, is_prepaid):
	if is_prepaid:
		prorate_factor = 1
	else:
		diff = flt(date_diff(nowdate(), period_start) + 1)
		plan_days = flt(date_diff(period_end, period_start) + 1)
		prorate_factor = diff / plan_days

	return prorate_factor


def process_all():
	"""
	Task to updates the status of all `Subscription` apart from those that are cancelled
	"""
	for subscription in frappe.get_all(
		"Subscription", {"status": ("!=", "Cancelled")}, pluck="name"
	):
		try:
			subscription = frappe.get_doc("Subscription", subscription)
			subscription.process()
			frappe.db.commit()
		except Exception:
			frappe.log_error(frappe.get_traceback())


@frappe.whitelist()
def cancel_subscription(name):
	"""
	Cancels a `Subscription`. This will stop the `Subscription` from further invoicing the
	`Subscriber` but all already outstanding invoices will not be affected.
	"""
	subscription = frappe.get_doc("Subscription", name)
	subscription.cancel_subscription()


@frappe.whitelist()
def restart_subscription(name):
	"""
	Restarts a cancelled `Subscription`. The `Subscription` will 'forget' the history of
	all invoices it has generated
	"""
	subscription = frappe.get_doc("Subscription", name)
	subscription.restart_subscription()


@frappe.whitelist()
def get_subscription_updates(name):
	"""
	Use this to get the latest state of the given `Subscription`
	"""
	subscription = frappe.get_doc("Subscription", name)
	subscription.process()
