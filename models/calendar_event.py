from odoo import fields, models

class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    physical_product_id = fields.Many2one('product.product', string="Reserved Vehicle")