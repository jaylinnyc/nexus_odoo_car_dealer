from odoo import fields, models

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
            sale_order = self.env['sale.order'].search([('calendar_event_id', '=', event.id)], limit=1)
            event.sale_order_id = sale_order.id if sale_order else False
            
    def action_confirm_reservation_and_reduce_stock(self):
        """
        Confirms the reservation and reduces the vehicle from stock.
        """
        self.ensure_one()
        product = self.physical_product_id
        
        # 1. Validation (Clean Code)
        if not product:
            # Not a vehicle reservation or product not set.
            return
        
        product.product_tmpl_id.sudo().write({'website_published': False})
        self.message_post(body=f"Vehicle **{product.display_name}** successfully reserved and **unpublished** from the website.")
