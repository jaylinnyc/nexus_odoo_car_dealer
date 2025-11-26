from odoo import http
from odoo.http import request

class PageController(http.Controller):
    @http.route('/inventory', type='http', auth='public', website=True)
    def render_inventory_page(self, **kw):
        return request.render('car_store.inventory', {})

    @http.route('/inventory/<int:product_id>', type='http', auth='public', website=True)
    def render_product_page(self, product_id):
        values = {
            'product_id': product_id,
        }
        return request.render('car_store.product', values)