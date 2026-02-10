from odoo import api, fields, models, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    make = fields.Char(string='Make')
    model = fields.Char(string='Model')
    year = fields.Char(string='Year', size=4)  # Char to avoid numeric formatting (2,025)
    vin = fields.Char(string='VIN')
    mileage = fields.Integer(string='Mileage')  # Integer to avoid decimal display
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        help='Analytic account for tracking all costs related to this vehicle',
        copy=False,
        readonly=True,
    )
    
    # Reservation status for vehicles (only for tracking reservations via appointment booking)
    reservation_status = fields.Selection([
        ('available', 'Available'),
        ('reserved', 'Reserved'),
    ], string='Reservation Status', default='available', tracking=True,
       help='Tracks if vehicle is reserved via appointment. Sold/Out of Stock is handled by Odoo inventory.')
    
    reserved_by_partner_id = fields.Many2one(
        'res.partner',
        string='Reserved By',
        help='Customer who has reserved this vehicle',
        tracking=True,
    )
    
    reserved_by_dealer_id = fields.Many2one(
        'res.partner',
        string='Reserved By Dealer',
        help='Dealer who has reserved this vehicle',
        tracking=True,
    )
    
    reservation_date = fields.Datetime(
        string='Reservation Date',
        help='Date and time when the vehicle was reserved',
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
    financing_dealer_id = fields.Many2one(
        'res.partner',
        string='Financing Dealer',
        copy=False,
        help='Dealer responsible for the financing agreement (for internal tracking)'
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
        string='Interest Payable Account',
        domain="[('account_type', '=', 'liability_payable')]",
        copy=False,
        default=lambda self: self.env.ref('nexus_odoo_car_dealer.account_interest_payable', raise_if_not_found=False),
        help='Liability account for unpaid interest charges. This tracks interest owed to the financing partner.'
    )
    financing_liability_account_id = fields.Many2one(
        'account.account',
        string='Floor Plan Payable Account',
        domain="[('account_type', 'in', ['liability_current', 'liability_non_current', 'liability_payable'])]",
        copy=False,
        default=lambda self: self.env.ref('nexus_odoo_car_dealer.account_floor_plan_payable', raise_if_not_found=False),
        help='Liability account for floor plan financing. This account tracks the amount owed to the financing partner.'
    )
    financing_balance = fields.Monetary(
        string='Floor Plan Balance',
        currency_field='currency_id',
        copy=False,
        readonly=True,
        help='Current outstanding balance on the floor plan loan'
    )
    financing_journal_entry_id = fields.Many2one(
        'account.move',
        string='Financing Journal Entry',
        copy=False,
        readonly=True,
        help='Journal entry that recorded the floor plan financing'
    )
    has_purchase_order = fields.Boolean(
        string='Has Purchase Order',
        compute='_compute_has_purchase_order',
        store=False,
        help='Whether this product has a confirmed purchase order'
    )
    has_vendor_bill = fields.Boolean(
        string='Has Vendor Bill',
        compute='_compute_vendor_bill_info',
        store=False,
        help='Whether this product has a posted vendor bill'
    )
    vendor_bill_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
        compute='_compute_vendor_bill_info',
        store=False,
        help='The vendor bill for this vehicle purchase'
    )
    vendor_bill_ids = fields.Many2many(
        'account.move',
        string='All Vendor Bills',
        compute='_compute_vendor_bill_info',
        store=False,
        help='All vendor bills related to this vehicle (including landed costs)'
    )
    vendor_bill_amount = fields.Monetary(
        string='Vendor Bill Amount',
        currency_field='currency_id',
        compute='_compute_vendor_bill_info',
        store=False,
        help='Total amount of the vendor bill'
    )
    vendor_bill_amount_residual = fields.Monetary(
        string='Amount Due',
        currency_field='currency_id',
        compute='_compute_vendor_bill_info',
        store=False,
        help='Outstanding amount on the vendor bill'
    )
    total_bills_amount = fields.Monetary(
        string='Total Bills Amount',
        currency_field='currency_id',
        compute='_compute_vendor_bill_info',
        store=False,
        help='Total amount of all bills including landed costs'
    )
    total_bills_residual = fields.Monetary(
        string='Total Amount Due',
        currency_field='currency_id',
        compute='_compute_vendor_bill_info',
        store=False,
        help='Total outstanding amount on all bills'
    )
    financing_agreement_count = fields.Integer(compute='_compute_financing_agreement_count', string='Agreements')

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

    @api.depends('product_variant_ids')
    def _compute_vendor_bill_info(self):
        """Find and display vendor bill information for this vehicle"""
        for product in self:
            # Find purchase order lines for this product
            po_lines = self.env['purchase.order.line'].search([
                ('product_id', 'in', product.product_variant_ids.ids),
                ('order_id.state', 'in', ['purchase', 'done'])
            ], limit=1)
            
            if po_lines:
                # Find all vendor bills associated with this purchase (including landed costs)
                all_bills = self.env['account.move'].search([
                    ('move_type', '=', 'in_invoice'),
                    ('state', '=', 'posted'),
                    ('line_ids.purchase_line_id', 'in', po_lines.ids)
                ])
                
                # Also find landed cost bills for this purchase order
                landed_costs = self.env['stock.landed.cost'].search([
                    ('picking_ids.purchase_id', '=', po_lines.order_id.id),
                    ('state', '=', 'done')
                ])
                if landed_costs:
                    landed_cost_bills = landed_costs.mapped('vendor_bill_id').filtered(
                        lambda b: b.state == 'posted'
                    )
                    all_bills = all_bills | landed_cost_bills
                
                # Get the main vendor bill (from the supplier)
                vendor_bill = all_bills.filtered(
                    lambda b: b.partner_id == po_lines.order_id.partner_id
                )[:1]
                
                if all_bills:
                    product.has_vendor_bill = True
                    product.vendor_bill_id = vendor_bill.id if vendor_bill else all_bills[0].id
                    product.vendor_bill_ids = all_bills.ids
                    product.vendor_bill_amount = vendor_bill.amount_total if vendor_bill else 0
                    product.vendor_bill_amount_residual = vendor_bill.amount_residual if vendor_bill else 0
                    product.total_bills_amount = sum(all_bills.mapped('amount_total'))
                    product.total_bills_residual = sum(all_bills.mapped('amount_residual'))
                else:
                    product.has_vendor_bill = False
                    product.vendor_bill_id = False
                    product.vendor_bill_ids = False
                    product.vendor_bill_amount = 0
                    product.vendor_bill_amount_residual = 0
                    product.total_bills_amount = 0
                    product.total_bills_residual = 0
            else:
                product.has_vendor_bill = False
                product.vendor_bill_id = False
                product.vendor_bill_ids = False
                product.vendor_bill_amount = 0
                product.vendor_bill_amount_residual = 0
                product.total_bills_amount = 0
                product.total_bills_residual = 0

    def _compute_financing_agreement_count(self):
        for record in self:
            record.financing_agreement_count = self.env['financing.agreement.line'].search_count([('vehicle_id', '=', record.id)])

    def action_view_financing_agreements(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('nexus_odoo_car_dealer.action_financing_agreement_line')
        action['domain'] = [('vehicle_id', '=', self.id)]
        action['context'] = {'default_vehicle_id': self.id}
        return action

    @api.onchange('year', 'make', 'model', 'categ_id')
    def _onchange_vehicle_details(self):
        """Auto-update product name when year, make, or model changes for vehicles"""
        if self.categ_id and self.categ_id.name == 'Vehicles':
            if self.year and self.make and self.model:
                self.name = f"{self.year} {self.make} {self.model}"

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to automatically set internal reference from VIN and product name from vehicle details"""
        for vals in vals_list:
            if vals.get('vin') and not vals.get('default_code'):
                vals['default_code'] = vals['vin']
            
            # Auto-set product name for vehicles: [year] [make] [model]
            if not vals.get('name'):
                categ_id = vals.get('categ_id')
                if categ_id:
                    category = self.env['product.category'].browse(categ_id)
                    if category.name == 'Vehicles':
                        year = vals.get('year')
                        make = vals.get('make')
                        model = vals.get('model')
                        if year and make and model:
                            vals['name'] = f"{year} {make} {model}"
        
        return super(ProductTemplate, self).create(vals_list)

    def write(self, vals):
        """Override write to automatically set internal reference from VIN"""
        if vals.get('vin') and not vals.get('default_code'):
            vals['default_code'] = vals['vin']
        return super(ProductTemplate, self).write(vals)

    def action_unreserve_vehicle(self):
        """Remove reservation from a vehicle, making it available again."""
        self.ensure_one()
        
        if self.qty_available <= 0:
            raise models.ValidationError(_('Cannot unreserve a vehicle that has been sold (out of stock).'))
        
        if self.reservation_status != 'reserved':
            raise models.ValidationError(_('This vehicle is not currently reserved.'))
        
        # Store info for the log message
        previous_customer = self.reserved_by_partner_id.name if self.reserved_by_partner_id else 'Unknown'
        
        # Clear reservation
        self.write({
            'reservation_status': 'available',
            'reserved_by_partner_id': False,
            'reservation_date': False,
        })
        
        # Re-publish on website if it was unpublished
        if hasattr(self, 'is_published') and not self.is_published:
            self.is_published = True
        
        # Post message to chatter
        self.message_post(
            body=_('Vehicle reservation removed. Previously reserved by: %s. Vehicle is now available for sale.') % previous_customer,
            subject=_('Reservation Cancelled')
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reservation Removed'),
                'message': _('Vehicle %s is now available for sale.') % self.display_name,
                'type': 'success',
                'sticky': False,
            }
        }