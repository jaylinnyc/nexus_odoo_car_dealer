from odoo import api, fields, models

import logging

_logger = logging.getLogger(__name__)


class CalendarBooking(models.Model):
    """
    Extend calendar.booking to store the vehicle being reserved.
    This is used when appointments require payment before confirmation.
    The vehicle_template_id is passed to calendar.event when the booking is confirmed/paid.
    """
    _inherit = 'calendar.booking'

    vehicle_template_id = fields.Many2one(
        'product.template',
        string="Reserved Vehicle",
        help="The vehicle (product template) being reserved through this booking"
    )

    def _make_event_from_paid_booking(self):
        """
        Override: Pass the vehicle_template_id to the calendar event when created from paid booking.
        """
        # Call parent to create the events
        super()._make_event_from_paid_booking()
        
        # Now link the vehicle to the created events
        for booking in self.filtered(lambda b: b.vehicle_template_id and b.calendar_event_id):
            if not booking.calendar_event_id.vehicle_template_id:
                booking.calendar_event_id.vehicle_template_id = booking.vehicle_template_id
                _logger.info(
                    "Linked vehicle template %s to calendar event %s from paid booking",
                    booking.vehicle_template_id.display_name,
                    booking.calendar_event_id.id
                )
