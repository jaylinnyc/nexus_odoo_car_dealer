from odoo import http
from odoo.http import request

class ReservationController(http.Controller):

    @http.route('/reservation/submit', type='http', auth='public', website=True, methods=['POST'])
    def submit_reservation(self, **post):
        # 1. Input Validation and Data Extraction
        name = post.get('name')
        email = post.get('email')
        phone = post.get('phone')
        comment = post.get('comment')
        product_id = int(post.get('product_id'))

        if not name or not email or not product_id:
            # Handle error gracefully (e.g., redirect back with an error message)
            return request.redirect("/product/detail/%s?error=missing_fields" % product_id)

        # 2. Create/Link Customer (res.partner)
        try:
            # Check if customer already exists by email
            partner = request.env['res.partner'].sudo().search([('email', '=', email)], limit=1)

            if not partner:
                # HIGHLIGHT: Create new customer (res.partner)
                partner = request.env['res.partner'].sudo().create({
                    'name': name,
                    'email': email,
                    'phone': phone,
                    'is_company': False,
                    'type': 'contact',
                })

            # 3. Create a Reservation/Sales Order (Optional but Recommended)
            # You might want to create a sales order or a dedicated reservation record here
            sale_order = request.env['sale.order'].sudo().create({
                'partner_id': partner.id,
                'partner_shipping_id': partner.id,  # HIGHLIGHT: Satisfies Odoo's address requirement
                'partner_invoice_id': partner.id,  # HIGHLIGHT: Satisfies Odoo's invoice requirement
                'order_line': [(0, 0, {
                    'product_id': product_id,
                    'product_uom_qty': 1,
                    # You might set a specific price or reservation deposit here
                })],
            })

            # Set the new order as the current active one (Odoo's standard cart/checkout process)
            request.session['sale_order_id'] = sale_order.id

            # 4. HIGHLIGHT: Navigate user to payment/checkout page
            return request.redirect("/shop/payment")

        except Exception as e:
            # Log error for developer review (performance and DX best practice)
            request.env.cr.rollback()
            request.env['ir.logging'].sudo().log(
                'Reservation Error', 'error', 'Error creating customer or order: %s' % str(e),
                dbname=request.env.cr.dbname, func='submit_reservation'
            )
            # Redirect back with a generic error
            return request.redirect("/product/detail/%s?error=submission_failed" % product_id)