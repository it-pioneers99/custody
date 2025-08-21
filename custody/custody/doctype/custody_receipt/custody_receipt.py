# Copyright (c) 2025, gadallah and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

class CustodyReceipt(Document):
    def validate(self):
        self.validate_mandatory_fields()
    
    def validate_mandatory_fields(self):
        """Validate that required fields are set before submission"""
        if self.docstatus.is_draft():
            return
            
        if not self.get('employee'):
            frappe.throw(_("Employee is mandatory for submitting Custody Receipt"))
            
        if not self.get('posting_date'):
            frappe.throw(_("Posting Date is mandatory for submitting Custody Receipt"))
        
        # Additional validation for items if needed
        if not self.get('items') or len(self.items) == 0:
            frappe.throw(_("Cannot submit Custody Receipt without any items"))