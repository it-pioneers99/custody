frappe.ui.form.on('Purchase Receipt', {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__('Create Custody Receipt'), () => {
				frappe.call({
					method: 'custody.custody.api.custody_receipt.create_custody_receipt_from_pr',
					args: { source_name: frm.doc.name },
					freeze: true,
					callback: (r) => {
						if (r && r.message) {
							frappe.set_route('Form', 'Custody Receipt', r.message);
						}
					}
				});
			}, __('Create'));
		}
	}
}); 