from odoo import http
from odoo.http import request
from odoo.addons.website_appointment.controllers.main import WebsiteAppointment

class WebsiteAppointmentExtended(WebsiteAppointment):
    @http.route(['/website/appointment/submit'], type='http', auth="public", website=True, csrf=True)
    def appointment_submit(self, **post):
        # Parse params from URL (passed from Reserve Now button)
        product_id = request.params.get('product_id')
        res = super(WebsiteAppointmentExtended, self).appointment_submit(**post)
        if res and 'appointment_id' in res and product_id:
            appointment = request.env['calendar.event'].sudo().browse(res['appointment_id'])
            appointment.write({'physical_product_id': int(product_id)})
        return res