frappe.ui.form.on('Asset', {
    refresh(frm) {
        // Add button to create custody receipt from this asset
        frm.add_custom_button(__('Create Custody Receipt'), () => {
            frappe.call({
                method: 'custody.custody.api.custody_receipt.create_custody_receipt_from_asset',
                args: { asset_name: frm.doc.name },
                freeze: true,
                callback: (r) => {
                    if (r && r.message) {
                        frappe.set_route('Form', 'Custody Receipt', r.message);
                    }
                }
            });
        }, __('Create'));
    }
}); 