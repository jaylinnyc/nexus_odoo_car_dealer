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
    @http.route(['/appointment/<int:appointment_type_id>'], type='http', auth="public", website=True, csrf=True)
    def appointment_submit(self, appointment_type_id=None, **kwargs):
        response = super(WebsiteAppointmentExtended, self).appointment_type_page(appointment_type_id)
        
        # Parse params from URL
        product_id = kwargs.get('product_id')
        _logger.info("Received appointment submission with product_id: %s", product_id)
        product = request.env['product.product'].sudo().browse(int(product_id))
        
        if response.qcontext:
            response.qcontext['product_id'] = product_id
        
        return response
        
       