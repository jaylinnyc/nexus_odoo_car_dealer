from odoo import http
from odoo.http import request


class ContactController(http.Controller):

    @http.route(
        '/reservation',
        type='http',
        auth='public',
        website=True,
        methods=['GET'],
        sitemap=False
    )
    def render_reservation_form(self, product_id=None, **post):



        countries = request.env['res.country'].sudo().search([])

        render_values = {
            'countries': countries,
            'error': {},  # To hold validation errors
            'partner': {},
            'product_id': product_id # To hold submitted values in case of error
        }

        return request.render('car_store.contact_form_template', render_values)

    @http.route(
        '/reservation/create_contact',
        type='http',
        auth='public',
        website=True,
        methods=['POST'],
        csrf=True  # Essential for security on POST requests
    )
    def create_customer_contact(self, **post):
        """ Processes the form submission and creates a new res.partner record. """

        # Data validation should ideally happen here.

        try:
            # 2. Extract and Process Data from POST
            name = post.get('partner_name')
            email = post.get('email')
            phone = post.get('phone')
            # Optional: Address fields
            country_id = int(post.get('country_id', 0)) if post.get('country_id') else False

            product_id = post.get('product_id')

            # 3. Create the res.partner record (Customer)
            new_partner = request.env['res.partner'].sudo().create({
                'name': name,
                'email': email,
                'phone': phone,
                'country_id': country_id,
                'is_company': False,  # Creating an individual contact
                'customer_rank': 1,  # Marks them as a customer
            })

            # --- 2. Sales Order (SO) Creation ---
            try:
                # 2a. Fetch required records
                product = request.env['product.product'].sudo().search([('product_tmpl_id', '=', product_id)],
                                                                       limit=1)

                if not product:
                    # UX: Redirect if product is not found
                    return request.redirect('/shop/cart?error=ProductNotFound')

                # 2b. Prepare SO values
                order_values = {
                    'partner_id': new_partner.id,
                    'partner_invoice_id': new_partner.id,
                    'partner_shipping_id': new_partner.id,
                    'pricelist_id': request.website.get_current_website().default_pricelist_id.id,
                    'website_id': request.website.id,
                    'order_line': [(0, 0, {  # (0, 0, VALUES) creates a new line
                        'product_template_id': product.product_tmpl_id,
                        'product_uom_qty': 1,  # One car reservation
                        'price_unit': product.list_price,# Use list price as base
                    })]
                }

                # 2c. Create the Sales Order
                new_so = request.env['sale.order'].sudo().create(order_values)

                # The sales order must be computed to get accurate totals/taxes
                new_so.action_confirm()  # Optional: Confirm the order immediately

            except Exception as e:
                request.env.cr.rollback()
                # UX: Handle errors specific to SO creation
                return request.redirect('/reservation?error=OrderCreationFailed')

            # 4. Success: Redirect to the next step (e.g., payment, confirmation)
            request.session['sale_order_id'] = new_so.id
            return request.redirect('/shop/payment')

        except Exception as e:
            # 5. Error: Log and Re-render the form with error messages
            # For UX, you should catch specific validation errors and provide user feedback.
            request.env.cr.rollback()  # Rollback any failed transaction

            countries = request.env['res.country'].sudo().search([])

            # Re-render the form, preserving user input and showing an error
            return request.render('reservation_module.contact_form_template', {
                'error': {'general': "An error occurred while creating the contact."},
                'partner': post,  # Pass submitted data back for persistence
                'countries': countries,
            })