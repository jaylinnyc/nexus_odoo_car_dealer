from odoo import api, fields, models, _
from odoo.exceptions import UserError
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
        readonly=True
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
            bill_date = self.last_interest_bill_date + relativedelta(months=1)
        elif self.financing_start_date:
            bill_date = self.financing_start_date
        else:
            raise UserError(_('Please set a financing start date.'))
        
        return self._create_interest_bill(bill_date)

    def action_generate_backdated_bills(self):
        """Open wizard to generate multiple backdated interest bills."""
        self.ensure_one()
        
        return {
            'name': _('Generate Backdated Interest Bills'),
            'type': 'ir.actions.act_window',
            'res_model': 'vehicle.financing.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_id': self.id,
            }
        }

    def _create_interest_bill(self, bill_date):
        """Create an interest bill for the given date."""
        self.ensure_one()
        
        # Calculate monthly interest (simple interest: Principal * Rate / 12)
        monthly_interest = (self.financing_amount * self.financing_rate / 100) / 12
        
        # Try to find the best matching expense account for interest
        # Priority: 1) Interest expense, 2) Financial costs, 3) Any expense account
        account = self.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('company_id', '=', self.env.company.id),
            '|', '|',
            ('code', 'ilike', 'interest'),
            ('name', 'ilike', 'interest'),
            ('name', 'ilike', 'financial')
        ], limit=1)
        
        # Fallback to any expense account
        if not account:
            account = self.env['account.account'].search([
                ('account_type', '=', 'expense'),
                ('company_id', '=', self.env.company.id),
            ], limit=1)
        
        if not account:
            raise UserError(_('Please configure at least one expense account in your chart of accounts.'))
        
        # Prepare analytic distribution
        analytic_dist = {str(self.analytic_account_id.id): 100.0} if self.analytic_account_id else {}
        
        # Create vendor bill
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.financing_partner_id.id,
            'invoice_date': bill_date,
            'date': bill_date,
            'invoice_line_ids': [(0, 0, {
                'name': _('Interest charge for %s - %s') % (
                    self.name,
                    bill_date.strftime('%B %Y')
                ),
                'quantity': 1,
                'price_unit': monthly_interest,
                'account_id': account.id,
                'analytic_distribution': analytic_dist or False,
            })],
        }
        
        bill = self.env['account.move'].create(bill_vals)
        
        # Auto-confirm the bill
        bill.action_post()
        
        # Create financing record
        financing_record = self.env['vehicle.financing'].create({
            'product_id': self.id,
            'bill_date': bill_date,
            'interest_amount': monthly_interest,
            'bill_id': bill.id,
        })
        
        # Update last bill date
        self.last_interest_bill_date = bill_date
        
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
