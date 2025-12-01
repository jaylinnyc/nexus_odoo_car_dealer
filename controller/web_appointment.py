from odoo import http
from odoo.http import request
# 1. UPDATE IMPORT: The controller is now in 'appointment'
from odoo.addons.appointment.controllers.appointment import AppointmentController

# 2. UPDATE CLASS: Inherit from AppointmentController
class WebsiteAppointmentExtended(AppointmentController):
    
    # Check if this route still matches the Odoo 19 standard, 
    # or if you are defining a custom endpoint.
    @http.route(['/website/appointment/submit'], type='http', auth="public", website=True, csrf=True)
    def appointment_submit(self, **kwargs):
        # Parse params from URL
        product_id = kwargs.get('product_id')
        
        # 3. Call super() on the new parent class
        response = super(WebsiteAppointmentExtended, self).appointment_submit(**kwargs)

        # 4. Logic to write the product_id (handled safely for Odoo 19/HTTP Response)
        if product_id:
            # We must try to extract the created appointment from the response context
            # because super() returns an HTML Response, not a dict.
            appointment = self._get_created_appointment_safe(response)
            
            if appointment:
                appointment.sudo().write({'physical_product_id': int(product_id)})
        
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