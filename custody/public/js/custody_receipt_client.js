frappe.ui.form.on('Custody Receipt', {
    refresh(frm) {
        // Add button to create custody receipt from employee
        if (frm.doc.employee) {
            frm.add_custom_button(__('Add Asset Item'), () => {
                add_asset_item(frm);
            }, __('Add'));
        }
    },
    
    employee(frm) {
        // When employee is selected, clear items and allow asset selection
        if (frm.doc.employee) {
            frm.set_value('items', []);
            frm.refresh_field('items');
        }
    }
});

frappe.ui.form.on('Custody Receipt Item', {
    asset(frm, cdt, cdn) {
        // When asset is selected, automatically populate item details
        let row = locals[cdt][cdn];
        if (row.asset) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Asset',
                    name: row.asset
                },
                callback: (r) => {
                    if (r.message) {
                        let asset = r.message;
                        if (asset.item_code) {
                            // Get item details
                            frappe.call({
                                method: 'frappe.client.get',
                                args: {
                                    doctype: 'Item',
                                    name: asset.item_code
                                },
                                callback: (r2) => {
                                    if (r2.message) {
                                        let item = r2.message;
                                        row.item_code = item.item_code;
                                        row.item_name = item.item_name;
                                        row.description = `${item.item_name} (Asset: ${row.asset})`;
                                        row.uom = item.stock_uom;
                                        row.warehouse = asset.warehouse || '';
                                        frm.refresh_field('items');
                                    }
                                }
                            });
                        }
                    }
                }
            });
        }
    }
});

function add_asset_item(frm) {
    // Add a new row for asset selection
    let new_row = frm.add_child('items');
    new_row.qty = 1;
    frm.refresh_field('items');
    
    // Focus on the asset field of the new row
    setTimeout(() => {
        let last_row = frm.doc.items[frm.doc.items.length - 1];
        frm.set_focus('items', last_row.name, 'asset');
    }, 100);
} 