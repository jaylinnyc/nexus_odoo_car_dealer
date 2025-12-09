from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    make = fields.Char(string='Make')
    model = fields.Char(string='Model')
    year = fields.Integer(string='Year')
    vin = fields.Char(string='VIN')
    mileage = fields.Float(string='Mileage')
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        help='Analytic account for tracking all costs related to this vehicle',
        copy=False,
        readonly=True,
    )
    
    # Financing fields
    financing_type = fields.Selection([
        ('none', 'No Financing'),
        ('internal', 'Internal Financing'),
        ('external', 'External Financing'),
    ], string='Financing Type', default='none', copy=False)
    financing_amount = fields.Monetary(
        string='Financing Amount',
        currency_field='currency_id',
        copy=False,
        help='Original loan/financing amount (floor plan)'
    )
    financing_rate = fields.Float(
        string='Annual Interest Rate (%)',
        copy=False,
        help='Annual interest rate for financing'
    )
    financing_start_date = fields.Date(
        string='Financing Start Date',
        copy=False,
        help='Date when financing begins (defaults to PO confirmation date)'
    )
    financing_partner_id = fields.Many2one(
        'res.partner',
        string='Financing Partner',
        copy=False,
        help='Internal partner for financing (bank/lender for external reference only)'
    )
    financing_status = fields.Selection([
        ('active', 'Active'),
        ('paid_off', 'Paid Off'),
    ], string='Financing Status', default='active', copy=False)
    last_interest_bill_date = fields.Date(
        string='Last Interest Bill Date',
        copy=False,
        readonly=True,
        help='Date of the last generated interest bill'
    )
    financing_expense_account_id = fields.Many2one(
        'account.account',
        string='Interest Expense Account',
        domain="[('account_type', '=', 'expense')]",
        copy=False,
        default=lambda self: self.env.ref('nexus_odoo_car_dealer.account_interest_expense', raise_if_not_found=False),
        help='Account to use for recording interest expenses. If not set, will search for an interest expense account.'
    )
    has_purchase_order = fields.Boolean(
        string='Has Purchase Order',
        compute='_compute_has_purchase_order',
        store=False,
        help='Whether this product has a confirmed purchase order'
    )

    @api.depends('product_variant_ids')
    def _compute_has_purchase_order(self):
        """Check if product has any confirmed purchase orders"""
        for product in self:
            # Search for purchase order lines with this product
            po_lines = self.env['purchase.order.line'].search([
                ('product_id', 'in', product.product_variant_ids.ids),
                ('order_id.state', 'in', ['purchase', 'done'])
            ], limit=1)
            product.has_purchase_order = bool(po_lines)