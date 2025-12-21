from odoo import http
from odoo.http import request

# Import from appointment_account_payment since we're using paid appointments
# This inherits from AppointmentController but adds payment handling
try:
    from odoo.addons.appointment_account_payment.controllers.appointment import AppointmentAccountPayment as BaseController
except ImportError:
    from odoo.addons.appointment.controllers.appointment import AppointmentController as BaseController

import logging
_logger = logging.getLogger(__name__)


class WebsiteAppointmentExtended(BaseController):
    """
    Extend the appointment controller to pass vehicle template_id through the entire
    appointment booking flow and store it on the final calendar.event.
    """

    def _check_vehicle_already_in_cart(self, vehicle_template_id):
        """
        Check if the vehicle already has a pending reservation in the cart.
        Returns the existing SOL if found, False otherwise.
        """
        if not vehicle_template_id:
            return False
        
        try:
            # Get the current cart - try request.cart first (set by website_sale)
            # or fall back to fetching from session
            cart = getattr(request, 'cart', None)
            if not cart:
                # Try to get cart from session
                cart_id = request.session.get('website_sale_cart_id')
                if cart_id:
                    cart = request.env['sale.order'].sudo().browse(cart_id)
                    if not cart.exists():
                        cart = None
            
            if not cart:
                return False
            
            # Check if any SOL in cart has this vehicle
            existing_line = cart.order_line.filtered(
                lambda l: l.reservation_vehicle_id and l.reservation_vehicle_id.id == int(vehicle_template_id)
            )
            return existing_line[:1] if existing_line else False
        except Exception as e:
            _logger.warning("Error checking vehicle in cart: %s", e)
            return False

    def _check_vehicle_already_reserved(self, vehicle_template_id):
        """
        Check if the vehicle is already reserved or out of stock.
        Returns the vehicle if unavailable, False otherwise.
        """
        if not vehicle_template_id:
            return False
        
        vehicle = request.env['product.template'].sudo().browse(int(vehicle_template_id))
        if vehicle.exists():
            # Check reservation status or if out of stock
            if vehicle.reservation_status == 'reserved' or vehicle.qty_available <= 0:
                return vehicle
        return False

    def _check_vehicle_has_pending_booking(self, vehicle_template_id):
        """
        Check if the vehicle has a pending (unpaid) calendar.booking.
        Returns the existing booking if found, False otherwise.
        """
        if not vehicle_template_id:
            return False
        
        # Find bookings that haven't been converted to calendar events yet
        existing_booking = request.env['calendar.booking'].sudo().search([
            ('vehicle_template_id', '=', int(vehicle_template_id)),
            ('calendar_event_id', '=', False),  # Not yet converted to event
        ], limit=1)
        return existing_booking if existing_booking else False

    @http.route(['/appointment/<int:appointment_type_id>'], type='http', auth="public", website=True)
    def appointment_type_page(self, appointment_type_id, state=False, staff_user_id=False, resource_selected_id=False, **kwargs):
        """Override to pass vehicle_template_id into the appointment flow context."""
        vehicle_template_id = kwargs.get('vehicle_template_id')
        
        # Check if vehicle is already reserved or out of stock
        if vehicle_template_id:
            reserved_vehicle = self._check_vehicle_already_reserved(vehicle_template_id)
            if reserved_vehicle:
                status = 'out of stock' if reserved_vehicle.qty_available <= 0 else reserved_vehicle.reservation_status
                _logger.info("Vehicle %s is already %s, redirecting to product page", 
                           vehicle_template_id, status)
                return request.redirect(f'/shop/product/{reserved_vehicle.id}?vehicle_not_available=1')
        
        # Check if vehicle is already in cart - redirect to cart if so
        if vehicle_template_id:
            existing_line = self._check_vehicle_already_in_cart(vehicle_template_id)
            if existing_line:
                _logger.info("Vehicle %s already in cart (SOL %s), redirecting to cart", vehicle_template_id, existing_line.id)
                return request.redirect('/shop/cart?vehicle_already_in_cart=1')
        
        # Store vehicle_template_id in session so it persists through the multi-step flow
        if vehicle_template_id:
            request.session['vehicle_template_id'] = int(vehicle_template_id)
            _logger.info("Stored vehicle_template_id %s in session for appointment flow", vehicle_template_id)
        
        response = super().appointment_type_page(
            appointment_type_id, state=state, staff_user_id=staff_user_id, 
            resource_selected_id=resource_selected_id, **kwargs
        )
        
        # Add vehicle info to qcontext for display
        if hasattr(response, 'qcontext') and response.qcontext:
            vid = request.session.get('vehicle_template_id')
            if vid:
                vehicle = request.env['product.template'].sudo().browse(int(vid))
                if vehicle.exists():
                    response.qcontext['vehicle_template_id'] = vid
                    response.qcontext['vehicle_name'] = vehicle.display_name
                    response.qcontext['vehicle_price'] = vehicle.list_price
        
        return response
    
    @http.route(['/appointment/<int:appointment_type_id>/info'], type='http', auth="public", website=True, sitemap=False)
    def appointment_type_id_form(self, appointment_type_id, date_time, duration, staff_user_id=None, 
                                  resource_selected_id=None, available_resource_ids=None, asked_capacity=1, **kwargs):
        """Override to pass vehicle_template_id to the form page."""
        response = super().appointment_type_id_form(
            appointment_type_id, date_time, duration, staff_user_id=staff_user_id,
            resource_selected_id=resource_selected_id, available_resource_ids=available_resource_ids,
            asked_capacity=asked_capacity, **kwargs
        )
        
        # Add vehicle info to qcontext for display and hidden form field
        if hasattr(response, 'qcontext') and response.qcontext:
            vid = request.session.get('vehicle_template_id')
            if vid:
                vehicle = request.env['product.template'].sudo().browse(int(vid))
                if vehicle.exists():
                    response.qcontext['vehicle_template_id'] = vid
                    response.qcontext['vehicle_name'] = vehicle.display_name
                    response.qcontext['vehicle_price'] = vehicle.list_price
        
        return response

    def _get_extra_calendar_event_params(self, **kwargs):
        """Override to add vehicle_template_id to calendar event creation values (non-paid flow)."""
        vals = super()._get_extra_calendar_event_params(**kwargs)
        
        # Get vehicle_template_id from session (stored during appointment_type_page)
        # NOTE: Don't clear session here - _handle_appointment_form_submission also needs it
        vehicle_template_id = request.session.get('vehicle_template_id')
        if vehicle_template_id:
            vals['vehicle_template_id'] = int(vehicle_template_id)
            _logger.info("_get_extra_calendar_event_params: Adding vehicle_template_id %s to calendar event values", vehicle_template_id)
        
        return vals

    def _handle_appointment_form_submission(
        self, appointment_type,
        date_start, date_end, description, duration, allday,
        answer_input_values, name, customer, appointment_invite, guests=None,
        staff_user=None, asked_capacity=1, booking_line_values=None,
        extra_calendar_event_params=None,
    ):
        """
        Override to inject vehicle_template_id into paid booking flow.
        For paid appointments, the calendar.booking is created first, then converted to calendar.event on payment.
        """
        # Get vehicle_template_id from session before calling super
        vehicle_template_id = request.session.get('vehicle_template_id')
        
        # Call parent which handles both paid and non-paid flows
        result = super()._handle_appointment_form_submission(
            appointment_type, date_start, date_end, description, duration, allday,
            answer_input_values, name, customer, appointment_invite, guests,
            staff_user, asked_capacity, booking_line_values,
            extra_calendar_event_params or {},
        )
        
        # For paid appointments, the booking was just created - find it and add vehicle_template_id
        if vehicle_template_id and appointment_type.has_payment_step:
            # Find the most recent booking for this customer and appointment type
            booking = request.env['calendar.booking'].sudo().search([
                ('partner_id', '=', customer.id),
                ('appointment_type_id', '=', appointment_type.id),
                ('start', '=', date_start),
            ], limit=1, order='id desc')
            
            if booking:
                booking.vehicle_template_id = int(vehicle_template_id)
                _logger.info("Added vehicle_template_id %s to calendar.booking %s", vehicle_template_id, booking.id)
                
                # Also update the SOL that was created for this booking
                # The SOL was created before we set vehicle_template_id, so we need to update it now
                if booking.order_line_id:
                    booking.order_line_id.reservation_vehicle_id = int(vehicle_template_id)
                    _logger.info("Updated SOL %s with reservation_vehicle_id %s", booking.order_line_id.id, vehicle_template_id)
                
                # Clear from session
                request.session.pop('vehicle_template_id', None)
        
        return result