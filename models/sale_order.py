from odoo import models, fields, api
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
        This links the reserved vehicle to the cart line and adds vehicle details to description.
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
                # Enhance the line description with detailed vehicle info
                vehicle = booking_sudo.vehicle_template_id
                vehicle_details = []
                vehicle_details.append(f"Reserved Vehicle: {vehicle.display_name}")
                if vehicle.vin:
                    vehicle_details.append(f"VIN: {vehicle.vin}")
                if vehicle.year and vehicle.make and vehicle.model:
                    vehicle_details.append(f"Year/Make/Model: {vehicle.year} {vehicle.make} {vehicle.model}")
                if vehicle.list_price:
                    vehicle_details.append(f"Vehicle Price: ${vehicle.list_price:,.2f}")
                
                vehicle_info = "\n" + "\n".join(vehicle_details)
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
        
        # Mark vehicle financing as paid off when sold
        for line in self.order_line:
            if line.product_template_id.financing_status == 'active':
                line.product_template_id.financing_status = 'paid_off'
                _logger.info(
                    "Financing marked as paid off for vehicle %s (Sale Order %s)", 
                    line.product_template_id.name,
                    self.name
                )
            
        return res

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
