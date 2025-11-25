from odoo import fields, models, _


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # Add a link to our custom reservation model
    reservation_id = fields.Many2one('car.reservation', string="Car Reservation")
    reservation_model = fields.Char("Reservation Model")

    def _post_process_after_done(self):
        """
        Extends the standard post-processing to handle car reservations.
        This is triggered when the payment transaction status becomes 'done'.
        """
        super()._post_process_after_done()

        # Check if this transaction is related to a car reservation
        if self.reservation_id and self.reservation_model == 'car.reservation':
            reservation = self.reservation_id

            if reservation.state == 'pending_payment':
                # 1. Update the Reservation State
                reservation.write({'state': 'reserved', 'transaction_id': self.id})

                # 2. Inventory Holding (Crucial step)
                reservation._create_holding_move()  # Call the method to lock the stock

                # 3. Notification (Optional but good UX)
                reservation.message_post(body=_("Reservation deposit paid. Car is now reserved."))

                # 4. Optional: Send Confirmation Email (Requires separate email template logic)
                # template = self.env.ref('my_car_reservations.email_template_reservation_confirm')
                # template.send_mail(reservation.id, force_send=True)