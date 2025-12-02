from odoo import models, fields, api
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
                

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        _logger.info("Sale Order %s confirmed. Checking for vehicle reservation appointments.", self.id)
        appointment = self.env['calendar.event'].search([
            ('sale_order_id', '=', self.id), 
            ('physical_product_id', '!=', False) # Filter for vehicle reservations
        ], limit=1)
        if appointment:
            appointment.action_confirm_reservation_and_unpublish_product()
            _logger.info(
                    "Vehicle reservation successfully confirmed and product (ID: %s) unpublished for Sale Order %s.", 
                    appointment.physical_product_id.id,
                    self.name
                )
        else:
            _logger.info("No vehicle reservation appointment found for Sale Order ID %s", self.id)
            
        return res