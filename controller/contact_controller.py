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
    def render_reservation_form(self, **post):
        """ Renders the customer contact creation form. """

        # 1. Prepare Data for Rendering (if any, e.g., default values)
        # In a real scenario, you might fetch available car models or states/countries here.
        # Example: Fetching available countries for the address dropdown
        countries = request.env['res.country'].sudo().search([])

        render_values = {
            'countries': countries,
            'error': {},  # To hold validation errors
            'partner': {},  # To hold submitted values in case of error
        }

        return request.render('nexus_odoo_car_dealer.contact_form_template', render_values)

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

            # 3. Create the res.partner record (Customer)
            new_partner = request.env['res.partner'].sudo().create({
                'name': name,
                'email': email,
                'phone': phone,
                'country_id': country_id,
                'is_company': False,  # Creating an individual contact
                'customer_rank': 1,  # Marks them as a customer
            })

            # 4. Success: Redirect to the next step (e.g., payment, confirmation)
            return request.redirect(f'/reservation/thank-you?partner_id={new_partner.id}')

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