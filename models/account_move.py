from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.onchange('invoice_date')
    def _onchange_invoice_date_sync_accounting(self):
        """Automatically sync accounting date to match bill/invoice date."""
        if self.invoice_date and self.move_type in ('in_invoice', 'in_refund'):
            self.date = self.invoice_date

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure accounting date matches bill date on creation."""
        for vals in vals_list:
            # For vendor bills, sync date to invoice_date if provided
            if vals.get('move_type') in ('in_invoice', 'in_refund') and vals.get('invoice_date'):
                vals['date'] = vals['invoice_date']
        
        return super().create(vals_list)

    def write(self, vals):
        """Ensure accounting date matches bill date on write."""
        # If invoice_date is being updated on a vendor bill, sync the date
        if 'invoice_date' in vals:
            for move in self:
                if move.move_type in ('in_invoice', 'in_refund'):
                    vals['date'] = vals['invoice_date']
                    break
        
        return super().write(vals)
