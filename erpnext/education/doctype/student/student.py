# -*- coding: utf-8 -*-
# Copyright (c) 2015, Frappe Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _
from frappe.desk.form.linked_with import get_linked_doctypes

class Student(Document):
	def validate(self):
		self.title = " ".join(filter(None, [self.first_name, self.middle_name, self.last_name]))

		if self.student_applicant:
			self.check_unique()
			self.update_applicant_status()

		if frappe.get_value("Student", self.name, "title") != self.title:
			self.update_student_name_in_linked_doctype()

	def update_student_name_in_linked_doctype(self):
		linked_doctypes = get_linked_doctypes("Student")
		for d in linked_doctypes:
			meta = frappe.get_meta(d)
			if not meta.issingle:
				if "student_name" in [f.fieldname for f in meta.fields]:
					frappe.db.sql("""UPDATE `tab{0}` set student_name = %s where {1} = %s"""
						.format(d, linked_doctypes[d]["fieldname"]),(self.title, self.name))

				if "child_doctype" in linked_doctypes[d].keys() and "student_name" in \
					[f.fieldname for f in frappe.get_meta(linked_doctypes[d]["child_doctype"]).fields]:
					frappe.db.sql("""UPDATE `tab{0}` set student_name = %s where {1} = %s"""
						.format(linked_doctypes[d]["child_doctype"], linked_doctypes[d]["fieldname"]),(self.title, self.name))

	def check_unique(self):
		"""Validates if the Student Applicant is Unique"""
		student = frappe.db.sql("select name from `tabStudent` where student_applicant=%s and name!=%s", (self.student_applicant, self.name))
		if student:
			frappe.throw(_("Student {0} exist against student applicant {1}").format(student[0][0], self.student_applicant))

	def update_applicant_status(self):
		"""Updates Student Applicant status to Admitted"""
		if self.student_applicant:
			frappe.db.set_value("Student Applicant", self.student_applicant, "application_status", "Admitted")

def get_timeline_data(doctype, name):
	'''returns timeline data based on membership'''
	from six import iteritems
	from frappe.utils import get_timestamp

	out = {}
	
	'''attendance'''
	items = dict(frappe.db.sql('''select unix_timestamp(`date`), count(*)
		from `tabStudent Attendance` where
			student=%s
			and `date` > date_sub(curdate(), interval 1 year)
			and status = 'Present'
			group by date''', name))

	for date, count in items.iteritems():
		timestamp = get_timestamp(date)
		out.update({ timestamp: count })

	'''Program Enrollment'''
	items = dict(frappe.db.sql('''select creation, count(*)
		from `tabProgram Enrollment` where student=%s
			and creation > date_sub(curdate(), interval 1 year)
			group by creation''', name))

	for date, count in iteritems(items):
		timestamp = get_timestamp(date)
		if not timestamp in out:
			out.update({timestamp: count})
		else :
			out.update({timestamp: out[timestamp] + count})

	'''assessment result'''
	items = dict(frappe.db.sql('''select creation, count(*)
		from `tabAssessment Result` where student=%s
			and creation > date_sub(curdate(), interval 1 year)
			group by creation''', name))

	for date, count in iteritems(items):
		timestamp = get_timestamp(date)
		if not timestamp in out:
			out.update({timestamp: count})
		else :
			out.update({timestamp: out[timestamp] + count})

	'''fees'''
	items = dict(frappe.db.sql('''select posting_date, count(*)
		from `tabFees` where student=%s
			and posting_date > date_sub(curdate(), interval 1 year)
			group by posting_date''', name))

	for date, count in iteritems(items):
		timestamp = get_timestamp(date)
		if not timestamp in out:
			out.update({timestamp: count})
		else :
			out.update({timestamp: out[timestamp] + count})

	'''student log'''
	items = dict(frappe.db.sql('''select creation, count(*)
		from `tabStudent Log` where student=%s
			and creation > date_sub(curdate(), interval 1 year)
			group by creation''', name))

	for date, count in iteritems(items):
		timestamp = get_timestamp(date)
		if not timestamp in out:
			out.update({timestamp: count})
		else :
			out.update({timestamp: out[timestamp] + count})

	'''student leave application'''
	items = dict(frappe.db.sql('''select creation, count(*)
		from `tabStudent Leave Application` where student=%s
			and creation > date_sub(curdate(), interval 1 year)
			group by creation''', name))

	for date, count in iteritems(items):
		timestamp = get_timestamp(date)
		if not timestamp in out:
			out.update({timestamp: count})
		else :
			out.update({timestamp: out[timestamp] + count})

	return out
