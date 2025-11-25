from odoo import api, fields, models

class ProductProduct(models.Model):
    _inherit = 'product.product'

    # This field aggregates the total number of units reserved by *all* active reservations.
    reserved_qty = fields.Float(
        string='Reserved Quantity',
        compute='_compute_reserved_qty',
        store=True,
        help="Total units of this product variant reserved by active car reservation records."
    )

    @api.depends('car_reservation_ids.state', 'car_reservation_ids.qty_reserved')
    def _compute_reserved_qty(self):
        """ Sums up reserved quantities across multiple active reservation records. """
        for product in self:
            domain = [
                ('product_id', '=', product.id),
                ('state', '=', 'reserved'),
            ]
            reservations = self.env['car.reservation'].search(domain)
            # This sum is crucial for calculating the true available stock
            product.reserved_qty = sum(reservations.mapped('qty_reserved'))

    # Link reservations back to the product (for dependency tracking)
    car_reservation_ids = fields.One2many(
        'car.reservation',
        'product_id',
        string='Active Reservations',
    )