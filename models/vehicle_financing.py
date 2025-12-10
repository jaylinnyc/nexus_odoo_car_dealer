from odoo import api, fields, models, _
from odoo.exceptions import UserError
from markupsafe import Markup
from dateutil.relativedelta import relativedelta
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class VehicleFinancing(models.Model):
    _name = 'vehicle.financing'
    _description = 'Vehicle Financing Management'
    _order = 'product_id, bill_date desc'

    product_id = fields.Many2one(
        'product.template',
        string='Vehicle',
        required=True,
        ondelete='cascade'
    )
    bill_date = fields.Date(string='Bill Date', required=True)
    interest_amount = fields.Monetary(
        string='Interest Amount',
        currency_field='currency_id',
        required=True
    )
    bill_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
        readonly=True,
        ondelete='cascade'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
    ], string='Status', default='draft', compute='_compute_state', store=True)

    @api.depends('bill_id.state')
    def _compute_state(self):
        for rec in self:
            if rec.bill_id:
                rec.state = 'posted' if rec.bill_id.state == 'posted' else 'draft'
            else:
                rec.state = 'draft'

    def unlink(self):
        """Delete associated bills when financing record is deleted"""
        # Check if any bills are posted
        posted_bills = self.mapped('bill_id').filtered(lambda b: b.state == 'posted')
        if posted_bills:
            raise UserError(_(
                'Cannot delete financing records with posted bills. '
                'Please reset the following bills to draft first:\n%s'
            ) % ', '.join(posted_bills.mapped('name')))
        
        # Get affected products before deletion
        affected_products = self.mapped('product_id')
        
        # Delete draft bills
        bills_to_delete = self.mapped('bill_id')
        result = super().unlink()
        if bills_to_delete:
            bills_to_delete.unlink()
        
        # Recalculate last_interest_bill_date for affected products
        for product in affected_products:
            # Find the most recent remaining bill date
            latest_financing = self.search(
                [('product_id', '=', product.id)],
                order='bill_date desc',
                limit=1
            )
            product.last_interest_bill_date = latest_financing.bill_date if latest_financing else False
        
        return result


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    financing_ids = fields.One2many(
        'vehicle.financing',
        'product_id',
        string='Financing History'
    )
    financing_count = fields.Integer(
        string='Financing Bills',
        compute='_compute_financing_count'
    )

    @api.depends('financing_ids')
    def _compute_financing_count(self):
        for product in self:
            product.financing_count = len(product.financing_ids)

    def action_setup_floor_plan_financing(self):
        """Create journal entry to record floor plan financing and pay vendor bill."""
        self.ensure_one()
        
        if self.financing_type != 'internal':
            raise UserError(_('Floor plan financing can only be set up for internal financing.'))
        
        if not self.financing_amount or self.financing_amount <= 0:
            raise UserError(_('Please set a valid financing amount first.'))
        
        if not self.financing_partner_id:
            raise UserError(_('Please set the financing partner first.'))
        
        if self.financing_journal_entry_id:
            raise UserError(_('Floor plan financing has already been set up for this vehicle.'))
        
        # Find the vendor bill from purchase order
        po_lines = self.env['purchase.order.line'].search([
            ('product_id', 'in', self.product_variant_ids.ids),
            ('order_id.state', 'in', ['purchase', 'done'])
        ], limit=1)
        
        if not po_lines:
            raise UserError(_('No confirmed purchase order found for this vehicle.'))
        
        vendor_bill = self.env['account.move'].search([
            ('partner_id', '=', po_lines.order_id.partner_id.id),
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('line_ids.purchase_line_id', 'in', po_lines.ids)
        ], limit=1)
        
        if not vendor_bill:
            raise UserError(_('No unpaid vendor bill found for this vehicle purchase.'))
        
        # Get the liability account
        liability_account = self.financing_liability_account_id
        if not liability_account:
            # Try to find the Floor Plan Payable account
            liability_account = self.env.ref('nexus_odoo_car_dealer.account_floor_plan_payable', raise_if_not_found=False)
        
        if not liability_account:
            # Search for any current liability account with "floor plan" in the name
            liability_account = self.env['account.account'].search([
                ('account_type', 'in', ['liability_current', 'liability_non_current']),
                '|',
                ('name', 'ilike', 'floor plan'),
                ('name', 'ilike', 'payable')
            ], limit=1)
        
        if not liability_account:
            raise UserError(_('Please configure the Floor Plan Payable account in the Financing tab or create an account with account type "Current Liabilities".'))
        
        # Get the default journal for payments
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not journal:
            raise UserError(_('No general journal found. Please create one first.'))
        
        # Prepare analytic distribution
        analytic_dist = {str(self.analytic_account_id.id): 100.0} if self.analytic_account_id else {}
        
        # Create journal entry to record the financing
        financing_ref = _('Floor Plan Financing - %s (Partner: %s)') % (
            self.name, 
            self.financing_partner_id.name
        )
        
        journal_entry_vals = {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.financing_start_date or fields.Date.today(),
            'ref': financing_ref,
            'narration': _('Floor plan financing for %s\nFinancing Amount: %s\nFinancing Partner: %s\nVendor Bill: %s') % (
                self.name,
                self.financing_amount,
                self.financing_partner_id.name,
                vendor_bill.name
            ),
            'line_ids': [
                # Debit: Accounts Payable (reduces vendor bill)
                (0, 0, {
                    'name': _('Floor plan payment - %s via %s') % (self.name, self.financing_partner_id.name),
                    'account_id': vendor_bill.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')[0].account_id.id,
                    'partner_id': vendor_bill.partner_id.id,
                    'debit': self.financing_amount,
                    'credit': 0,
                    'analytic_distribution': analytic_dist or False,
                }),
                # Credit: Floor Plan Payable (creates liability)
                (0, 0, {
                    'name': _('Floor plan financing - %s') % self.name,
                    'account_id': liability_account.id,
                    'partner_id': self.financing_partner_id.id,
                    'debit': 0,
                    'credit': self.financing_amount,
                    'analytic_distribution': analytic_dist or False,
                }),
            ],
        }
        
        journal_entry = self.env['account.move'].create(journal_entry_vals)
        journal_entry.action_post()
        
        # Register payment against vendor bill
        # Get the payable line from journal entry
        payable_line = journal_entry.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')
        vendor_bill_payable_line = vendor_bill.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')
        
        # Reconcile if amounts match or do partial reconciliation
        if payable_line and vendor_bill_payable_line:
            (payable_line + vendor_bill_payable_line).reconcile()
        
        # Add a note to the vendor bill for reference
        vendor_bill.message_post(
            body=Markup('<b>Floor Plan Financing Applied</b><br/>'
                   'Amount: %s<br/>'
                   'Financing Partner: %s<br/>'
                   'Journal Entry: %s<br/>'
                   'Vehicle: %s') % (
                self.financing_amount,
                self.financing_partner_id.name,
                journal_entry.name,
                self.name
            ),
            subject=_('Floor Plan Financing')
        )
        
        # Update product template with financing info
        self.write({
            'financing_journal_entry_id': journal_entry.id,
            'financing_balance': self.financing_amount,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': journal_entry.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_generate_interest_bill(self):
        """Manually generate an interest bill for internal financing."""
        self.ensure_one()
        
        if self.financing_type != 'internal':
            raise UserError(_('Interest bills can only be generated for internal financing.'))
        
        if self.financing_status != 'active':
            raise UserError(_('Financing is not active for this vehicle.'))
        
        if not self.financing_amount or not self.financing_rate:
            raise UserError(_('Please set financing amount and interest rate first.'))
        
        if not self.financing_partner_id:
            raise UserError(_('Please set the financing partner first.'))
        
        # Calculate next bill date
        if self.last_interest_bill_date:
            # For subsequent bills, use the last day of the next month
            bill_date = self.last_interest_bill_date + relativedelta(months=1, day=31)
        elif self.financing_start_date:
            # For the first bill, use the last day of the financing start month
            bill_date = self.financing_start_date + relativedelta(day=31)
        else:
            raise UserError(_('Please set a financing start date.'))
        
        return self._create_interest_bill(bill_date)

    def _create_interest_bill(self, bill_date):
        """Create a journal entry to record interest expense and increase floor plan liability."""
        self.ensure_one()
        
        # Calculate daily interest rate (Annual Rate / 365)
        daily_rate = (self.financing_amount * self.financing_rate / 100) / 365
        
        # Determine the billing period
        # For the first bill, start from financing_start_date
        # For subsequent bills, start from the day after last_interest_bill_date
        if self.last_interest_bill_date:
            period_start = self.last_interest_bill_date + relativedelta(days=1)
        else:
            period_start = self.financing_start_date
        
        # Period end is the last day of the bill_date's month
        period_end = (bill_date + relativedelta(day=31))
        
        # Calculate number of days in the billing period
        days_charged = (period_end - period_start).days + 1  # +1 to include both start and end dates
        
        # Calculate interest for this period
        monthly_interest = daily_rate * days_charged
        
        # Get the expense account
        expense_account = self.financing_expense_account_id
        
        if not expense_account:
            # Try to find the best matching expense account for interest
            expense_account = self.env['account.account'].search([
                ('account_type', '=', 'expense'),
                '|', '|',
                ('code', 'ilike', 'interest'),
                ('name', 'ilike', 'interest'),
                ('name', 'ilike', 'financial')
            ], limit=1)
        
        # Fallback to any expense account
        if not expense_account:
            expense_account = self.env['account.account'].search([
                ('account_type', '=', 'expense'),
            ], limit=1)
        
        if not expense_account:
            raise UserError(_('Please configure an expense account in your chart of accounts.'))
        
        # Get the liability account
        liability_account = self.financing_liability_account_id
        if not liability_account:
            raise UserError(_('Please configure the Floor Plan Payable account.'))
        
        # Get the default journal for general entries
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not journal:
            raise UserError(_('No general journal found. Please create one first.'))
        
        # Prepare analytic distribution
        analytic_dist = {str(self.analytic_account_id.id): 100.0} if self.analytic_account_id else {}
        
        # Create journal entry for interest
        interest_description = _('Interest charge - %s\nVehicle: %s\nPeriod: %s to %s\nDaily Rate: $%.2f × %d days') % (
            bill_date.strftime('%B %Y'),
            self.name,
            period_start.strftime('%m/%d/%Y'),
            period_end.strftime('%m/%d/%Y'),
            daily_rate,
            days_charged
        )
        
        journal_entry_vals = {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': bill_date,
            'ref': _('Interest - %s - %s') % (self.name, bill_date.strftime('%B %Y')),
            'line_ids': [
                # Debit: Interest Expense
                (0, 0, {
                    'name': interest_description,
                    'account_id': expense_account.id,
                    'debit': monthly_interest,
                    'credit': 0,
                    'analytic_distribution': analytic_dist or False,
                }),
                # Credit: Floor Plan Payable (increases liability)
                (0, 0, {
                    'name': interest_description,
                    'account_id': liability_account.id,
                    'partner_id': self.financing_partner_id.id,
                    'debit': 0,
                    'credit': monthly_interest,
                    'analytic_distribution': analytic_dist or False,
                }),
            ],
        }
        
        bill = self.env['account.move'].create(journal_entry_vals)
        
        # Auto-post the journal entry
        bill.action_post()
        
        # Create financing record
        financing_record = self.env['vehicle.financing'].create({
            'product_id': self.id,
            'bill_date': bill_date,
            'interest_amount': monthly_interest,
            'bill_id': bill.id,
        })
        
        # Update last bill date and increase floor plan balance
        self.write({
            'last_interest_bill_date': bill_date,
            'financing_balance': self.financing_balance + monthly_interest,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_financing(self):
        """View financing history for this vehicle."""
        self.ensure_one()
        
        return {
            'name': _('Financing History - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'vehicle.financing',
            'view_mode': 'tree,form',
            'domain': [('product_id', '=', self.id)],
            'context': {'default_product_id': self.id},
        }

    @api.model
    def _cron_generate_monthly_interest_bills(self):
        """Scheduled action to generate monthly interest bills for all active internal financing."""
        today = date.today()
        
        # Find all vehicles with active internal financing
        vehicles = self.search([
            ('financing_type', '=', 'internal'),
            ('financing_status', '=', 'active'),
            ('financing_amount', '>', 0),
            ('financing_rate', '>', 0),
            ('financing_partner_id', '!=', False),
            ('financing_start_date', '!=', False),
        ])
        
        for vehicle in vehicles:
            # Calculate next bill date
            if vehicle.last_interest_bill_date:
                next_bill_date = vehicle.last_interest_bill_date + relativedelta(months=1)
            else:
                next_bill_date = vehicle.financing_start_date
            
            # Only generate if next bill date is today or in the past
            if next_bill_date <= today:
                try:
                    vehicle._create_interest_bill(next_bill_date)
                except Exception as e:
                    # Log error but continue processing other vehicles
                    _logger.error(
                        'Failed to generate interest bill for %s: %s',
                        vehicle.name,
                        str(e),
                        exc_info=True
                    )
