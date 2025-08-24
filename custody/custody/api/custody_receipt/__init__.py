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
    For fixed assets, automatically links the asset ID.
    Uses naming series for purchase_receipt field in items.
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
    cr.purchase_receipt = pr.name  # Keep as actual PR name for proper linking
    cr.purchase_receipt_name = pr.name  # Keep as actual PR name for proper linking

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

    # Group items by item_code to handle asset ranges
    items_by_code = {}
    for item in pr.items:
        pr_item_name = item.name
        accepted_qty = float(item.get("accepted_qty") or item.get("qty") or 0)
        already = float(receipted_by_pr_item.get(pr_item_name, 0))
        remaining = max(0, accepted_qty - already)
        if remaining <= 0:
            continue
            
        item_code = item.item_code
        if item_code not in items_by_code:
            items_by_code[item_code] = []
        
        # Get asset number directly from purchase receipt item for fixed assets
        asset = None
        try:
            # First check if the PR item has an asset field populated
            if item.get('asset'):
                asset = item.asset
                frappe.logger().info(f"Asset found in PR item: {asset} for PR: {pr.name}, PR Item: {pr_item_name}")
            else:
                # Check if item is a fixed asset
                item_doc = frappe.get_doc("Item", item.item_code)
                
                if item_doc.is_fixed_asset:
                    frappe.logger().info(f"Item {item.item_code} is a fixed asset, searching for linked asset...")
                    
                    # Debug: Check what assets exist for this PR
                    all_assets = frappe.get_all("Asset",
                        filters={"purchase_receipt": pr.name},
                        fields=["name", "purchase_receipt_item", "item_code", "docstatus"]
                    )
                    frappe.logger().info(f"All assets for PR {pr.name}: {all_assets}")
                    
                    # Try to find asset by purchase receipt item (most specific)
                    asset_list = frappe.get_all("Asset",
                        filters={
                            "purchase_receipt": pr.name,
                            "purchase_receipt_item": pr_item_name
                        },
                        fields=["name"],
                        limit=1
                    )
                    
                    if asset_list:
                        asset = asset_list[0].name
                        frappe.logger().info(f"Asset found by PR item search: {asset} for PR: {pr.name}, PR Item: {pr_item_name}")
                    else:
                        frappe.logger().info(f"No asset found by PR item search for PR: {pr.name}, PR Item: {pr_item_name}")
                        
                        # Fallback: try to find asset by purchase receipt only
                        asset_list = frappe.get_all("Asset",
                            filters={
                                "purchase_receipt": pr.name,
                                "item_code": item.item_code
                            },
                            fields=["name"],
                            limit=1
                        )
                        
                        if asset_list:
                            asset = asset_list[0].name
                            frappe.logger().info(f"Asset found by PR search: {asset} for PR: {pr.name}, Item: {item.item_code}")
                        else:
                            frappe.logger().info(f"No asset found by PR search for PR: {pr.name}, Item: {item.item_code}")
                            
                            # Additional fallback: try to find asset by item code and company
                            asset_list = frappe.get_all("Asset",
                                filters={
                                    "item_code": item.item_code,
                                    "company": pr.company
                                },
                                fields=["name"],
                                limit=1
                            )
                            
                            if asset_list:
                                asset = asset_list[0].name
                                frappe.logger().info(f"Asset found by item code search: {asset} for Item: {item.item_code}")
                            else:
                                frappe.logger().warning(f"No asset found for fixed asset item: {item.item_code} in PR: {pr.name}")
                                # For fixed assets without found asset, create a warning but continue
                                frappe.msgprint(
                                    _("Warning: Fixed asset item {0} has no linked asset found. Asset field will be empty.").format(item.item_code),
                                    title=_("Asset Not Found"),
                                    indicator="orange"
                                )
                else:
                    frappe.logger().info(f"Item {item.item_code} is not a fixed asset, asset field will remain empty")
                            
        except Exception as e:
            frappe.logger().error(f"Error getting asset for item {item.item_code}: {str(e)}")
            frappe.msgprint(
                _("Error processing asset for item {0}: {1}").format(item.item_code, str(e)),
                title=_("Asset Processing Error"),
                indicator="red"
            )
            asset = None

        # Debug: Log what asset value we're setting
        frappe.logger().info(f"Setting asset field for item {item.item_code}: {asset}")
        
        # Store item info for grouping
        items_by_code[item_code].append({
            "pr_item_name": pr_item_name,
            "item_name": item.item_name,
            "description": item.description,
            "qty": remaining,
            "uom": item.uom,
            "warehouse": item.warehouse,
            "asset": asset,
            "rate": float(item.get("rate") or 0),
            "amount": float(item.get("rate") or 0) * remaining,
        })

    # Now create custody receipt items with distributed assets - split assets across rows
    total_appended = 0
    
    for item_code, items_list in items_by_code.items():
        if not items_list:
            continue
            
        # Sort items by asset name for consistent ordering
        items_list.sort(key=lambda x: x.get('asset', '') or '')
        
        # Create individual custody receipt items with distributed assets
        for item_info in items_list:
            qty = item_info['qty']
            
            # Find all assets linked to this purchase receipt item
            linked_assets = []
            
            # First check if there are assets directly linked to this purchase receipt item
            assets = frappe.get_all("Asset",
                filters={
                    "purchase_receipt": pr.name,
                    "purchase_receipt_item": item_info['pr_item_name']
                },
                fields=["name"],
                order_by="name"  # Order assets by name for sequential distribution
            )
            
            if assets:
                linked_assets = [asset.name for asset in assets]
                frappe.logger().info(f"Found {len(linked_assets)} assets for PR item {item_info['pr_item_name']}: {linked_assets}")
            else:
                # Fallback: check if asset is directly in the item
                if item_info.get('asset'):
                    linked_assets.append(item_info['asset'])
                    frappe.logger().info(f"Using direct asset from item: {item_info['asset']}")
                else:
                    frappe.logger().info(f"No assets found for PR item {item_info['pr_item_name']}")
            
            # Create rows with sequential asset distribution
            frappe.logger().info(f"Creating {int(qty)} rows for item {item_code}, with {len(linked_assets)} assets available")
            
            for i in range(int(qty)):
                base_description = item_info['description'] or item_info['item_name']
                
                # Assign asset if available for this row
                asset = None
                if i < len(linked_assets):
                    asset = linked_assets[i]
                    asset_description = f"{base_description} (Asset: {asset})"
                    frappe.logger().info(f"Row {i+1}: Assigning asset {asset}")
                else:
                    asset_description = base_description
                    frappe.logger().info(f"Row {i+1}: No asset available (asset index {i} >= {len(linked_assets)})")
                
                cr.append("items", {
                    "item_code": item_code,
                    "item_name": item_info['item_name'],
                    "description": asset_description,
                    "qty": 1,  # Each row has quantity 1
                    "uom": item_info['uom'],
                    "warehouse": item_info['warehouse'],
                    "purchase_receipt": pr.name,
                    "purchase_receipt_item": item_info['pr_item_name'],
                    "asset": asset,  # Asset assigned sequentially
                    "rate": item_info['rate'],
                    "amount": item_info['rate'],
                })
                total_appended += 1

    if not total_appended:
        frappe.throw(_("No remaining quantities available to create a Custody Receipt."))

    cr.insert(ignore_permissions=True)

    # Debug: Log the final custody receipt items to verify asset field
    frappe.logger().info(f"Custody Receipt created: {cr.name}")
    for idx, item in enumerate(cr.items):
        frappe.logger().info(f"Item {idx+1}: {item.item_code}, Asset: {item.asset}")

    frappe.msgprint(
        _("Successfully created Custody Receipt: {0}").format(
            get_link_to_form("Custody Receipt", cr.name)
        ),
        title=_("Success"),
        indicator="green"
    )

    return cr.name


@frappe.whitelist()
def create_custody_receipt_from_employee(employee_name, assets=None):
    """
    Creates a Custody Receipt from an Employee with selected assets.
    The custody receipt will have the employee and selected assets with automatic item population.
    """
    try:
        # Get the employee details
        employee = frappe.get_doc("Employee", employee_name)
        
        if not employee:
            frappe.throw(_("Employee {0} not found").format(employee_name))
        
        # Create new custody receipt
        cr = frappe.new_doc("Custody Receipt")
        
        # Set basic fields
        cr.employee = employee_name
        cr.employee_name = employee.employee_name
        cr.company_name = employee.company
        cr.posting_date = frappe.utils.today()
        
        # If assets are provided, add them
        if assets:
            assets_list = assets if isinstance(assets, list) else [assets]
            
            for asset_name in assets_list:
                # Get asset details
                asset = frappe.get_doc("Asset", asset_name)
                if asset and asset.item_code:
                    # Get item details
                    item = frappe.get_doc("Item", asset.item_code)
                    if item:
                        cr.append("items", {
                            "item_code": asset.item_code,
                            "item_name": item.item_name,
                            "description": f"{item.item_name} (Asset: {asset_name})",
                            "qty": 1,
                            "uom": item.stock_uom,
                            "warehouse": asset.warehouse if hasattr(asset, 'warehouse') else None,
                            "asset": asset_name,
                            "rate": 0,
                            "amount": 0,
                        })
        
        # Insert the custody receipt
        cr.insert(ignore_permissions=True)
        
        frappe.msgprint(
            _("Successfully created Custody Receipt: {0} for Employee: {1}").format(
                get_link_to_form("Custody Receipt", cr.name),
                get_link_to_form("Employee", employee_name)
            ),
            title=_("Success"),
            indicator="green"
        )
        
        return cr.name
        
    except Exception as e:
        frappe.logger().error(f"Error creating custody receipt from employee {employee_name}: {str(e)}")
        frappe.throw(_("Error creating custody receipt from employee: {0}").format(str(e)))


@frappe.whitelist()
def get_assets_for_employee(employee_name):
    """
    Gets available assets for an employee to select from.
    """
    try:
        # Get assets that are not currently in custody
        assets = frappe.get_all("Asset",
            filters={
                "docstatus": 1,  # Submitted assets
                "asset_status": "In Use"  # Available assets
            },
            fields=["name", "asset_name", "item_code", "item_name", "warehouse"],
            order_by="name"
        )
        
        return assets
        
    except Exception as e:
        frappe.logger().error(f"Error getting assets for employee {employee_name}: {str(e)}")
        frappe.throw(_("Error getting assets for employee: {0}").format(str(e)))


@frappe.whitelist()
def create_custody_receipt_from_asset(asset_name):
    """
    Creates a Custody Receipt from an Asset.
    The custody receipt will have the asset serial and item code equal to the item code linked with this asset.
    """
    try:
        # Get the asset details
        asset = frappe.get_doc("Asset", asset_name)
        
        if not asset:
            frappe.throw(_("Asset {0} not found").format(asset_name))
        
        # Get the item linked to this asset
        item_code = asset.item_code
        if not item_code:
            frappe.throw(_("Asset {0} has no linked item code").format(asset_name))
        
        # Get item details
        item = frappe.get_doc("Item", item_code)
        if not item:
            frappe.throw(_("Item {0} not found").format(item_code))
        
        # Create new custody receipt
        cr = frappe.new_doc("Custody Receipt")
        
        # Set basic fields
        cr.company_name = asset.company
        cr.posting_date = frappe.utils.today()
        
        # Add the asset as a single item
        cr.append("items", {
            "item_code": item_code,
            "item_name": item.item_name,
            "description": f"{item.item_name} (Asset: {asset_name})",
            "qty": 1,
            "uom": item.stock_uom,
            "warehouse": asset.warehouse if hasattr(asset, 'warehouse') else None,
            "asset": asset_name,  # Link to the specific asset
            "rate": 0,  # Set rate as needed
            "amount": 0,  # Set amount as needed
        })
        
        # Insert the custody receipt
        cr.insert(ignore_permissions=True)
        
        frappe.msgprint(
            _("Successfully created Custody Receipt: {0} for Asset: {1}").format(
                get_link_to_form("Custody Receipt", cr.name),
                get_link_to_form("Asset", asset_name)
            ),
            title=_("Success"),
            indicator="green"
        )
        
        return cr.name
        
    except Exception as e:
        frappe.logger().error(f"Error creating custody receipt from asset {asset_name}: {str(e)}")
        frappe.throw(_("Error creating custody receipt from asset: {0}").format(str(e)))


@frappe.whitelist()
def test_asset_linking(purchase_receipt_name):
    """
    Test function to debug asset linking issues
    """
    try:
        pr = frappe.get_doc("Purchase Receipt", purchase_receipt_name)
        
        result = {
            "purchase_receipt": pr.name,
            "company": pr.company,
            "items": [],
            "assets_found": []
        }
        
        # Check all assets for this PR
        assets = frappe.get_all("Asset",
            filters={"purchase_receipt": pr.name},
            fields=["name", "purchase_receipt_item", "item_code", "docstatus", "company"]
        )
        result["assets_found"] = assets
        
        # Check each item
        for item in pr.items:
            item_info = {
                "item_code": item.item_code,
                "item_name": item.item_name,
                "is_fixed_asset": False,
                "asset_in_item": item.get('asset'),
                "linked_assets": []
            }
            
            # Check if item is fixed asset
            try:
                item_doc = frappe.get_doc("Item", item.item_code)
                item_info["is_fixed_asset"] = item_doc.is_fixed_asset
                
                if item_doc.is_fixed_asset:
                    # Find linked assets
                    linked_assets = frappe.get_all("Asset",
                        filters={
                            "purchase_receipt": pr.name,
                            "purchase_receipt_item": item.name
                        },
                        fields=["name", "docstatus"]
                    )
                    item_info["linked_assets"] = linked_assets
            except Exception as e:
                item_info["error"] = str(e)
            
            result["items"].append(item_info)
        
        return result
        
    except Exception as e:
        return {"error": str(e)} 