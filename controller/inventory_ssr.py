from odoo import http
from odoo.http import request

class Inventory(http.Controller):
    @http.route('/inventory', type='http', auth='public', website=True)
    def render_inventory_cars(self, **kw):
        cars = request.env['product.template'].sudo().search_read(
            [],
            ['name', 'list_price', 'categ_id', 'description_sale', 'website_ribbon_id'],
            order='name asc'
        )
        print(cars)
        values = {
            'cars': cars,
            'page_title': "Car Inventory",
        }

        return request.render('car_store.ssr_inventory', values)

    @http.route('/inventory/<int:product_id>', type='http', auth='public', website=True)
    def render_product_page_ssr(self, product_id):
        # Fetch the product data on the server
        ProductTemplate = request.env['product.template'].sudo()
        product = ProductTemplate.search_read(
            [('id', '=', product_id)],
            ['name', 'list_price', 'description_sale', 'description', 'currency_id', 'qty_available'],
            limit=1
        )

        # Handle 404 (Product not found)
        if not product:
            return request.render('website.404')

        # Pass the full product record to the SSR QWeb template
        values = {
            'product': product[0],  # Pass the dictionary containing all fields
            'price_formatted': f"${product[0]['list_price']:.2f}" ,
        }

        # Render the template 'car_store.product_ssr'
        return request.render('car_store.product_ssr', values)
