from odoo import api, fields, models, _
from odoo.exceptions import UserError

class FinancingAgreement(models.Model):
    _name = 'financing.agreement'
    _description = 'Financing Agreement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'agreement_date desc, id desc'

    partner_id = fields.Many2one('res.partner', string='Lender', required=True, tracking=True)
    agreement_date = fields.Date(string='Agreement Date', default=fields.Date.today, required=True, tracking=True)
    active = fields.Boolean(default=True)
    
    line_ids = fields.One2many('financing.agreement.line', 'agreement_id', string='Vehicles')
    
    total_financed_amount = fields.Monetary(string='Total Principal', compute='_compute_totals', currency_field='currency_id', store=True)
    total_balance = fields.Monetary(string='Total Balance', compute='_compute_totals', currency_field='currency_id', store=True)
    total_interest_paid = fields.Monetary(string='Total Interest Paid', compute='_compute_totals', currency_field='currency_id', store=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    vehicle_count = fields.Integer(string='Vehicles', compute='_compute_vehicle_count')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    @api.depends('line_ids.financed_amount', 'line_ids.current_balance', 'line_ids.accumulated_interest')
    def _compute_totals(self):
        for record in self:
            record.total_financed_amount = sum(record.line_ids.mapped('financed_amount'))
            record.total_balance = sum(record.line_ids.mapped('current_balance'))
            record.total_interest_paid = sum(record.line_ids.mapped('accumulated_interest'))

    def _compute_vehicle_count(self):
        for record in self:
            record.vehicle_count = len(record.line_ids)

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

    def action_activate(self):
        self.write({'state': 'active'})
        for line in self.line_ids:
            line.state = 'active'

    def action_close(self):
        self.write({'state': 'closed'})
        for line in self.line_ids:
            line.state = 'paid_off'

    @api.model
    def migrate_old_data(self):
        """Migrate data from product.template to financing.agreement"""
        # Find all products with financing
        products = self.env['product.template'].search([('financing_type', '!=', 'none')])
        Agreement = self.env['financing.agreement']
        AgreementLine = self.env['financing.agreement.line']
        
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

    @api.depends('interest_bill_ids.interest_amount', 'interest_bill_ids.state')
    def _compute_accumulated_interest(self):
        for record in self:
            # Sum all posted interest bills
            posted_bills = record.interest_bill_ids.filtered(lambda b: b.state == 'posted')
            record.accumulated_interest = sum(posted_bills.mapped('interest_amount'))

    @api.depends('vehicle_id')
    def _compute_name(self):
        for record in self:
            record.name = f"{record.agreement_id.name} - {record.vehicle_id.name}"
