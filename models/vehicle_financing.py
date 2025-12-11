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


class VehicleFinancingTransaction(models.Model):
    _name = 'vehicle.financing.transaction'
    _description = 'Vehicle Financing Transaction History'
    _order = 'product_id, transaction_date asc, id asc'

    product_id = fields.Many2one(
        'product.template',
        string='Vehicle',
        required=True,
        ondelete='cascade',
        index=True
    )
    transaction_date = fields.Date(
        string='Transaction Date',
        required=True,
        default=fields.Date.today
    )
    transaction_type = fields.Selection([
        ('initial', 'Initial Financing'),
        ('topup', 'Top-Up Financing'),
        ('paydown', 'Pay Down'),
    ], string='Type', required=True, default='topup')
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
        help='Positive for financing/top-up, negative for pay down'
    )
    balance_after = fields.Monetary(
        string='Balance After',
        currency_field='currency_id',
        readonly=True,
        help='Floor plan balance after this transaction'
    )
    vendor_bill_id = fields.Many2one(
        'account.move',
        string='Related Bill',
        help='Vendor bill that was paid with this financing'
    )
    journal_entry_id = fields.Many2one(
        'account.move',
        string='Journal Entry',
        readonly=True,
        help='Journal entry that recorded this transaction'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    notes = fields.Text(string='Notes')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    financing_ids = fields.One2many(
        'vehicle.financing',
        'product_id',
        string='Financing History'
    )
    financing_transaction_ids = fields.One2many(
        'vehicle.financing.transaction',
        'product_id',
        string='Financing Transactions'
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
        """Create journal entry to record floor plan financing and pay vendor bills.
        
        Payment priority:
        1. Original vendor bill (from purchase order) gets paid first
        2. If financing amount remains, landed cost bills are paid in chronological order (earliest first)
        """
        self.ensure_one()
        
        if self.financing_type != 'internal':
            raise UserError(_('Floor plan financing can only be set up for internal financing.'))
        
        if not self.financing_amount or self.financing_amount <= 0:
            raise UserError(_('Please set a valid financing amount first.'))
        
        if not self.financing_partner_id:
            raise UserError(_('Please set the financing partner first.'))
        
        if self.financing_journal_entry_id:
            raise UserError(_('Floor plan financing has already been set up for this vehicle.'))
        
        # Find the primary vendor bill from purchase order
        po_lines = self.env['purchase.order.line'].search([
            ('product_id', 'in', self.product_variant_ids.ids),
            ('order_id.state', 'in', ['purchase', 'done'])
        ], limit=1)
        
        if not po_lines:
            raise UserError(_('No confirmed purchase order found for this vehicle.'))
        
        primary_vendor_bill = self.env['account.move'].search([
            ('partner_id', '=', po_lines.order_id.partner_id.id),
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('line_ids.purchase_line_id', 'in', po_lines.ids)
        ], limit=1)
        
        if not primary_vendor_bill:
            raise UserError(_('No unpaid vendor bill found for this vehicle purchase.'))
        
        # Find landed cost bills (ordered by date, earliest first)
        landed_cost_bills = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('id', '!=', primary_vendor_bill.id),
            ('id', 'in', self.vendor_bill_ids.ids)
        ], order='invoice_date asc, id asc')
        
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
        
        # Build the payment distribution
        # Priority 1: Pay the primary vendor bill
        # Priority 2: Pay landed cost bills in chronological order with remaining amount
        
        remaining_amount = self.financing_amount
        bill_payments = []
        
        # Pay primary bill first
        primary_amount_due = primary_vendor_bill.amount_residual
        primary_payment = min(remaining_amount, primary_amount_due)
        primary_payable_account = primary_vendor_bill.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
        )[0].account_id
        
        bill_payments.append({
            'bill': primary_vendor_bill,
            'amount': primary_payment,
            'account': primary_payable_account,
            'partner': primary_vendor_bill.partner_id,
            'type': 'primary'
        })
        remaining_amount -= primary_payment
        
        # Pay landed cost bills with remaining amount (if any)
        for lc_bill in landed_cost_bills:
            if remaining_amount <= 0:
                break
            
            lc_amount_due = lc_bill.amount_residual
            lc_payment = min(remaining_amount, lc_amount_due)
            lc_payable_account = lc_bill.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable'
            )[0].account_id
            
            bill_payments.append({
                'bill': lc_bill,
                'amount': lc_payment,
                'account': lc_payable_account,
                'partner': lc_bill.partner_id,
                'type': 'landed_cost'
            })
            remaining_amount -= lc_payment
        
        # Build journal entry line items
        line_items = []
        bills_paid_list = []
        
        for payment in bill_payments:
            # Debit: Accounts Payable (reduces vendor bill)
            line_items.append((0, 0, {
                'name': _('Floor plan payment - %s - %s') % (
                    'Primary Bill' if payment['type'] == 'primary' else 'Landed Cost',
                    payment['bill'].name
                ),
                'account_id': payment['account'].id,
                'partner_id': payment['partner'].id,
                'debit': payment['amount'],
                'credit': 0,
                'analytic_distribution': analytic_dist or False,
            }))
            bills_paid_list.append('%s: %s' % (payment['bill'].name, payment['amount']))
        
        # Credit: Floor Plan Payable (creates liability)
        line_items.append((0, 0, {
            'name': _('Floor plan financing - %s') % self.name,
            'account_id': liability_account.id,
            'partner_id': self.financing_partner_id.id,
            'debit': 0,
            'credit': self.financing_amount,
            'analytic_distribution': analytic_dist or False,
        }))
        
        # Create journal entry
        financing_ref = _('Floor Plan Financing - %s') % self.name
        
        journal_entry_vals = {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.financing_start_date or fields.Date.today(),
            'ref': financing_ref,
            'narration': _('Floor plan financing for %s\nFinancing Amount: %s\nFinancing Partner: %s\n\nBills Paid:\n%s') % (
                self.name,
                self.financing_amount,
                self.financing_partner_id.name,
                '\n'.join(bills_paid_list)
            ),
            'line_ids': line_items,
        }
        
        journal_entry = self.env['account.move'].create(journal_entry_vals)
        journal_entry.action_post()
        
        # Reconcile each bill payment
        for payment in bill_payments:
            payable_line = journal_entry.line_ids.filtered(
                lambda l: l.account_id == payment['account'] and l.partner_id == payment['partner']
            )
            bill_payable_line = payment['bill'].line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable'
            )
            
            if payable_line and bill_payable_line:
                (payable_line + bill_payable_line).reconcile()
            
            # Add message to each bill
            payment['bill'].message_post(
                body=Markup('<b>Floor Plan Financing Applied</b><br/>'
                       'Amount: %s<br/>'
                       'Type: %s<br/>'
                       'Financing Partner: %s<br/>'
                       'Journal Entry: %s<br/>'
                       'Vehicle: %s') % (
                    payment['amount'],
                    'Primary Bill Payment' if payment['type'] == 'primary' else 'Landed Cost Payment',
                    self.financing_partner_id.name,
                    journal_entry.name,
                    self.name
                ),
                subject=_('Floor Plan Financing')
            )
        
        # Create financing transaction record
        self.env['vehicle.financing.transaction'].create({
            'product_id': self.id,
            'transaction_date': self.financing_start_date or fields.Date.today(),
            'transaction_type': 'initial',
            'amount': self.financing_amount,
            'balance_after': self.financing_amount,
            'vendor_bill_id': primary_vendor_bill.id,
            'journal_entry_id': journal_entry.id,
            'notes': _('Initial floor plan financing setup\nPaid %d bill(s)') % len(bill_payments),
        })
        
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

    def action_topup_floor_plan_financing(self):
        """Add additional financing (top-up) for unpaid bills.
        
        Opens a wizard to enter the top-up amount, then automatically distributes
        the amount across unpaid bills in chronological order (earliest first).
        """
        self.ensure_one()
        
        if self.financing_type != 'internal':
            raise UserError(_('Top-up financing is only available for internal financing.'))
        
        if not self.financing_journal_entry_id:
            raise UserError(_('Please set up floor plan financing first before adding a top-up.'))
        
        # Find unpaid vendor bills related to this vehicle (ordered by date)
        unpaid_bills = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('id', 'in', self.vendor_bill_ids.ids)
        ], order='invoice_date asc, id asc')
        
        if not unpaid_bills:
            raise UserError(_('No unpaid bills found for this vehicle.'))
        
        # Calculate total unpaid amount
        total_unpaid = sum(unpaid_bills.mapped('amount_residual'))
        
        # Return a simplified wizard to enter top-up amount
        return {
            'name': _('Top-Up Floor Plan Financing'),
            'type': 'ir.actions.act_window',
            'res_model': 'vehicle.financing.topup.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_id': self.id,
                'default_topup_amount': total_unpaid,  # Suggest full unpaid amount
                'unpaid_bill_count': len(unpaid_bills),
                'total_unpaid_amount': total_unpaid,
            },
        }

    def action_paydown_floor_plan_financing(self):
        """Record a payment towards the floor plan financing balance.
        
        Opens a wizard to enter the paydown amount and records the transaction.
        """
        self.ensure_one()
        
        if self.financing_type != 'internal':
            raise UserError(_('Paydown is only available for internal financing.'))
        
        if not self.financing_journal_entry_id:
            raise UserError(_('Please set up floor plan financing first.'))
        
        if self.financing_balance <= 0:
            raise UserError(_('There is no outstanding financing balance to pay down.'))
        
        # Return wizard to enter paydown amount
        return {
            'name': _('Pay Down Floor Plan Financing'),
            'type': 'ir.actions.act_window',
            'res_model': 'vehicle.financing.paydown.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_id': self.id,
                'default_paydown_amount': self.financing_balance,  # Suggest full balance
                'current_balance': self.financing_balance,
            },
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
        """Create a journal entry to record interest expense and increase floor plan liability.
        
        Uses time-weighted interest calculation:
        If there are balance changes (top-ups) during the billing period,
        interest is calculated separately for each balance segment.
        
        Example: If original balance is $50,000 from day 1-19, then $55,000 from day 20-30,
        we charge interest on $50,000 for 19 days and $55,000 for 11 days.
        """
        self.ensure_one()
        
        # Determine the billing period
        # For the first bill, start from financing_start_date
        # For subsequent bills, start from the day after last_interest_bill_date
        if self.last_interest_bill_date:
            period_start = self.last_interest_bill_date + relativedelta(days=1)
        else:
            period_start = self.financing_start_date
        
        # Period end is the last day of the bill_date's month
        period_end = (bill_date + relativedelta(day=31))
        
        # Get all financing transactions within this billing period
        # Transactions represent balance changes (initial financing, top-ups, etc.)
        transactions = self.env['vehicle.financing.transaction'].search([
            ('product_id', '=', self.id),
            ('transaction_date', '>=', period_start),
            ('transaction_date', '<=', period_end),
        ], order='transaction_date asc')
        
        # Build time-weighted interest calculation
        # Start with the balance at the beginning of the period
        current_balance = self.financing_balance
        
        # If there are transactions in this period, we need to work backwards
        # to find the balance at the start of the period
        if transactions:
            # Find the balance before the first transaction in this period
            # by looking at the transaction just before this period
            prev_transaction = self.env['vehicle.financing.transaction'].search([
                ('product_id', '=', self.id),
                ('transaction_date', '<', period_start),
            ], order='transaction_date desc', limit=1)
            
            if prev_transaction:
                current_balance = prev_transaction.balance_after
            else:
                # No previous transaction means we start from 0
                # This shouldn't happen if initial financing was recorded properly
                current_balance = 0
        
        # Calculate interest for each segment
        total_interest = 0
        interest_details = []  # For description
        segment_start = period_start
        
        # Annual interest rate
        annual_rate = self.financing_rate
        
        for transaction in transactions:
            # Calculate interest from segment_start to transaction_date - 1
            segment_end = transaction.transaction_date - relativedelta(days=1)
            days_in_segment = (segment_end - segment_start).days + 1
            
            if days_in_segment > 0 and current_balance > 0:
                # Daily rate for this balance: (balance × annual_rate / 100) / 365
                daily_interest = (current_balance * annual_rate / 100) / 365
                segment_interest = daily_interest * days_in_segment
                total_interest += segment_interest
                
                interest_details.append(
                    _('  $%s @ %.2f%% for %d days = $%.2f') % (
                        '{:,.2f}'.format(current_balance),
                        annual_rate,
                        days_in_segment,
                        segment_interest
                    )
                )
            
            # Move to next segment
            current_balance = transaction.balance_after
            segment_start = transaction.transaction_date
        
        # Calculate interest for the final segment (from last transaction to period end)
        segment_end = period_end
        days_in_segment = (segment_end - segment_start).days + 1
        
        if days_in_segment > 0 and current_balance > 0:
            daily_interest = (current_balance * annual_rate / 100) / 365
            segment_interest = daily_interest * days_in_segment
            total_interest += segment_interest
            
            interest_details.append(
                _('  $%s @ %.2f%% for %d days = $%.2f') % (
                    '{:,.2f}'.format(current_balance),
                    annual_rate,
                    days_in_segment,
                    segment_interest
                )
            )
        
        # Build interest description
        if interest_details:
            interest_breakdown = '\n'.join(interest_details)
            interest_description = _('Interest charge - %s\nVehicle: %s\nPeriod: %s to %s\n\nTime-weighted calculation:\n%s\n\nTotal Interest: $%.2f') % (
                bill_date.strftime('%B %Y'),
                self.name,
                period_start.strftime('%m/%d/%Y'),
                period_end.strftime('%m/%d/%Y'),
                interest_breakdown,
                total_interest
            )
        else:
            # Fallback to simple calculation if no transactions found
            days_charged = (period_end - period_start).days + 1
            daily_rate = (current_balance * annual_rate / 100) / 365
            total_interest = daily_rate * days_charged
            
            interest_description = _('Interest charge - %s\nVehicle: %s\nPeriod: %s to %s\nDaily Rate: $%.2f × %d days') % (
                bill_date.strftime('%B %Y'),
                self.name,
                period_start.strftime('%m/%d/%Y'),
                period_end.strftime('%m/%d/%Y'),
                daily_rate,
                days_charged
            )
        
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
                    'debit': total_interest,
                    'credit': 0,
                    'analytic_distribution': analytic_dist or False,
                }),
                # Credit: Floor Plan Payable (increases liability)
                (0, 0, {
                    'name': interest_description,
                    'account_id': liability_account.id,
                    'partner_id': self.financing_partner_id.id,
                    'debit': 0,
                    'credit': total_interest,
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
            'interest_amount': total_interest,
            'bill_id': bill.id,
        })
        
        # Update last bill date and increase floor plan balance
        self.write({
            'last_interest_bill_date': bill_date,
            'financing_balance': self.financing_balance + total_interest,
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
            'view_mode': 'list,form',
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


class VehicleFinancingTopupWizard(models.TransientModel):
    _name = 'vehicle.financing.topup.wizard'
    _description = 'Top-Up Floor Plan Financing Wizard'

    product_id = fields.Many2one(
        'product.template',
        string='Vehicle',
        required=True,
        readonly=True
    )
    topup_amount = fields.Monetary(
        string='Top-Up Amount',
        currency_field='currency_id',
        required=True,
        help='Amount to add to floor plan financing. Will be automatically distributed across unpaid bills in chronological order.'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    topup_date = fields.Date(
        string='Top-Up Date',
        required=True,
        default=fields.Date.today
    )
    notes = fields.Text(string='Notes')
    
    # Display fields to show unpaid bills summary
    unpaid_bill_count = fields.Integer(
        string='Unpaid Bills',
        compute='_compute_unpaid_summary'
    )
    total_unpaid_amount = fields.Monetary(
        string='Total Unpaid',
        currency_field='currency_id',
        compute='_compute_unpaid_summary'
    )
    has_posted_interest_bill = fields.Boolean(
        string='Has Posted Interest Bill',
        compute='_compute_interest_bill_warning',
        help='Indicates if there is already a posted interest bill for the top-up period'
    )
    interest_bill_warning = fields.Text(
        string='Warning',
        compute='_compute_interest_bill_warning'
    )

    @api.depends('product_id')
    def _compute_unpaid_summary(self):
        for wizard in self:
            if wizard.product_id:
                unpaid_bills = self.env['account.move'].search([
                    ('move_type', '=', 'in_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ['not_paid', 'partial']),
                    ('id', 'in', wizard.product_id.vendor_bill_ids.ids)
                ])
                wizard.unpaid_bill_count = len(unpaid_bills)
                wizard.total_unpaid_amount = sum(unpaid_bills.mapped('amount_residual'))
            else:
                wizard.unpaid_bill_count = 0
                wizard.total_unpaid_amount = 0
    
    @api.depends('product_id', 'topup_date')
    def _compute_interest_bill_warning(self):
        for wizard in self:
            if wizard.product_id and wizard.topup_date:
                # Check if there's already an interest bill for this period
                topup_period_start = wizard.topup_date.replace(day=1)
                topup_period_end = (wizard.topup_date + relativedelta(day=31))
                
                existing_bills = self.env['vehicle.financing'].search([
                    ('product_id', '=', wizard.product_id.id),
                    ('bill_date', '>=', topup_period_start),
                    ('bill_date', '<=', topup_period_end),
                    ('bill_id.state', '=', 'posted'),
                ], limit=1)
                
                if existing_bills:
                    wizard.has_posted_interest_bill = True
                    days_remaining = (topup_period_end - wizard.topup_date).days + 1
                    wizard.interest_bill_warning = _(
                        'Note: An interest bill already exists for %s. '
                        'A supplemental interest bill will be automatically generated '
                        'to charge interest on this top-up amount for the remaining %d days of the period.'
                    ) % (wizard.topup_date.strftime('%B %Y'), days_remaining)
                else:
                    wizard.has_posted_interest_bill = False
                    wizard.interest_bill_warning = False
            else:
                wizard.has_posted_interest_bill = False
                wizard.interest_bill_warning = False

    def action_apply_topup(self):
        """Create journal entry for top-up financing and automatically distribute across unpaid bills.
        
        Payment distribution:
        - Unpaid bills are paid in chronological order (earliest invoice date first)
        - Each bill gets paid up to its outstanding amount or remaining top-up balance
        """
        self.ensure_one()
        
        product = self.product_id
        
        # Find all unpaid bills in chronological order
        unpaid_bills = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('id', 'in', product.vendor_bill_ids.ids)
        ], order='invoice_date asc, id asc')
        
        if not unpaid_bills:
            raise UserError(_('No unpaid bills found for this vehicle.'))
        
        # Get the liability account
        liability_account = product.financing_liability_account_id
        if not liability_account:
            liability_account = self.env.ref('nexus_odoo_car_dealer.account_floor_plan_payable', raise_if_not_found=False)
        
        if not liability_account:
            raise UserError(_('Please configure the Floor Plan Payable account.'))
        
        # Get the default journal
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not journal:
            raise UserError(_('No general journal found.'))
        
        # Prepare analytic distribution
        analytic_dist = {str(product.analytic_account_id.id): 100.0} if product.analytic_account_id else {}
        
        # Build the payment distribution across unpaid bills
        remaining_amount = self.topup_amount
        bill_payments = []
        
        for bill in unpaid_bills:
            if remaining_amount <= 0:
                break
            
            bill_amount_due = bill.amount_residual
            payment_amount = min(remaining_amount, bill_amount_due)
            payable_account = bill.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable'
            )[0].account_id
            
            bill_payments.append({
                'bill': bill,
                'amount': payment_amount,
                'account': payable_account,
                'partner': bill.partner_id,
            })
            remaining_amount -= payment_amount
        
        # Build journal entry line items
        line_items = []
        bills_paid_list = []
        
        for payment in bill_payments:
            # Debit: Accounts Payable (reduces vendor bill)
            line_items.append((0, 0, {
                'name': _('Floor plan top-up payment - %s') % payment['bill'].name,
                'account_id': payment['account'].id,
                'partner_id': payment['partner'].id,
                'debit': payment['amount'],
                'credit': 0,
                'analytic_distribution': analytic_dist or False,
            }))
            bills_paid_list.append('%s: %s' % (payment['bill'].name, payment['amount']))
        
        # Credit: Floor Plan Payable (increases liability)
        line_items.append((0, 0, {
            'name': _('Floor plan top-up - %s') % product.name,
            'account_id': liability_account.id,
            'partner_id': product.financing_partner_id.id,
            'debit': 0,
            'credit': self.topup_amount,
            'analytic_distribution': analytic_dist or False,
        }))
        
        # Create journal entry for top-up
        topup_ref = _('Floor Plan Top-Up - %s') % product.name
        
        journal_entry_vals = {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.topup_date,
            'ref': topup_ref,
            'narration': _('Floor plan financing top-up\nVehicle: %s\nTop-Up Amount: %s\n\nBills Paid:\n%s%s') % (
                product.name,
                self.topup_amount,
                '\n'.join(bills_paid_list),
                '\n\n' + self.notes if self.notes else ''
            ),
            'line_ids': line_items,
        }
        
        journal_entry = self.env['account.move'].create(journal_entry_vals)
        journal_entry.action_post()
        
        # Reconcile each bill payment
        for payment in bill_payments:
            payable_line = journal_entry.line_ids.filtered(
                lambda l: l.account_id == payment['account'] and l.partner_id == payment['partner']
            )
            bill_payable_line = payment['bill'].line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable'
            )
            
            if payable_line and bill_payable_line:
                (payable_line + bill_payable_line).reconcile()
            
            # Add message to each bill
            payment['bill'].message_post(
                body=Markup('<b>Floor Plan Top-Up Applied</b><br/>'
                       'Amount: %s<br/>'
                       'Date: %s<br/>'
                       'Financing Partner: %s<br/>'
                       'Journal Entry: %s<br/>'
                       'Vehicle: %s') % (
                    payment['amount'],
                    self.topup_date,
                    product.financing_partner_id.name,
                    journal_entry.name,
                    product.name
                ),
                subject=_('Floor Plan Top-Up')
            )
        
        # Create financing transaction record
        new_balance = product.financing_balance + self.topup_amount
        self.env['vehicle.financing.transaction'].create({
            'product_id': product.id,
            'transaction_date': self.topup_date,
            'transaction_type': 'topup',
            'amount': self.topup_amount,
            'balance_after': new_balance,
            'vendor_bill_id': bill_payments[0]['bill'].id if bill_payments else False,
            'journal_entry_id': journal_entry.id,
            'notes': (self.notes or '') + _('\nPaid %d bill(s) automatically') % len(bill_payments),
        })
        
        # Update financing balance
        product.write({
            'financing_balance': new_balance,
        })
        
        # Check if top-up occurred in an already-billed period
        # This handles the edge case where interest was already charged on the old balance
        self._handle_topup_interest_adjustment(product)
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': journal_entry.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _handle_topup_interest_adjustment(self, product):
        """Handle interest adjustment when top-up occurs in an already-billed period.
        
        Edge cases handled:
        1. Top-up in month with posted interest bill -> Generate supplemental interest bill
        2. Top-up in month with draft interest bill -> Delete draft and let next run regenerate
        3. Multiple top-ups in same month -> Each generates its own adjustment
        """
        # Find if there's an interest bill for the period containing the top-up date
        topup_period_start = self.topup_date.replace(day=1)
        topup_period_end = (self.topup_date + relativedelta(day=31))
        
        # Look for existing interest bills that cover this period
        existing_bills = self.env['vehicle.financing'].search([
            ('product_id', '=', product.id),
            ('bill_date', '>=', topup_period_start),
            ('bill_date', '<=', topup_period_end),
        ], order='bill_date desc')
        
        if not existing_bills:
            # No interest bill exists for this period yet - normal case, no action needed
            return
        
        # Check each bill to see if it needs adjustment
        for financing_record in existing_bills:
            bill = financing_record.bill_id
            
            if bill.state == 'draft':
                # Draft bill exists - delete it so it can be regenerated with correct time-weighted interest
                bill.message_post(
                    body=Markup('<b>Interest Bill Cancelled</b><br/>'
                           'Reason: Top-up occurred on %s during this billing period<br/>'
                           'This bill will be regenerated with time-weighted interest calculation') % (
                        self.topup_date.strftime('%m/%d/%Y')
                    ),
                    subject=_('Bill Cancelled - Top-Up Adjustment')
                )
                financing_record.unlink()
                bill.button_draft()
                bill.unlink()
                
                # Update last_interest_bill_date to force regeneration
                # Find the previous posted bill
                prev_bill = self.env['vehicle.financing'].search([
                    ('product_id', '=', product.id),
                    ('bill_id.state', '=', 'posted'),
                    ('bill_date', '<', financing_record.bill_date)
                ], order='bill_date desc', limit=1)
                
                if prev_bill:
                    product.write({'last_interest_bill_date': prev_bill.bill_date})
                else:
                    product.write({'last_interest_bill_date': False})
                
            elif bill.state == 'posted':
                # Posted bill exists - generate supplemental interest for the additional amount
                # Calculate how many days remain in the period after the top-up
                days_remaining = (topup_period_end - self.topup_date).days + 1
                
                if days_remaining <= 0:
                    # Top-up was on the last day of the month, no adjustment needed
                    continue
                
                # Calculate supplemental interest on the top-up amount for remaining days
                annual_rate = product.financing_rate
                daily_interest = (self.topup_amount * annual_rate / 100) / 365
                supplemental_interest = daily_interest * days_remaining
                
                if supplemental_interest <= 0:
                    continue
                
                # Generate supplemental interest bill
                self._create_supplemental_interest_bill(
                    product=product,
                    original_bill_date=financing_record.bill_date,
                    topup_amount=self.topup_amount,
                    topup_date=self.topup_date,
                    period_end=topup_period_end,
                    supplemental_interest=supplemental_interest,
                    days_charged=days_remaining
                )
    
    def _create_supplemental_interest_bill(self, product, original_bill_date, topup_amount, 
                                          topup_date, period_end, supplemental_interest, days_charged):
        """Create a supplemental interest bill for top-up that occurred mid-period."""
        
        # Get accounts
        expense_account = product.financing_expense_account_id
        if not expense_account:
            expense_account = self.env['account.account'].search([
                ('account_type', '=', 'expense'),
                '|', '|',
                ('code', 'ilike', 'interest'),
                ('name', 'ilike', 'interest'),
                ('name', 'ilike', 'financial')
            ], limit=1)
        
        if not expense_account:
            expense_account = self.env['account.account'].search([
                ('account_type', '=', 'expense'),
            ], limit=1)
        
        liability_account = product.financing_liability_account_id
        if not liability_account:
            liability_account = self.env.ref('nexus_odoo_car_dealer.account_floor_plan_payable', raise_if_not_found=False)
        
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        # Prepare analytic distribution
        analytic_dist = {str(product.analytic_account_id.id): 100.0} if product.analytic_account_id else {}
        
        # Create description
        interest_description = _('Supplemental Interest - %s\nVehicle: %s\nOriginal Bill: %s\n\nTop-Up Adjustment:\nTop-Up Amount: %s on %s\nAdditional Interest: $%s @ %.2f%% for %d days\n(From %s to %s)') % (
            original_bill_date.strftime('%B %Y'),
            product.name,
            original_bill_date.strftime('%m/%d/%Y'),
            topup_amount,
            topup_date.strftime('%m/%d/%Y'),
            '{:,.2f}'.format(topup_amount),
            product.financing_rate,
            days_charged,
            topup_date.strftime('%m/%d/%Y'),
            period_end.strftime('%m/%d/%Y')
        )
        
        # Create journal entry
        journal_entry_vals = {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': original_bill_date,  # Use same date as original bill
            'ref': _('Supplemental Interest - %s - %s') % (product.name, original_bill_date.strftime('%B %Y')),
            'line_ids': [
                (0, 0, {
                    'name': interest_description,
                    'account_id': expense_account.id,
                    'debit': supplemental_interest,
                    'credit': 0,
                    'analytic_distribution': analytic_dist or False,
                }),
                (0, 0, {
                    'name': interest_description,
                    'account_id': liability_account.id,
                    'partner_id': product.financing_partner_id.id,
                    'debit': 0,
                    'credit': supplemental_interest,
                    'analytic_distribution': analytic_dist or False,
                }),
            ],
        }
        
        bill = self.env['account.move'].create(journal_entry_vals)
        bill.action_post()
        
        # Create financing record
        self.env['vehicle.financing'].create({
            'product_id': product.id,
            'bill_date': original_bill_date,
            'interest_amount': supplemental_interest,
            'bill_id': bill.id,
        })
        
        # Update financing balance
        product.write({
            'financing_balance': product.financing_balance + supplemental_interest,
        })
        
        # Add message to product
        product.message_post(
            body=Markup('<b>Supplemental Interest Bill Generated</b><br/>'
                   'Amount: %s<br/>'
                   'Reason: Top-up of %s on %s<br/>'
                   'Days Charged: %d<br/>'
                   'Journal Entry: %s') % (
                supplemental_interest,
                topup_amount,
                topup_date.strftime('%m/%d/%Y'),
                days_charged,
                bill.name
            ),
            subject=_('Supplemental Interest')
        )


class VehicleFinancingPaydownWizard(models.TransientModel):
    _name = 'vehicle.financing.paydown.wizard'
    _description = 'Pay Down Floor Plan Financing Wizard'

    product_id = fields.Many2one(
        'product.template',
        string='Vehicle',
        required=True,
        readonly=True
    )
    paydown_amount = fields.Monetary(
        string='Paydown Amount',
        currency_field='currency_id',
        required=True,
        help='Amount to pay towards the floor plan financing balance'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    paydown_date = fields.Date(
        string='Paydown Date',
        required=True,
        default=fields.Date.today
    )
    notes = fields.Text(string='Notes')
    
    current_balance = fields.Monetary(
        string='Current Balance',
        currency_field='currency_id',
        compute='_compute_current_balance'
    )

    @api.depends('product_id')
    def _compute_current_balance(self):
        for wizard in self:
            if wizard.product_id:
                wizard.current_balance = wizard.product_id.financing_balance
            else:
                wizard.current_balance = 0

    @api.constrains('paydown_amount', 'product_id')
    def _check_paydown_amount(self):
        for wizard in self:
            if wizard.paydown_amount <= 0:
                raise UserError(_('Paydown amount must be greater than zero.'))
            if wizard.paydown_amount > wizard.product_id.financing_balance:
                raise UserError(_(
                    'Paydown amount ($%s) cannot exceed the current financing balance ($%s).'
                ) % (wizard.paydown_amount, wizard.product_id.financing_balance))

    def action_apply_paydown(self):
        """Create journal entry for paydown and reduce financing balance."""
        self.ensure_one()
        
        product = self.product_id
        
        # Get the liability account
        liability_account = product.financing_liability_account_id
        if not liability_account:
            liability_account = self.env.ref('nexus_odoo_car_dealer.account_floor_plan_payable', raise_if_not_found=False)
        
        if not liability_account:
            raise UserError(_('Please configure the Floor Plan Payable account.'))
        
        # Get the default journal
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not journal:
            raise UserError(_('No general journal found.'))
        
        # Prepare analytic distribution
        analytic_dist = {str(product.analytic_account_id.id): 100.0} if product.analytic_account_id else {}
        
        # Create journal entry for paydown
        # Debit: Floor Plan Payable (reduces liability)
        # Credit: Cash/Bank (represents payment made)
        
        paydown_ref = _('Floor Plan Paydown - %s') % product.name
        
        journal_entry_vals = {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.paydown_date,
            'ref': paydown_ref,
            'narration': _('Floor plan financing paydown\nVehicle: %s\nPaydown Amount: %s%s') % (
                product.name,
                self.paydown_amount,
                '\n\n' + self.notes if self.notes else ''
            ),
            'line_ids': [
                # Debit: Floor Plan Payable (reduces liability)
                (0, 0, {
                    'name': _('Floor plan paydown - %s') % product.name,
                    'account_id': liability_account.id,
                    'partner_id': product.financing_partner_id.id,
                    'debit': self.paydown_amount,
                    'credit': 0,
                    'analytic_distribution': analytic_dist or False,
                }),
                # Credit: Cash/Bank - user should reconcile this with actual payment
                (0, 0, {
                    'name': _('Floor plan paydown - %s') % product.name,
                    'account_id': self.env.company.account_journal_payment_debit_account_id.id,
                    'debit': 0,
                    'credit': self.paydown_amount,
                    'analytic_distribution': analytic_dist or False,
                }),
            ],
        }
        
        journal_entry = self.env['account.move'].create(journal_entry_vals)
        journal_entry.action_post()
        
        # Create financing transaction record
        new_balance = product.financing_balance - self.paydown_amount
        self.env['vehicle.financing.transaction'].create({
            'product_id': product.id,
            'transaction_date': self.paydown_date,
            'transaction_type': 'paydown',
            'amount': -self.paydown_amount,  # Negative for paydown
            'balance_after': new_balance,
            'journal_entry_id': journal_entry.id,
            'notes': self.notes or _('Floor plan financing paydown'),
        })
        
        # Update financing balance and status
        vals = {'financing_balance': new_balance}
        if new_balance <= 0:
            vals['financing_status'] = 'paid_off'
        
        product.write(vals)
        
        # Add message to product
        product.message_post(
            body=Markup('<b>Floor Plan Paydown Applied</b><br/>'
                   'Amount: %s<br/>'
                   'Date: %s<br/>'
                   'New Balance: %s<br/>'
                   'Journal Entry: %s%s') % (
                self.paydown_amount,
                self.paydown_date,
                new_balance,
                journal_entry.name,
                '<br/>Status: Paid Off' if new_balance <= 0 else ''
            ),
            subject=_('Floor Plan Paydown')
        )
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': journal_entry.id,
            'view_mode': 'form',
            'target': 'current',
        }

