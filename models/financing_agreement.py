from odoo import api, fields, models, _
from odoo.exceptions import UserError

class FinancingAgreement(models.Model):
    _name = 'financing.agreement'
    _description = 'Financing Agreement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'agreement_date desc, id desc'
    _rec_name = 'display_name'

    name = fields.Char(string='Reference', copy=False, readonly=True, default=lambda self: _('New'))
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    partner_id = fields.Many2one('res.partner', string='Lender', required=True, tracking=True)
    agreement_date = fields.Date(string='Agreement Date', default=fields.Date.today, required=True, tracking=True)
    active = fields.Boolean(default=True)
    
    line_ids = fields.One2many('financing.agreement.line', 'agreement_id', string='Vehicles')
    
    total_financed_amount = fields.Monetary(string='Total Principal', compute='_compute_totals', currency_field='currency_id', store=True)
    total_balance = fields.Monetary(string='Total Balance', compute='_compute_totals', currency_field='currency_id', store=True)
    total_interest_paid = fields.Monetary(string='Total Interest Paid', compute='_compute_totals', currency_field='currency_id', store=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    vehicle_count = fields.Integer(string='Vehicles', compute='_compute_vehicle_count')
    bill_count = fields.Integer(string='Bills', compute='_compute_counts')
    journal_entry_count = fields.Integer(string='Journal Entries', compute='_compute_counts')
    
    # Related records for the detail view
    transaction_ids = fields.One2many('vehicle.financing.transaction', compute='_compute_related_records')
    interest_bill_ids = fields.One2many('vehicle.financing', compute='_compute_related_records')
    related_bill_ids = fields.Many2many('account.move', compute='_compute_related_records')
    
    # Warning flag for overbilled lines
    has_overbilled_lines = fields.Boolean(
        string='Has Overbilled Lines',
        compute='_compute_has_overbilled_lines',
        help='Warning: One or more vehicles have financing amounts exceeding their billed amounts.'
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('financing.agreement') or _('New')
        return super().create(vals_list)

    def unlink(self):
        """Override unlink to clean up all related journal entries, transactions, and interest bills."""
        for record in self:
            # Collect all related records
            vehicle_ids = record.line_ids.mapped('vehicle_id')
            
            # Get all transactions for vehicles in this agreement
            transactions = self.env['vehicle.financing.transaction'].search([
                ('product_id', 'in', vehicle_ids.ids)
            ])
            
            # Get all interest bill records FIRST (before we delete journal entries)
            interest_bills = self.env['vehicle.financing'].search([
                ('agreement_line_id', 'in', record.line_ids.ids)
            ])
            
            # Collect all journal entries
            journal_entries = transactions.mapped('journal_entry_id')
            journal_entries |= record.line_ids.mapped('journal_entry_id')
            # Also get interest bill journal entries
            interest_journal_entries = interest_bills.mapped('bill_id')
            journal_entries |= interest_journal_entries
            
            # Filter out empty/deleted records
            journal_entries = journal_entries.filtered(lambda j: j.exists())
            
            # Clear references BEFORE deleting to avoid cascade issues
            # Clear transaction journal entry references
            if transactions.exists():
                transactions.write({'journal_entry_id': False})
            
            # Clear interest bill references
            if interest_bills.exists():
                interest_bills.write({'bill_id': False})
            
            # Reset posted journal entries to draft first
            posted_entries = journal_entries.filtered(lambda j: j.exists() and j.state == 'posted')
            if posted_entries:
                posted_entries.button_draft()
            
            # Delete journal entries (now safe since references are cleared)
            journal_entries = journal_entries.filtered(lambda j: j.exists())
            if journal_entries:
                journal_entries.unlink()
            
            # Delete transactions
            transactions = transactions.filtered(lambda t: t.exists())
            if transactions:
                transactions.unlink()
            
            # Delete interest bill records
            interest_bills = interest_bills.filtered(lambda b: b.exists())
            if interest_bills:
                interest_bills.unlink()
            
            # Reset vehicle financing fields
            for vehicle in vehicle_ids.filtered(lambda v: v.exists()):
                vehicle.write({
                    'financing_type': 'none',
                    'financing_amount': 0,
                    'financing_rate': 0,
                    'financing_balance': 0,
                    'financing_status': 'active',
                    'financing_start_date': False,
                    'financing_partner_id': False,
                    'financing_journal_entry_id': False,
                    'last_interest_bill_date': False,
                })
        
        return super().unlink()

    @api.depends('partner_id', 'agreement_date')
    def _compute_display_name(self):
        for record in self:
            if record.partner_id:
                date_str = record.agreement_date.strftime('%Y-%m-%d') if record.agreement_date else ''
                record.display_name = f"{record.partner_id.name} - {date_str}"
            else:
                record.display_name = record.name or _('New Agreement')

    @api.depends('line_ids.financed_amount', 'line_ids.current_balance', 'line_ids.accumulated_interest')
    def _compute_totals(self):
        for record in self:
            record.total_financed_amount = sum(record.line_ids.mapped('financed_amount'))
            record.total_balance = sum(record.line_ids.mapped('current_balance'))
            record.total_interest_paid = sum(record.line_ids.mapped('accumulated_interest'))

    @api.depends('line_ids.has_overbilled_warning')
    def _compute_has_overbilled_lines(self):
        for record in self:
            record.has_overbilled_lines = any(record.line_ids.mapped('has_overbilled_warning'))

    def _compute_vehicle_count(self):
        for record in self:
            record.vehicle_count = len(record.line_ids)

    def _compute_counts(self):
        for record in self:
            # Count interest bills
            record.bill_count = self.env['vehicle.financing'].search_count([
                ('agreement_line_id', 'in', record.line_ids.ids)
            ])
            # Count journal entries from transactions
            transactions = self.env['vehicle.financing.transaction'].search([
                ('product_id', 'in', record.line_ids.mapped('vehicle_id').ids)
            ])
            record.journal_entry_count = len(transactions.mapped('journal_entry_id'))

    def _compute_related_records(self):
        for record in self:
            # Get all vehicle IDs from agreement lines
            vehicle_ids = record.line_ids.mapped('vehicle_id').ids
            
            # Get transactions for all vehicles in this agreement
            record.transaction_ids = self.env['vehicle.financing.transaction'].search([
                ('product_id', 'in', vehicle_ids)
            ])
            
            # Get interest bills for all lines
            record.interest_bill_ids = self.env['vehicle.financing'].search([
                ('agreement_line_id', 'in', record.line_ids.ids)
            ])
            
            # Get related vendor bills for all vehicles
            bills = self.env['account.move']
            for line in record.line_ids:
                if line.vehicle_id and line.vehicle_id.vendor_bill_ids:
                    bills |= line.vehicle_id.vendor_bill_ids
            record.related_bill_ids = bills

    def action_view_vehicles(self):
        self.ensure_one()
        vehicles = self.line_ids.mapped('vehicle_id')
        return {
            'name': _('Financed Vehicles'),
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'view_mode': 'list,form',
            'domain': [('id', 'in', vehicles.ids)],
            'context': {'create': False},
        }

    def action_view_all_bills(self):
        """View all vendor bills related to vehicles in this agreement"""
        self.ensure_one()
        bills = self.env['account.move']
        for line in self.line_ids:
            if line.vehicle_id and line.vehicle_id.vendor_bill_ids:
                bills |= line.vehicle_id.vendor_bill_ids
        # Also include interest bills
        interest_bills = self.env['vehicle.financing'].search([
            ('agreement_line_id', 'in', self.line_ids.ids)
        ]).mapped('bill_id')
        bills |= interest_bills
        
        return {
            'name': _('Related Bills'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', bills.ids)],
            'context': {'create': False},
        }

    def action_view_journal_entries(self):
        """View all journal entries related to this agreement"""
        self.ensure_one()
        vehicle_ids = self.line_ids.mapped('vehicle_id').ids
        transactions = self.env['vehicle.financing.transaction'].search([
            ('product_id', 'in', vehicle_ids)
        ])
        journal_entries = transactions.mapped('journal_entry_id')
        
        # Also include opening entries
        opening_entries = self.line_ids.mapped('journal_entry_id')
        journal_entries |= opening_entries
        
        return {
            'name': _('Journal Entries'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', journal_entries.ids)],
            'context': {'create': False},
        }

    def action_activate(self):
        """Activate the agreement and all its lines, pay vendor bills, create journal entries"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft agreements can be activated.'))
            
            # Activate each line and set up financing
            for line in record.line_ids:
                line._setup_financing()
                line.state = 'active'
            
            record.write({'state': 'active'})
            record.message_post(body=_('Agreement activated. All vendor bills have been paid via floor plan financing.'))

    def action_reset_to_draft(self):
        """Reset agreement to draft, reverse all journal entries and bill payments"""
        for record in self:
            if record.state != 'active':
                raise UserError(_('Only active agreements can be reset to draft.'))
            
            # Reset each line
            for line in record.line_ids:
                line._reverse_financing()
                line.state = 'draft'
            
            record.write({'state': 'draft'})
            record.message_post(body=_('Agreement reset to draft. All journal entries and bill payments have been reversed.'))

    def action_close(self):
        """Close the agreement - only allowed when all lines are paid off or have zero balance"""
        for record in self:
            # Check if there are any active lines with balance
            active_lines_with_balance = record.line_ids.filtered(
                lambda l: l.state == 'active' and l.current_balance > 0
            )
            
            if active_lines_with_balance:
                vehicle_names = ', '.join(active_lines_with_balance.mapped('vehicle_id.name'))
                total_balance = sum(active_lines_with_balance.mapped('current_balance'))
                raise UserError(_(
                    'Cannot close agreement: The following vehicles still have outstanding balances:\n\n'
                    '%s\n\n'
                    'Total Outstanding: %s\n\n'
                    'Please use "Pay Down" on each vehicle to clear the balance before closing the agreement, '
                    'or use "Full Payoff" when the vehicle is sold.'
                ) % (vehicle_names, total_balance))
            
            # Mark any remaining active lines (with zero balance) as paid off
            for line in record.line_ids.filtered(lambda l: l.state == 'active'):
                line.write({
                    'state': 'paid_off',
                    'end_date': fields.Date.today(),
                })
                # Update the vehicle financing status
                if line.vehicle_id:
                    line.vehicle_id.write({'financing_status': 'paid_off'})
            
            record.write({'state': 'closed'})

    @api.model
    def migrate_old_data(self):
        """Migrate data from product.template to financing.agreement"""
        # Find all products with financing
        products = self.env['product.template'].search([('financing_type', '!=', 'none')])
        Agreement = self.env['financing.agreement']
        # Use context to skip financing validation during migration
        AgreementLine = self.env['financing.agreement.line'].with_context(skip_financing_validation=True)
        
        count = 0
        for product in products:
            # Check if already migrated
            existing_line = AgreementLine.search([('vehicle_id', '=', product.id)], limit=1)
            if existing_line:
                continue
        
            # Create Agreement (One per vehicle for safety/simplicity in migration)
            agreement = Agreement.create({
                'partner_id': product.financing_partner_id.id or self.env.user.partner_id.id, # Fallback if missing
                'agreement_date': product.financing_start_date or fields.Date.today(),
                'state': 'active' if product.financing_status == 'active' else 'closed',
            })
        
            # Create Agreement Line
            line = AgreementLine.create({
                'agreement_id': agreement.id,
                'vehicle_id': product.id,
                'financed_amount': product.financing_amount,
                'interest_rate': product.financing_rate,
                'start_date': product.financing_start_date or fields.Date.today(),
                'current_balance': product.financing_balance,
                'state': 'active' if product.financing_status == 'active' else 'paid_off',
                'expense_account_id': product.financing_expense_account_id.id,
                'liability_account_id': product.financing_liability_account_id.id,
                'journal_entry_id': product.financing_journal_entry_id.id,
            })
        
            # Link existing interest bills to the new line
            interest_bills = self.env['vehicle.financing'].search([('product_id', '=', product.id)])
            interest_bills.write({'agreement_line_id': line.id})
            count += 1
            
        return count


class FinancingAgreementLine(models.Model):
    _name = 'financing.agreement.line'
    _description = 'Financing Agreement Line (Vehicle)'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    agreement_id = fields.Many2one('financing.agreement', string='Agreement', required=True, ondelete='cascade')
    partner_id = fields.Many2one(related='agreement_id.partner_id', string='Lender', store=True)
    vehicle_id = fields.Many2one('product.template', string='Vehicle', required=True, domain=[('make', '!=', False)])
    
    currency_id = fields.Many2one(related='agreement_id.currency_id')
    
    financed_amount = fields.Monetary(string='Principal Amount', required=True, tracking=True)
    interest_rate = fields.Float(string='Interest Rate (%)', required=True, tracking=True)
    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date')
    
    current_balance = fields.Monetary(string='Current Balance', tracking=True)
    accumulated_interest = fields.Monetary(string='Accumulated Interest', compute='_compute_accumulated_interest', store=True, currency_field='currency_id')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('paid_off', 'Paid Off'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    # Accounting
    expense_account_id = fields.Many2one('account.account', string='Interest Expense Account')
    liability_account_id = fields.Many2one('account.account', string='Liability Account')
    journal_entry_id = fields.Many2one('account.move', string='Opening Entry')

    # Link to interest bills
    interest_bill_ids = fields.One2many('vehicle.financing', 'agreement_line_id', string='Interest Bills')
    
    # Warning flag for overbilled financing (migrated data)
    has_overbilled_warning = fields.Boolean(
        string='Financing Exceeds Bills',
        compute='_compute_overbilled_warning',
        store=True,
        help='Warning: The financing amount exceeds the total billed amount for this vehicle.'
    )
    
    # Computed fields for stat buttons
    interest_bill_count = fields.Integer(string='Interest Bills', compute='_compute_counts')
    transaction_count = fields.Integer(string='Transactions', compute='_compute_counts')
    transaction_ids = fields.One2many('vehicle.financing.transaction', compute='_compute_transactions')

    @api.depends('interest_bill_ids.interest_amount', 'interest_bill_ids.state')
    def _compute_accumulated_interest(self):
        for record in self:
            # Sum all posted interest bills
            posted_bills = record.interest_bill_ids.filtered(lambda b: b.state == 'posted')
            record.accumulated_interest = sum(posted_bills.mapped('interest_amount'))

    @api.depends('financed_amount', 'vehicle_id', 'vehicle_id.total_bills_amount')
    def _compute_overbilled_warning(self):
        """Check if financing amount exceeds total billed amount"""
        for record in self:
            if record.vehicle_id and record.financed_amount:
                total_billed = record.vehicle_id.total_bills_amount
                record.has_overbilled_warning = record.financed_amount > total_billed
            else:
                record.has_overbilled_warning = False

    @api.constrains('financed_amount', 'vehicle_id')
    def _check_financed_amount_limit(self):
        """Ensure financed amount does not exceed total billed amount for the vehicle
        
        This validation is skipped during migration (context key: skip_financing_validation)
        """
        # Skip validation during migration
        if self.env.context.get('skip_financing_validation'):
            return
        
        for record in self:
            if record.vehicle_id and record.financed_amount:
                total_billed = record.vehicle_id.total_bills_amount
                if record.financed_amount > total_billed:
                    raise UserError(_(
                        'The financing amount (%(financed)s) cannot exceed the total billed amount (%(billed)s) for vehicle %(vehicle)s.',
                        financed=record.financed_amount,
                        billed=total_billed,
                        vehicle=record.vehicle_id.name
                    ))

    def _compute_counts(self):
        for record in self:
            record.interest_bill_count = len(record.interest_bill_ids)
            record.transaction_count = self.env['vehicle.financing.transaction'].search_count([
                ('product_id', '=', record.vehicle_id.id)
            ]) if record.vehicle_id else 0

    def _compute_transactions(self):
        for record in self:
            if record.vehicle_id:
                record.transaction_ids = self.env['vehicle.financing.transaction'].search([
                    ('product_id', '=', record.vehicle_id.id)
                ])
            else:
                record.transaction_ids = self.env['vehicle.financing.transaction']

    @api.depends('vehicle_id')
    def _compute_name(self):
        for record in self:
            record.name = f"{record.agreement_id.name} - {record.vehicle_id.name}"

    def _setup_financing(self):
        """Set up floor plan financing: create journal entry and pay vendor bills.
        
        This replicates the logic from product.template.action_setup_floor_plan_financing
        """
        self.ensure_one()
        vehicle = self.vehicle_id
        
        if not vehicle:
            raise UserError(_('No vehicle linked to this financing line.'))
        
        if not self.financed_amount or self.financed_amount <= 0:
            raise UserError(_('Please set a valid financing amount for %s.') % vehicle.name)
        
        if self.journal_entry_id:
            raise UserError(_('Financing has already been set up for %s.') % vehicle.name)
        
        # Find all unpaid vendor bills for this vehicle
        unpaid_bills = vehicle.vendor_bill_ids.filtered(
            lambda b: b.state == 'posted' and b.payment_state in ['not_paid', 'partial']
        ).sorted(key=lambda b: (b.invoice_date or fields.Date.today(), b.id))
        
        if not unpaid_bills:
            raise UserError(_('No unpaid vendor bills found for %s.') % vehicle.name)
        
        # Get the liability account
        liability_account = self.liability_account_id
        if not liability_account:
            liability_account = self.env.ref('nexus_odoo_car_dealer.account_floor_plan_payable', raise_if_not_found=False)
        
        if not liability_account:
            liability_account = self.env['account.account'].search([
                ('account_type', 'in', ['liability_current', 'liability_non_current', 'liability_payable']),
                '|', ('name', 'ilike', 'floor plan'), ('name', 'ilike', 'payable')
            ], limit=1)
        
        if not liability_account:
            raise UserError(_('Please configure a Floor Plan Liability account.'))
        
        # Get the journal
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not journal:
            raise UserError(_('No general journal found.'))
        
        # Prepare analytic distribution
        analytic_dist = {str(vehicle.analytic_account_id.id): 100.0} if vehicle.analytic_account_id else {}
        
        # Build bill payment distribution
        remaining_amount = self.financed_amount
        bill_payments = []
        
        for bill in unpaid_bills:
            if remaining_amount <= 0:
                break
            
            amount_due = bill.amount_residual
            payment_amount = min(remaining_amount, amount_due)
            payable_account = bill.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable'
            )
            
            if payable_account:
                bill_payments.append({
                    'bill': bill,
                    'amount': payment_amount,
                    'account': payable_account[0].account_id,
                    'partner': bill.partner_id,
                })
                remaining_amount -= payment_amount
        
        if not bill_payments:
            raise UserError(_('Could not allocate financing to any bills for %s.') % vehicle.name)
        
        # Build journal entry line items
        line_items = []
        bills_paid_list = []
        
        for payment in bill_payments:
            line_items.append((0, 0, {
                'name': _('Floor plan payment - %s') % payment['bill'].name,
                'account_id': payment['account'].id,
                'partner_id': payment['partner'].id,
                'debit': payment['amount'],
                'credit': 0,
                'analytic_distribution': analytic_dist or False,
            }))
            bills_paid_list.append('%s: %s' % (payment['bill'].name, payment['amount']))
        
        # Credit: Floor Plan Payable
        line_items.append((0, 0, {
            'name': _('Floor plan financing - %s') % vehicle.name,
            'account_id': liability_account.id,
            'partner_id': self.partner_id.id,
            'debit': 0,
            'credit': self.financed_amount,
            'analytic_distribution': analytic_dist or False,
        }))
        
        # Create and post journal entry
        journal_entry = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.start_date or fields.Date.today(),
            'ref': _('Floor Plan Financing - %s') % vehicle.name,
            'narration': _('Floor plan financing for %s\nAmount: %s\nLender: %s\n\nBills Paid:\n%s') % (
                vehicle.name, self.financed_amount, self.partner_id.name, '\n'.join(bills_paid_list)
            ),
            'line_ids': line_items,
        })
        journal_entry.action_post()
        
        # Reconcile bill payments
        for payment in bill_payments:
            payable_line = journal_entry.line_ids.filtered(
                lambda l: l.account_id == payment['account'] and l.partner_id == payment['partner']
            )
            bill_payable_line = payment['bill'].line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable'
            )
            
            if payable_line and bill_payable_line:
                (payable_line + bill_payable_line).reconcile()
            
            payment['bill'].message_post(
                body=_('<b>Floor Plan Financing Applied</b><br/>'
                       'Amount: %s<br/>Lender: %s<br/>Journal Entry: %s') % (
                    payment['amount'], self.partner_id.name, journal_entry.name
                )
            )
        
        # Create financing transaction record
        self.env['vehicle.financing.transaction'].create({
            'product_id': vehicle.id,
            'transaction_type': 'initial',
            'amount': self.financed_amount,
            'date': self.start_date or fields.Date.today(),
            'balance_after': self.financed_amount,
            'journal_entry_id': journal_entry.id,
            'notes': _('Initial floor plan financing via Agreement %s') % self.agreement_id.name,
        })
        
        # Update the line with journal entry reference
        self.write({
            'journal_entry_id': journal_entry.id,
            'current_balance': self.financed_amount,
        })
        
        # Update vehicle
        vehicle.write({
            'financing_journal_entry_id': journal_entry.id,
            'financing_balance': self.financed_amount,
            'last_interest_bill_date': self.start_date or fields.Date.today(),
        })

    def _reverse_financing(self):
        """Reverse all financing: cancel/delete journal entries and un-reconcile bills"""
        self.ensure_one()
        vehicle = self.vehicle_id
        
        if not self.journal_entry_id:
            # Nothing to reverse
            return
        
        # Get all transactions for this vehicle
        transactions = self.env['vehicle.financing.transaction'].search([
            ('product_id', '=', vehicle.id)
        ])
        
        # Collect all journal entries to reverse
        journal_entries = transactions.mapped('journal_entry_id')
        journal_entries |= self.journal_entry_id
        journal_entries = journal_entries.filtered(lambda j: j.exists())
        
        # Un-reconcile and reverse journal entries
        for je in journal_entries:
            if je.state == 'posted':
                # Un-reconcile all lines first
                for line in je.line_ids:
                    if line.matched_debit_ids or line.matched_credit_ids:
                        line.remove_move_reconcile()
                # Reset to draft
                je.button_draft()
            # Delete the journal entry
            je.unlink()
        
        # Clear transaction journal entry references and delete
        if transactions:
            transactions.write({'journal_entry_id': False})
            transactions.unlink()
        
        # Delete interest bill records (vehicle.financing)
        interest_bills = self.env['vehicle.financing'].search([
            ('agreement_line_id', '=', self.id)
        ])
        if interest_bills:
            # Also need to reverse/delete their bills
            bill_moves = interest_bills.mapped('bill_id').filtered(lambda b: b.exists())
            for bill in bill_moves:
                if bill.state == 'posted':
                    bill.button_draft()
                bill.unlink()
            interest_bills.write({'bill_id': False})
            interest_bills.unlink()
        
        # Reset vehicle financing fields
        vehicle.write({
            'financing_journal_entry_id': False,
            'financing_balance': 0,
            'last_interest_bill_date': False,
        })
        
        # Clear line journal entry reference and reset balance
        self.write({
            'journal_entry_id': False,
            'current_balance': self.financed_amount,
        })

    def action_view_vehicle_details(self):
        """Open the vehicle financing line detail form"""
        self.ensure_one()
        return {
            'name': _('Vehicle Financing Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'financing.agreement.line',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_view_vehicle(self):
        """Open the vehicle product form"""
        self.ensure_one()
        return {
            'name': _('Vehicle'),
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'view_mode': 'form',
            'res_id': self.vehicle_id.id,
            'target': 'current',
        }

    def action_view_interest_bills(self):
        """View interest bills for this financing line"""
        self.ensure_one()
        return {
            'name': _('Interest Bills'),
            'type': 'ir.actions.act_window',
            'res_model': 'vehicle.financing',
            'view_mode': 'list,form',
            'domain': [('agreement_line_id', '=', self.id)],
            'context': {'create': False},
        }

    def action_view_transactions(self):
        """View transactions for this financing line"""
        self.ensure_one()
        return {
            'name': _('Financing Transactions'),
            'type': 'ir.actions.act_window',
            'res_model': 'vehicle.financing.transaction',
            'view_mode': 'list,form',
            'domain': [('product_id', '=', self.vehicle_id.id)],
            'context': {'create': False},
        }

    def action_topup(self):
        """Open the top-up wizard for this vehicle"""
        self.ensure_one()
        if not self.vehicle_id:
            raise UserError(_('No vehicle linked to this financing line.'))
        return self.vehicle_id.action_topup_floor_plan_financing()

    def action_paydown(self):
        """Open the paydown wizard for this vehicle"""
        self.ensure_one()
        if not self.vehicle_id:
            raise UserError(_('No vehicle linked to this financing line.'))
        return self.vehicle_id.action_paydown_floor_plan_financing()

    def action_generate_interest_bill(self):
        """Generate interest bill for this vehicle"""
        self.ensure_one()
        if not self.vehicle_id:
            raise UserError(_('No vehicle linked to this financing line.'))
        if self.state != 'active':
            raise UserError(_('Interest bills can only be generated for active financing.'))
        return self.vehicle_id.action_generate_interest_bill()

    def action_mark_paid_off(self):
        """Mark this financing line as paid off"""
        self.ensure_one()
        if self.current_balance > 0:
            raise UserError(_('Cannot mark as paid off: There is still an outstanding balance of %s.') % self.current_balance)
        self.write({
            'state': 'paid_off',
            'end_date': fields.Date.today(),
        })
        # Update the vehicle financing status
        if self.vehicle_id:
            self.vehicle_id.write({'financing_status': 'paid_off'})
        
        # Check if all lines in the agreement are now paid off - auto-close agreement
        self._check_agreement_completion()

    def _check_agreement_completion(self):
        """Check if all lines in the agreement are paid off and auto-close if so"""
        if self.agreement_id:
            active_lines = self.agreement_id.line_ids.filtered(lambda l: l.state == 'active')
            if not active_lines:
                # All lines are paid off, close the agreement
                self.agreement_id.write({'state': 'closed'})
                self.agreement_id.message_post(
                    body=_('Agreement automatically closed - all vehicles have been paid off.'),
                    subject=_('Agreement Closed')
                )

    @api.constrains('financed_amount', 'vehicle_id')
    def _check_financed_amount(self):
        for record in self:
            if record.state == 'draft' and record.vehicle_id and record.financed_amount > record.vehicle_id.total_bills_residual:
                 raise UserError(_('The financed amount (%s) cannot exceed the total outstanding bills (%s) for vehicle %s.') % (
                    record.financed_amount, 
                    record.vehicle_id.total_bills_residual,
                    record.vehicle_id.name
                ))
