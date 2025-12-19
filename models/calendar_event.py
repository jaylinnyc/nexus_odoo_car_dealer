from odoo import api, fields, models

import logging

_logger = logging.getLogger(__name__)


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    vehicle_template_id = fields.Many2one(
        'product.template', 
        string="Reserved Vehicle",
        tracking=True,
        help="The vehicle (product template) being reserved through this appointment"
    )
    
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Reservation Order',
        compute='_compute_sale_order_id',
        store=True,
        readonly=True
    )

    @api.depends('sale_order_line_ids', 'sale_order_line_ids.order_id')
    def _compute_sale_order_id(self):
        for event in self:
            sale_order_line = event.sale_order_line_ids[:1]
            event.sale_order_id = sale_order_line.order_id if sale_order_line else False
            if event.sale_order_id:
                _logger.info("Calendar Event %s linked to Sale Order %s", event.id, event.sale_order_id.name)
            
    def action_confirm_reservation_and_unpublish_product(self):
        """
        Confirms the reservation and unpublishes the vehicle from website.
        """
        self.ensure_one()
        vehicle = self.vehicle_template_id
        
        if not vehicle:
            _logger.warning("No vehicle linked to Calendar Event ID %s", self.id)
            return
        
        _logger.info("Confirming reservation and unpublishing vehicle template ID %s", vehicle.id)
        vehicle.sudo().write({'website_published': False})
        self.message_post(body=f"Vehicle **{vehicle.display_name}** successfully reserved and **unpublished** from the website.")
