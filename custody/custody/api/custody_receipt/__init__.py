# # apps/custody/custody/api.py

import frappe
from frappe import _
from frappe.utils import get_link_to_form

@frappe.whitelist()
def create_custody_receipt_from_pr(source_name):
    """
    Creates a Custody Receipt from a submitted Purchase Receipt.
    Maps: supplier, supplier_name, posting_date, purchase_receipt link and items with remaining qty.
    Prevents creating Custody Receipt Items beyond remaining quantities.
    """
    pr = frappe.get_doc("Purchase Receipt", source_name)

    cr = frappe.new_doc("Custody Receipt")
    # Header fields (ensure these exist in your Custody Receipt doctype)
    cr.company_name = pr.company
    if hasattr(pr, 'supplier'):
        cr.supplier = pr.supplier
    if hasattr(pr, 'supplier_name'):
        cr.supplier_name = pr.supplier_name
    if hasattr(pr, 'posting_date'):
        cr.purchase_date = pr.posting_date
    cr.purchase_receipt = pr.name
    cr.purchase_receipt_name = pr.name

    # Build map of already receipted qty per PR Item
    existing_rows = frappe.get_all(
        "Custody Receipt Item",
        filters={"purchase_receipt": pr.name,
            "docstatus": 1},
        fields=["purchase_receipt_item", "qty"],
    )
    receipted_by_pr_item = {}
    for r in existing_rows:
        key = r.get("purchase_receipt_item")
        if not key:
            continue
        receipted_by_pr_item[key] = receipted_by_pr_item.get(key, 0) + float(r.get("qty") or 0)

    # Append items with remaining qty only
    total_appended = 0
    for item in pr.items:
        pr_item_name = item.name
        accepted_qty = float(item.get("accepted_qty") or item.get("qty") or 0)
        already = float(receipted_by_pr_item.get(pr_item_name, 0))
        remaining = max(0, accepted_qty - already)
        if remaining <= 0:
            continue

        cr.append("items", {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "description": item.description,
            "qty": remaining,
            "uom": item.uom,
            "warehouse": item.warehouse,
            "purchase_receipt": pr.name,
            "purchase_receipt_item": pr_item_name,
            "rate": float(item.get("rate") or 0),
            "amount": float(item.get("rate") or 0) * remaining,
        })
        total_appended += 1

    if not total_appended:
        frappe.throw(_("No remaining quantities available to create a Custody Receipt."))

    cr.insert(ignore_permissions=True)

    frappe.msgprint(
        _("Successfully created Custody Receipt: {0}").format(
            get_link_to_form("Custody Receipt", cr.name)
        ),
        title=_("Success"),
        indicator="green"
    )

    return cr.name 