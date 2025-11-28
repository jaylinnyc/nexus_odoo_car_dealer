from odoo import fields, models

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    make = fields.Char(string='Make')
    model = fields.Char(string='Model')
    year = fields.Integer(string='Year')
    vin = fields.Char(string='VIN')
    mileage = fields.Float(string='Mileage')