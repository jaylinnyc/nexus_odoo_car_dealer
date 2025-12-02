from odoo import http
from odoo.http import request
# 1. UPDATE IMPORT: The controller is now in 'appointment'
from odoo.addons.appointment.controllers.appointment import AppointmentController

import logging

_logger = logging.getLogger(__name__)

# 2. UPDATE CLASS: Inherit from AppointmentController
class WebsiteAppointmentExtended(AppointmentController):

    @http.route(['/appointment/<int:appointment_type_id>'], type='http', auth="public", website=True, csrf=True)
    def appointment_submit(self, appointment_type_id=None, **kwargs):
        response = super(WebsiteAppointmentExtended, self).appointment_type_page(appointment_type_id)
        
        product_id = kwargs.get('product_id')
        product_name = kwargs.get('product_name')
        product_price = kwargs.get('product_price')
        
        if response.qcontext:
            response.qcontext['product_id'] = product_id
            response.qcontext['product_name'] = product_name
            response.qcontext['product_price'] = product_price 
        
        return response
    
    @http.route(['/appointment/<int:appointment_type_id>/info'], type='http', auth="public", website=True, csrf=True)
    def appointment_info(self, appointment_type_id=None, **kwargs):
        response = super(WebsiteAppointmentExtended, self).appointment_type_id_form(appointment_type_id, **kwargs)
        
        product_id = kwargs.get('product_id')
        product_name = kwargs.get('product_name')
        product_price = kwargs.get('product_price')
        
        if response.qcontext:
            response.qcontext['product_id'] = product_id
            response.qcontext['product_name'] = product_name
            response.qcontext['product_price'] = product_price 
        
        return response
    

        
       