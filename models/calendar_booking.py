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
        Override: Pass the vehicle_template_id to the calendar event when created from paid booking,
        and mark the vehicle as reserved.
        """
        # Call parent to create the events
        super()._make_event_from_paid_booking()
        
        # Now link the vehicle to the created events and mark as reserved
        for booking in self.filtered(lambda b: b.vehicle_template_id and b.calendar_event_id):
            vehicle = booking.vehicle_template_id
            event = booking.calendar_event_id
            
            # Link vehicle to calendar event
            if not event.vehicle_template_id:
                event.vehicle_template_id = vehicle
                _logger.info(
                    "Linked vehicle template %s to calendar event %s from paid booking",
                    vehicle.display_name,
                    event.id
                )
            
            # Mark the vehicle as reserved
            if vehicle.reservation_status != 'reserved':
                vehicle.sudo().write({
                    'reservation_status': 'reserved',
                    'reserved_by_partner_id': booking.partner_id.id,
                    'reservation_date': fields.Datetime.now(),
                })
                _logger.info(
                    "Vehicle %s marked as reserved for customer %s after paid booking %s",
                    vehicle.display_name,
                    booking.partner_id.name,
                    booking.id
                )
                event.message_post(
                    body=f"Vehicle <b>{vehicle.display_name}</b> has been marked as <b>Reserved</b> for {booking.partner_id.name}."
                )
