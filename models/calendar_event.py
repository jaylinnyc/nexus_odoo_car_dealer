from odoo import fields, models

import logging

_logger = logging.getLogger(__name__)

class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    physical_product_id = fields.Many2one('product.product', string="Reserved Vehicle")
    
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Reservation Order',
        compute='_compute_sale_order_id',
        store=True,
        readonly=True
    )

    def _compute_sale_order_id(self):
        for event in self:
            _logger.info("Computing sale_order_id for Calendar Event ID %s", event.sale_order_line_ids)
            # event.sale_order_id = event.sale_order_line_ids and event.sale_order_line_ids[0].order_id or False
            sale_order_line = event.sale_order_line_ids[:1]
            event.sale_order_id = sale_order_line.order_id if sale_order_line else False
            _logger.info("Sale order lines linked to this event: %s", event.sale_order_id)
            
    def action_confirm_reservation_and_unpublish_product(self):
        """
        Confirms the reservation and reduces the vehicle from stock.
        """
        self.ensure_one()
        product = self.physical_product_id
        _logger.info("Confirming reservation and unpublishing product ID %s", product.id)
        

        if not product:
            _logger.warning("No physical product linked to Calendar Event ID %s", self.id)
            return
        
        product.product_tmpl_id.sudo().write({'website_published': False})
        self.message_post(body=f"Vehicle **{product.display_name}** successfully reserved and **unpublished** from the website.")
