QUnit.module('hr');

QUnit.test("Test: Leave application [HR]", function (assert) {
	assert.expect(4);
	let done = assert.async();
	let today_date = frappe.datetime.nowdate();

	frappe.run_serially([
		// test creating leave application
		() => frappe.db.get_value('Employee', {'employee_name':'Test Employee 1'}, 'name'),
		(employee) => {
			return frappe.tests.make('Leave Application', [
				{leave_type: "Test Leave type"},
				{from_date: today_date},	// for today
				{to_date: today_date},
				{half_day: 1},
				{employee: employee.message.name},
				{leave_approver: "Administrator"},
				{follow_via_email: 0}
			]);
		},
		() => frappe.timeout(1),
		// check calculated total leave days
		() => assert.equal("0.5", cur_frm.doc.total_leave_days,
			"leave application for half day"),
		() => cur_frm.savesubmit(),
		() => frappe.timeout(1),
		() => frappe.click_button('Yes'),
		() => frappe.timeout(1),
		() => assert.equal("Only Leave Applications with status 'Approved' and 'Rejected' can be submitted", cur_dialog.body.innerText,
			"application not submitted with status as open"),
		() => frappe.click_button('Close'),
		() => frappe.timeout(0.5),
		() => cur_frm.set_value("status", "Approved"),	// approve the application [as administrator]
		() => frappe.timeout(0.5),
		// save form
		() => cur_frm.save(),
		() => frappe.timeout(1),
		() => cur_frm.savesubmit(),
		() => frappe.timeout(1),
		() => frappe.click_button('Yes'),
		() => frappe.timeout(1),
		// check auto filled posting date [today]
		() => assert.equal(today_date, cur_frm.doc.posting_date,
			"posting date correctly set"),
		() => frappe.set_route("List", "Leave Application", "List"),
		() => frappe.timeout(1),
		() => assert.deepEual(["Test Employee 1", "Approved"], [cur_list.data[0].employee_name, cur_list.data[0].status],
			"leave for correct employee is approved"),
		() => done()
	]);
});