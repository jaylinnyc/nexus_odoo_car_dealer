from odoo import http
from odoo.http import request
import json

class ProductController(http.Controller):
    @http.route('/api/products', type='json', auth='public')
    def get_products_data(self, **kw):
        cars = request.env['product.template'].sudo().search_read(
            [('is_published', '=', True)],
            ['name', 'list_price', 'categ_id', 'description_sale', 'website_ribbon_id', 'qty_available'],
            order='name asc'
        )

        for car in cars:
            car['is_sold_out'] = car.get('qty_available', 0) <= 0
        return cars

    @http.route('/api/product/<int:product_id>', type='json', auth='public')
    def get_product_detail_data(self, product_id, **kw):
        # Fetch detailed information for one product
        product = request.env['product.template'].sudo().search_read(
            [('id', '=', product_id)],
            ['name', 'list_price', 'description_sale', 'description', 'currency_id', 'image_1920', 'qty_available'],
            limit=1
        )
        if product:
            return product[0]
        return {}