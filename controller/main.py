from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class CarReservationController(http.Controller):
    # Deposit amount for reservation (can be set in system parameters later)
    RESERVATION_DEPOSIT = 500.00

    # Reservation holding period
    HOLDING_HOURS = 48

    @http.route('/car/reserve/init', type='json', auth='public', methods=['POST'], website=True)
    def init_reservation(self, product_id, **kw):
        # Ensure we have a valid product ID
        if not product_id:
            return {'error': _("No car model specified.")}

        Product = request.env['product.product'].sudo()
        product = Product.browse(int(product_id))

        # Check stock: True available stock = qty_available - reserved_qty
        # Since 'qty_available' includes reserved, we rely on the product model's reserved_qty
        available_for_sale = product.qty_available - product.reserved_qty

        if available_for_sale < 1.0:
            return {'error': _("This car is currently reserved by another customer.")}

        # 1. Determine Partner (Current User or Public placeholder)
        Partner = request.env.user.partner_id
        if Partner == request.env.ref('base.public_user'):
            # In a real scenario, you'd ask for contact info here.
            # For now, we use the public user as a temporary placeholder.
            pass

            # 2. Create the Draft Reservation
        try:
            reservation = request.env['car.reservation'].create({
                'product_id': product.id,
                'partner_id': Partner.id,
                'amount': self.RESERVATION_DEPOSIT,
                'qty_reserved': 1.0,  # Always 1 for car reservation
                'date_end': datetime.now() + timedelta(hours=self.HOLDING_HOURS),
                'state': 'pending_payment',  # Immediately moves to pending payment
            })
        except Exception as e:
            # Catch database errors
            return {'error': _("Failed to create reservation record: %s") % str(e)}

        # 3. Return data needed for the payment redirect
        return {
            'reservation_id': reservation.id,
            'deposit_amount': self.RESERVATION_DEPOSIT,
            'redirect_url': '/car/reserve/payment',
        }

    @http.route('/car/reserve/payment', type='http', auth='public', website=True)
    def start_reservation_payment(self, reservation_id, **kw):
        """
                Renders the payment selection page for the reservation deposit.
                """
        Reservation = request.env['car.reservation'].sudo()
        try:
            reservation = Reservation.browse(int(reservation_id))
        except:
            return request.render('website.404')  # Handle invalid ID

        # Ensure the reservation is still valid and pending payment
        if reservation.state not in ('draft', 'pending_payment'):
            return request.redirect('/shop')  # Or a custom error page

        # Determine the user/partner
        partner = request.env.user.partner_id
        if partner == request.env.ref('base.public_user'):
            # IMPORTANT: For production, you must redirect to a form
            # to collect name/email/address BEFORE payment to create a proper partner.
            # For simplicity now, we check the public user and redirect if necessary.
            pass

        # Prepare the transaction data
        tx_values = {
            'partner_id': partner.id,
            'amount': reservation.amount,
            'currency_id': request.website.currency_id.id,
            'reference': reservation.name,  # Use reservation ref as payment reference
            'custom_flow_identifier': reservation.name,  # Used later to link back to reservation
            'payment_type': 'form',
            # Link transaction back to the reservation model/ID
            'reservation_id': reservation.id,
            'reservation_model': 'car.reservation',
        }

        # Render the payment selection page (using standard Odoo templates)
        return request.render(
            'payment.acquirer_list',
            {
                'reservation': reservation,
                'acquirers': request.website.acquirer_ids(),  # Get all active acquirers
                'pms': request.env['payment.token'].sudo().search([('partner_id', '=', partner.id)]),
                'transaction_values': tx_values,
                'token_available': False,  # Assuming no tokens used for reservation deposit
                'mode': 'reservation',  # Custom mode to potentially adjust payment page appearance
                'amount': reservation.amount,
            }
        )
