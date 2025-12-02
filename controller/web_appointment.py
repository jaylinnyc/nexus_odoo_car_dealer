from odoo import http
from odoo.http import request
# 1. UPDATE IMPORT: The controller is now in 'appointment'
from odoo.addons.appointment.controllers.appointment import AppointmentController

import logging

_logger = logging.getLogger(__name__)

# 2. UPDATE CLASS: Inherit from AppointmentController
class WebsiteAppointmentExtended(AppointmentController):
    
    # Check if this route still matches the Odoo 19 standard, 
    # or if you are defining a custom endpoint.
    @http.route(['/appointment/submit'], type='http', auth="public", website=True, csrf=True)
    def appointment_submit(self, appointment_id=None, **kwargs):
        # Parse params from URL
        product_id = kwargs.get('product_id')
        
        # 1. Prepare data for the super call
        super_kwargs = kwargs.copy()
        
        # 2. Add required fields if they are missing (The reason for your TypeError)
        # We use current date/time strings for validity, but the email will be fake.
        import datetime
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Highlighted changes: Injecting hardcoded/dummy values if missing
        if not super_kwargs.get('datetime_str'):
            super_kwargs['datetime_str'] = now_str # Fallback Date/Time
        if not super_kwargs.get('duration_str'):
            super_kwargs['duration_str'] = '1.0'  # Fallback duration (1 hour)
        if not super_kwargs.get('name'):
            super_kwargs['name'] = 'Test User Name' # Fallback Name
        if not super_kwargs.get('email'):
            super_kwargs['email'] = 'test.user@dummy.com' # Fallback Email
        
        # --- END OF TEMPORARY FIX ---
        
        
        # 3. Call super() on the new parent class
        response = super(WebsiteAppointmentExtended, self).appointment_form_submit(**super_kwargs)
        # 4. Logic to write the product_id (handled safely for Odoo 19/HTTP Response)
        if product_id:
            # We must try to extract the created appointment from the response context
            # because super() returns an HTML Response, not a dict.
            appointment = self._get_created_appointment_safe(response)
            
            if appointment:
                appointment.sudo().write({'physical_product_id': int(product_id)})
                
            # --- LOGGING ADDED HERE ---
            _logger.info(
                "Product ID %s written to new Calendar Event ID %s. physical_product_id: %s",
                product_id,
                appointment.id,
                appointment.physical_product_id.id
            )
            # --- END LOGGING ---
        
        return response
        

    def _get_created_appointment_safe(self, response):
        """
        Helper to find the appointment.
        Odoo 19 returns a rendered QWeb template (lazy render), 
        so we can check the qcontext.
        """
        # Try retrieving from qcontext (standard success page)
        if hasattr(response, 'qcontext'):
            # The key in Odoo 17+ is usually 'event' or 'appointment'
            return response.qcontext.get('event') or response.qcontext.get('appointment')
        
        # Fallback: Find the most recently created appointment by this user/session
        # This handles cases where the controller redirects instead of rendering.
        domain = [('create_date', '>=', request.httprequest.date)]
        
        if not request.env.user._is_public():
            domain.append(('partner_id', '=', request.env.user.partner_id.id))
            
        return request.env['calendar.event'].sudo().search(domain, order='id desc', limit=1)