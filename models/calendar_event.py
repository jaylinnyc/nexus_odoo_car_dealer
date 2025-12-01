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
            event.sale_order_id = event.sale_order_line_ids and event.sale_order_line_ids[0].order_id or False
            
    def action_confirm_reservation_and_reduce_stock(self):
        """
        Confirms the reservation and reduces the vehicle from stock.
        """
        self.ensure_one()
        product = self.physical_product_id

        if not product:
            return
        
        product.product_tmpl_id.sudo().write({'website_published': False})
        self.message_post(body=f"Vehicle **{product.display_name}** successfully reserved and **unpublished** from the website.")
