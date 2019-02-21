# -*- coding: utf-8 -*-
# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
from __future__ import unicode_literals

import frappe
import unittest
from erpnext.support.doctype.service_level.test_service_level import make_service_level

class TestServiceLevelAgreement(unittest.TestCase):

	def test_service_level_agreement(self):
		test_make_service_level_agreement = make_service_level_agreement()
		test_get_service_level_agreement = get_service_level_agreement()
		self.assertEquals(test_make_service_level_agreement, test_get_service_level_agreement)

def make_service_level_agreement():
	make_service_level()
	customer = frappe.get_doc({
		"doctype": "Customer",
		"customer_name": "_Test Customer",
		"customer_group": "Commercial",
		"customer_type": "Individual",
		"territory": "Rest Of The World"
	})
	if not frappe.db.exists("Customer", "_Test Customer"):
		customer.insert()
	else:
		customer = frappe.get_doc("Customer", "_Test Customer")
	service_level_agreement = frappe.get_doc({
		"doctype": "Service Level Agreement",
		"name": "Test SLA",
		"customer": customer.customer_name,
		"service_level": "_Test Service Level",
		"holiday_list": "_Test Holiday List",
		"priority": "Medium",
		"employee_group": "_Test Employee Group",
		"start_date": frappe.utils.getdate(),
		"end_date": frappe.utils.add_to_date(frappe.utils.getdate(), days=100),
		"response_time": 1,
		"response_time_period": "Day",
		"resolution_time": 1,
		"resolution_time_period": "Day",
	})
	service_level_agreement_exists = frappe.db.exists("Service Level Agreement", "Test SLA")
	if not service_level_agreement_exists:
		service_level_agreement.insert()
		return service_level_agreement.name
	else:
		return service_level_agreement_exists

def get_service_level_agreement():
	service_level_agreement = frappe.db.exists("Service Level Agreement", "Test SLA")
	return service_level_agreement