from odoo import api, fields, models, _
from odoo.exceptions import UserError
from markupsafe import Markup


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
    
    # Reservation status for vehicles
    reservation_status = fields.Selection([
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('sold', 'Sold'),
    ], string='Reservation Status', default='available', tracking=True,
       help='Tracks the reservation status of the vehicle')
    
    reserved_by_partner_id = fields.Many2one(
        'res.partner',
        string='Reserved By',
        help='Customer who has reserved this vehicle',
        tracking=True,
    )
    
    reservation_date = fields.Datetime(
        string='Reservation Date',
        help='Date and time when the vehicle was reserved',
    )
    
    # ==========================================
    # Consignment Fields
    # ==========================================
    is_consignment = fields.Boolean(
        string='Consignment Vehicle',
        default=False,
        tracking=True,
        help='Check if this vehicle is on consignment from a third party'
    )
    consignor_id = fields.Many2one(
        'res.partner',
        string='Consignor (Vehicle Owner)',
        tracking=True,
        help='The owner of the vehicle who consigned it for sale'
    )
    consignment_agreement_date = fields.Date(
        string='Agreement Date',
        help='Date when the consignment agreement was signed'
    )
    consignment_commission_type = fields.Selection([
        ('percentage', 'Percentage of Sale'),
        ('fixed', 'Fixed Amount'),
    ], string='Commission Type', default='percentage',
       help='How the dealer commission is calculated')
    consignment_commission_rate = fields.Float(
        string='Commission Rate (%)',
        default=10.0,
        help='Percentage of sale price kept as dealer commission'
    )
    consignment_commission_amount = fields.Monetary(
        string='Fixed Commission',
        currency_field='currency_id',
        help='Fixed commission amount (used when Commission Type is Fixed)'
    )
    consignment_minimum_price = fields.Monetary(
        string='Minimum Sale Price',
        currency_field='currency_id',
        help='Minimum acceptable sale price agreed with consignor'
    )
    consignment_status = fields.Selection([
        ('active', 'Active'),
        ('sold', 'Sold'),
        ('returned', 'Returned to Owner'),
        ('expired', 'Agreement Expired'),
    ], string='Consignment Status', default='active', tracking=True)
    consignment_expiry_date = fields.Date(
        string='Agreement Expiry Date',
        help='Date when the consignment agreement expires'
    )
    consignment_notes = fields.Text(
        string='Consignment Notes',
        help='Additional notes about the consignment agreement'
    )
    
    # Consignment Accounting
    consignment_payable_account_id = fields.Many2one(
        'account.account',
        string='Consignment Payable Account',
        domain="[('account_type', 'in', ['liability_current', 'liability_non_current'])]",
        help='Liability account for amounts owed to consignor'
    )
    consignment_commission_account_id = fields.Many2one(
        'account.account',
        string='Commission Income Account',
        domain="[('account_type', 'in', ['income', 'income_other'])]",
        help='Income account for recording commission earned'
    )
    consignment_amount_owed = fields.Monetary(
        string='Amount Owed to Consignor',
        currency_field='currency_id',
        compute='_compute_consignment_amounts',
        store=True,
        help='Amount to be paid to the consignor after sale'
    )
    consignment_commission_earned = fields.Monetary(
        string='Commission Earned',
        currency_field='currency_id',
        compute='_compute_consignment_amounts',
        store=True,
        help='Dealer commission earned from the sale'
    )
    consignment_sale_price = fields.Monetary(
        string='Actual Sale Price',
        currency_field='currency_id',
        help='The actual price the vehicle was sold for'
    )
    consignment_payment_status = fields.Selection([
        ('not_sold', 'Not Sold Yet'),
        ('pending', 'Payment Pending'),
        ('partial', 'Partially Paid'),
        ('paid', 'Fully Paid'),
    ], string='Consignor Payment Status', default='not_sold', tracking=True)
    consignment_amount_paid = fields.Monetary(
        string='Amount Paid to Consignor',
        currency_field='currency_id',
        default=0.0,
        help='Total amount already paid to the consignor'
    )
    consignment_amount_remaining = fields.Monetary(
        string='Remaining Balance',
        currency_field='currency_id',
        compute='_compute_consignment_amounts',
        store=True,
        help='Remaining amount to be paid to the consignor'
    )
    
    @api.depends('consignment_sale_price', 'consignment_commission_type', 
                 'consignment_commission_rate', 'consignment_commission_amount',
                 'consignment_amount_paid')
    def _compute_consignment_amounts(self):
        for vehicle in self:
            if not vehicle.is_consignment or not vehicle.consignment_sale_price:
                vehicle.consignment_amount_owed = 0.0
                vehicle.consignment_commission_earned = 0.0
                vehicle.consignment_amount_remaining = 0.0
                continue
            
            sale_price = vehicle.consignment_sale_price
            if vehicle.consignment_commission_type == 'percentage':
                commission = sale_price * (vehicle.consignment_commission_rate / 100.0)
            else:
                commission = vehicle.consignment_commission_amount or 0.0
            
            vehicle.consignment_commission_earned = commission
            vehicle.consignment_amount_owed = sale_price - commission
            vehicle.consignment_amount_remaining = vehicle.consignment_amount_owed - vehicle.consignment_amount_paid
    
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
    financing_liability_account_id = fields.Many2one(
        'account.account',
        string='Floor Plan Payable Account',
        domain="[('account_type', 'in', ['liability_current', 'liability_non_current'])]",
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

    def action_pay_consignor(self):
        """Open wizard to pay the consignor for a sold consignment vehicle."""
        self.ensure_one()
        
        if not self.is_consignment:
            raise UserError(_('This vehicle is not a consignment vehicle.'))
        
        if self.consignment_status != 'sold':
            raise UserError(_('This vehicle has not been sold yet.'))
        
        if self.consignment_payment_status == 'paid':
            raise UserError(_('The consignor has already been fully paid for this vehicle.'))
        
        return {
            'name': _('Pay Consignor'),
            'type': 'ir.actions.act_window',
            'res_model': 'consignment.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_id': self.id,
            },
        }


class ConsignmentPaymentWizard(models.TransientModel):
    _name = 'consignment.payment.wizard'
    _description = 'Pay Consignor for Sold Vehicle'

    product_id = fields.Many2one(
        'product.template',
        string='Vehicle',
        required=True,
        readonly=True
    )
    consignor_id = fields.Many2one(
        'res.partner',
        string='Consignor',
        related='product_id.consignor_id',
        readonly=True
    )
    amount_owed = fields.Monetary(
        string='Total Amount Owed',
        currency_field='currency_id',
        compute='_compute_amounts',
        readonly=True
    )
    amount_paid = fields.Monetary(
        string='Already Paid',
        currency_field='currency_id',
        related='product_id.consignment_amount_paid',
        readonly=True
    )
    amount_remaining = fields.Monetary(
        string='Remaining Balance',
        currency_field='currency_id',
        compute='_compute_amounts',
        readonly=True
    )
    payment_amount = fields.Monetary(
        string='Payment Amount',
        currency_field='currency_id',
        required=True
    )
    is_full_payment = fields.Boolean(
        string='Full Payment',
        default=True,
        help='Check to pay the full remaining balance'
    )
    payment_date = fields.Date(
        string='Payment Date',
        required=True,
        default=fields.Date.today
    )
    payment_journal_id = fields.Many2one(
        'account.journal',
        string='Payment Journal',
        domain="[('type', 'in', ['bank', 'cash']), ('company_id', '=', company_id)]",
        required=True,
        help='Bank or cash journal to make the payment from'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        readonly=True
    )
    notes = fields.Text(string='Notes')

    @api.depends('product_id')
    def _compute_amounts(self):
        for wizard in self:
            if wizard.product_id:
                wizard.amount_owed = wizard.product_id.consignment_amount_owed
                wizard.amount_remaining = wizard.amount_owed - wizard.product_id.consignment_amount_paid
            else:
                wizard.amount_owed = 0
                wizard.amount_remaining = 0

    @api.onchange('is_full_payment', 'amount_remaining')
    def _onchange_is_full_payment(self):
        """Auto-populate payment amount when full payment is selected."""
        if self.is_full_payment:
            self.payment_amount = self.amount_remaining

    @api.onchange('payment_amount')
    def _onchange_payment_amount(self):
        """Update is_full_payment based on amount."""
        if self.payment_amount and self.amount_remaining:
            if abs(self.payment_amount - self.amount_remaining) < 0.01:
                self.is_full_payment = True
            elif self.is_full_payment:
                self.is_full_payment = False

    @api.constrains('payment_amount')
    def _check_payment_amount(self):
        for wizard in self:
            if wizard.payment_amount <= 0:
                raise UserError(_('Payment amount must be greater than zero.'))
            if wizard.payment_amount > wizard.amount_remaining:
                raise UserError(_(
                    'Payment amount ($%s) cannot exceed the remaining balance ($%s).'
                ) % (wizard.payment_amount, wizard.amount_remaining))

    def action_process_payment(self):
        """
        Process payment to consignor.
        
        Journal Entry:
            Dr. Consignment Payable    $45,000
               Cr. Bank/Cash                      $45,000
        """
        self.ensure_one()
        
        product = self.product_id
        
        # Get the consignment payable account
        consignment_payable = product.consignment_payable_account_id
        if not consignment_payable:
            consignment_payable = self.env.ref(
                'nexus_odoo_car_dealer.account_consignment_payable',
                raise_if_not_found=False
            )
        
        if not consignment_payable:
            raise UserError(_('Please configure the Consignment Payable account.'))
        
        # Get the bank/cash account
        bank_account = self.payment_journal_id.default_account_id
        if not bank_account:
            raise UserError(_('The selected payment journal does not have a default account configured.'))
        
        # Get general journal
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not journal:
            raise UserError(_('No general journal found.'))
        
        # Prepare analytic distribution
        analytic_dist = {str(product.analytic_account_id.id): 100.0} if product.analytic_account_id else {}
        
        # Create journal entry for payment
        journal_entry_vals = {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.payment_date,
            'ref': _('Consignment Payment - %s - %s') % (product.name, product.consignor_id.name),
            'narration': Markup(
                '<b>Consignment Payment to Owner</b><br/>'
                'Vehicle: %s<br/>'
                'Consignor: %s<br/>'
                'Payment Amount: %s<br/>'
                '%s'
            ) % (
                product.name,
                product.consignor_id.name,
                self.payment_amount,
                'Notes: ' + self.notes if self.notes else '',
            ),
            'line_ids': [
                # Debit: Consignment Payable (reduces liability)
                (0, 0, {
                    'name': _('Consignment payment - %s') % product.consignor_id.name,
                    'account_id': consignment_payable.id,
                    'partner_id': product.consignor_id.id,
                    'debit': self.payment_amount,
                    'credit': 0,
                    'analytic_distribution': analytic_dist or False,
                }),
                # Credit: Bank/Cash
                (0, 0, {
                    'name': _('Payment to consignor - %s') % product.name,
                    'account_id': bank_account.id,
                    'debit': 0,
                    'credit': self.payment_amount,
                    'analytic_distribution': analytic_dist or False,
                }),
            ],
        }
        
        journal_entry = self.env['account.move'].create(journal_entry_vals)
        journal_entry.action_post()
        
        # Update product payment tracking
        new_paid_amount = product.consignment_amount_paid + self.payment_amount
        new_remaining = product.consignment_amount_owed - new_paid_amount
        
        if new_remaining < 0.01:  # Fully paid (with small tolerance)
            payment_status = 'paid'
        else:
            payment_status = 'partial'
        
        product.write({
            'consignment_amount_paid': new_paid_amount,
            'consignment_payment_status': payment_status,
        })
        
        # Post message to chatter
        product.message_post(
            body=Markup(
                '<b>Consignment Payment Made</b><br/>'
                'Consignor: %s<br/>'
                'Payment Amount: %s<br/>'
                'Total Paid: %s<br/>'
                'Remaining Balance: %s<br/>'
                'Journal Entry: <a href="/web#id=%s&model=account.move">%s</a>'
            ) % (
                product.consignor_id.name,
                self.payment_amount,
                new_paid_amount,
                max(0, new_remaining),
                journal_entry.id, journal_entry.name,
            ),
            subject=_('Consignment Payment Processed')
        )
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': journal_entry.id,
            'view_mode': 'form',
            'target': 'current',
        }