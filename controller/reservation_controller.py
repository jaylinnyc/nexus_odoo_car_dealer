from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError
from datetime import datetime, timedelta

class ReservationController(http.Controller):
    @http.route('/reservation', auth='public', methods=['GET'], website=True)
    def init_reservation(self, product_id, **kw):
        print(product_id)
        if not product_id:
            return {'error': _("No car model specified.")}

        Product = request.env['product.product'].sudo()
        product = Product.browse(int(product_id))
        print(product)
        available_for_sale = product.qty_available - product.reserved_qty
        if available_for_sale < 1.0:
            return {'error': _("This car is currently reserved by another customer.")}