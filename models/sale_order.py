from odoo import models, fields, api, _
from odoo.exceptions import UserError
from markupsafe import Markup
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    first_order_line_id = fields.Many2one(
        'sale.order.line',
        string='First Order Line',
        compute='_compute_first_order_line',
        store=True,          # Important: stored so you can use it in domains, Sign, etc.
        readonly=True,
    )
    
    # just a regular Many2one to product
    linked_car = fields.Many2one(
        'product.product',
        string='Linked Car',
        domain="[('categ_id.name', '=', 'Vehicles')]",  # or whatever makes sense for cars
        help="Car linked to this sales order (used for subscription/storage)",
        tracking=True,  # optional: shows changes in chatter
    )

    @api.depends('order_line.sequence')
    def _compute_first_order_line(self):
        for order in self:
            if order.order_line:
                # First line according to sequence (same order as form view)
                first_line = order.order_line.sorted('sequence')[:1]
                order.first_order_line_id = first_line
            else:
                order.first_order_line_id = False

    def _prepare_order_line_values(self, *args, calendar_booking_id=False, calendar_booking_tz=False, **kwargs):
        """
        Override to add reservation_vehicle_id from calendar.booking to the SOL.
        This links the reserved vehicle to the cart line.
        """
        values = super()._prepare_order_line_values(
            *args,
            calendar_booking_id=calendar_booking_id,
            calendar_booking_tz=calendar_booking_tz,
            **kwargs,
        )
        
        if calendar_booking_id:
            booking_sudo = self.env['calendar.booking'].sudo().browse(calendar_booking_id)
            if booking_sudo.vehicle_template_id:
                values['reservation_vehicle_id'] = booking_sudo.vehicle_template_id.id
                # Enhance the line description with vehicle info
                vehicle = booking_sudo.vehicle_template_id
                vehicle_info = f"\nVehicle: {vehicle.display_name}"
                if values.get('name'):
                    values['name'] = values['name'] + vehicle_info
                _logger.info("Linked vehicle %s to SOL for booking %s", vehicle.display_name, booking_sudo.id)
        
        return values
                

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        _logger.info("Sale Order %s confirmed. Checking for vehicle reservation appointments.", self.id)
        appointment = self.env['calendar.event'].search([
            ('sale_order_line_ids', 'in', self.order_line.ids), 
        ], limit=1)
        
        if appointment:
            appointment.action_confirm_reservation_and_unpublish_product()
            _logger.info(
                    "Vehicle reservation successfully confirmed and vehicle (ID: %s) unpublished for Sale Order %s.", 
                    appointment.vehicle_template_id.id if appointment.vehicle_template_id else 'None',
                    self.name
                )
        else:
            _logger.info("No vehicle reservation appointment found for Sale Order ID %s", self.id)
        
        # Process each vehicle line for financing and consignment
        for line in self.order_line:
            product = line.product_template_id
            
            # Mark vehicle financing as paid off when sold
            if product.financing_status == 'active':
                product.financing_status = 'paid_off'
                _logger.info(
                    "Financing marked as paid off for vehicle %s (Sale Order %s)", 
                    product.name,
                    self.name
                )
            
            # Handle consignment sale - create accounting entries
            if product.is_consignment and product.consignment_status == 'active':
                self._process_consignment_sale(line)
            
        return res

    def _process_consignment_sale(self, sale_line):
        """
        Process accounting for consignment vehicle sale.
        
        Agent Model Accounting:
        - The dealer acts as an agent, not taking ownership of inventory
        - On sale, we record:
            - Full sale amount as revenue (will be offset)
            - Amount owed to consignor as liability
            - Dealer commission as income
        
        Journal Entry (when vehicle sells):
            Dr. Accounts Receivable (Customer)     $50,000
               Cr. Consignment Payable (Consignor)            $45,000  
               Cr. Commission Income                           $5,000
        """
        product = sale_line.product_template_id
        sale_price = sale_line.price_unit * sale_line.product_uom_qty
        
        # Calculate commission based on type
        if product.consignment_commission_type == 'percentage':
            commission = sale_price * (product.consignment_commission_rate / 100.0)
        else:
            commission = product.consignment_commission_amount or 0.0
        
        amount_owed = sale_price - commission
        
        # Get required accounts
        consignment_payable = product.consignment_payable_account_id
        if not consignment_payable:
            consignment_payable = self.env.ref(
                'nexus_odoo_car_dealer.account_consignment_payable', 
                raise_if_not_found=False
            )
        
        commission_account = product.consignment_commission_account_id
        if not commission_account:
            commission_account = self.env.ref(
                'nexus_odoo_car_dealer.account_consignment_commission_income', 
                raise_if_not_found=False
            )
        
        if not consignment_payable:
            raise UserError(_('Please configure the Consignment Payable account for vehicle %s') % product.name)
        
        if not commission_account:
            raise UserError(_('Please configure the Commission Income account for vehicle %s') % product.name)
        
        if not product.consignor_id:
            raise UserError(_('Please set the Consignor for consignment vehicle %s') % product.name)
        
        # Get journal
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not journal:
            raise UserError(_('No general journal found. Please create one first.'))
        
        # Prepare analytic distribution
        analytic_dist = {str(product.analytic_account_id.id): 100.0} if product.analytic_account_id else {}
        
        # Create journal entry for consignment sale
        # This entry records the liability to consignor and commission income
        # Note: The AR debit is handled by the normal invoice creation
        # We only need to reclassify the revenue into:
        # - Consignment Payable (liability to consignor)
        # - Commission Income (our revenue)
        
        journal_entry_vals = {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'ref': _('Consignment Sale - %s - %s') % (product.name, self.name),
            'narration': Markup(
                '<b>Consignment Vehicle Sale</b><br/>'
                'Vehicle: %s<br/>'
                'Sale Order: %s<br/>'
                'Sale Price: %s<br/>'
                'Consignor: %s<br/>'
                'Amount Owed to Consignor: %s<br/>'
                'Dealer Commission: %s<br/>'
            ) % (
                product.name,
                self.name,
                sale_price,
                product.consignor_id.name,
                amount_owed,
                commission,
            ),
            'line_ids': [
                # Debit: Revenue (offset the income to reclassify it)
                # We'll use COGS or a clearing account approach
                # For simplicity, let's create entries that work with the invoice
                
                # Credit: Consignment Payable (liability to consignor)
                (0, 0, {
                    'name': _('Consignment payable - %s') % product.consignor_id.name,
                    'account_id': consignment_payable.id,
                    'partner_id': product.consignor_id.id,
                    'debit': 0,
                    'credit': amount_owed,
                    'analytic_distribution': analytic_dist or False,
                }),
                # Debit: COGS/Expense (represents cost of goods sold for consignment)
                (0, 0, {
                    'name': _('Consignment cost - %s') % product.name,
                    'account_id': product.property_account_expense_id.id or product.categ_id.property_account_expense_categ_id.id,
                    'debit': amount_owed,
                    'credit': 0,
                    'analytic_distribution': analytic_dist or False,
                }),
            ],
        }
        
        journal_entry = self.env['account.move'].create(journal_entry_vals)
        journal_entry.action_post()
        
        # Update product with sale information
        product.write({
            'consignment_status': 'sold',
            'consignment_sale_price': sale_price,
            'consignment_payment_status': 'pending',
            'reservation_status': 'sold',
        })
        
        # Post message to chatter
        product.message_post(
            body=Markup(
                '<b>Consignment Vehicle Sold</b><br/>'
                'Sale Order: <a href="/web#id=%s&model=sale.order">%s</a><br/>'
                'Sale Price: %s<br/>'
                'Commission Earned: %s<br/>'
                'Amount Owed to Consignor: %s<br/>'
                'Journal Entry: <a href="/web#id=%s&model=account.move">%s</a>'
            ) % (
                self.id, self.name,
                sale_price,
                commission,
                amount_owed,
                journal_entry.id, journal_entry.name,
            ),
            subject=_('Consignment Sale Completed')
        )
        
        _logger.info(
            "Consignment sale processed for vehicle %s (SO: %s). "
            "Amount owed to consignor: %s, Commission: %s",
            product.name, self.name, amount_owed, commission
        )

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    reservation_vehicle_id = fields.Many2one(
        'product.template',
        string="Reserved Vehicle",
        help="The vehicle being reserved through this appointment booking"
    )

    @api.onchange('product_id', 'price_unit')
    def _onchange_product_id_auto_tax(self):
        """Automatically set appropriate tax based on price threshold for vehicles."""
        if self.product_id and self.product_template_id.categ_id.name == 'Vehicles':
            # Get the tax records
            standard_tax = self.env.ref('nexus_odoo_car_dealer.account_tax_sales_635', raise_if_not_found=False)
            luxury_tax = self.env.ref('nexus_odoo_car_dealer.account_tax_sales_775', raise_if_not_found=False)
            
            if standard_tax and luxury_tax:
                # Apply luxury tax if price exceeds $50,000, otherwise standard tax
                if self.price_unit > 50000:
                    self.tax_ids = [(6, 0, [luxury_tax.id])]
                else:
                    self.tax_ids = [(6, 0, [standard_tax.id])]

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-apply tax on creation based on price."""
        lines = super().create(vals_list)
        for line in lines:
            if line.product_template_id.categ_id.name == 'Vehicles':
                standard_tax = self.env.ref('nexus_odoo_car_dealer.account_tax_sales_635', raise_if_not_found=False)
                luxury_tax = self.env.ref('nexus_odoo_car_dealer.account_tax_sales_775', raise_if_not_found=False)
                
                if standard_tax and luxury_tax:
                    if line.price_unit > 50000:
                        line.tax_ids = [(6, 0, [luxury_tax.id])]
                    else:
                        line.tax_ids = [(6, 0, [standard_tax.id])]
        return lines

    def write(self, vals):
        """Update tax when price changes."""
        res = super().write(vals)
        
        # If price_unit is being updated, recalculate tax
        if 'price_unit' in vals:
            for line in self:
                if line.product_template_id.categ_id.name == 'Vehicles':
                    standard_tax = self.env.ref('nexus_odoo_car_dealer.account_tax_sales_635', raise_if_not_found=False)
                    luxury_tax = self.env.ref('nexus_odoo_car_dealer.account_tax_sales_775', raise_if_not_found=False)
                    
                    if standard_tax and luxury_tax:
                        if line.price_unit > 50000:
                            line.tax_ids = [(6, 0, [luxury_tax.id])]
                        else:
                            line.tax_ids = [(6, 0, [standard_tax.id])]
        return res
