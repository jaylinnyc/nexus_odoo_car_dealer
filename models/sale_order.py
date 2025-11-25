from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    first_order_line_id = fields.Many2one(
        'sale.order.line',
        string='First Order Line',
        compute='_compute_first_order_line',
        store=True,          # Important: stored so you can use it in domains, Sign, etc.
        readonly=True,
    )

    @api.depends('order_line.sequence', 'order_line.id')
    def _compute_first_order_line(self):
        for order in self:
            if order.order_line:
                # First line according to sequence (same order as form view)
                first_line = order.order_line.sorted('sequence')[:1]
                order.first_order_line_id = first_line
            else:
                order.first_order_line_id = False