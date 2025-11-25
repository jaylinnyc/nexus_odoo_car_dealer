from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class CarReservation(models.Model):
    _name = 'car.reservation'
    _description = 'Car Reservation Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Reservation Reference', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))

    product_id = fields.Many2one(
        'product.product',
        string='Car Model',
        required=True,
        domain=[('sale_ok', '=', True)],
        help="The specific car product variant being reserved."
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True
    )

    amount = fields.Float(string="Deposit Amount", required=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending_payment', 'Pending Payment'),
        ('reserved', 'Reserved'),
        ('expired', 'Expired'),
        ('converted', 'Converted to Sale'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    transaction_id = fields.Many2one(
        'payment.transaction',
        string='Payment Transaction',
        readonly=True
    )

    date_end = fields.Datetime(
        string="Reservation Expiry",
        required=True,
        # default=lambda self: datetime.now() + timedelta(hours=48)
    )

    qty_reserved = fields.Float(string="Quantity", required=True, default=1.0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('car.reservation') or _('New')
        return super().create(vals_list)

    @api.constrains('qty_reserved')
    def _check_qty_reserved(self):
        if self.qty_reserved <= 0:
            raise UserError(_("The reserved quantity must be positive."))

    def _create_holding_move(self):
        """Creates a stock move to transfer the reserved car to a non-saleable location."""
        self.ensure_one()

        # 1. Find or create the dedicated 'Reserved' Stock Location
        reserved_location = self.env.ref('car_reservation.stock_location_reserved', raise_if_not_found=False)
        if not reserved_location:
            reserved_location = self.env['stock.location'].create({
                'name': 'Reserved Cars',
                'usage': 'internal',
                'location_id': self.env.ref('stock.stock_location_stock').id,  # Put it under the main stock
                'active': True,
            })
            # Save the reference for future use
            self.env['ir.model.data'].create({
                'module': 'car_reservation',
                'name': 'stock_location_reserved',
                'model': 'stock.location',
                'res_id': reserved_location.id,
                'noupdate': True,
            })

        # 2. Find the Source Location (where the product is currently)
        source_location = self.env.ref('stock.stock_location_stock')

        # 3. Create the Stock Move
        stock_move = self.env['stock.move'].create({
            'name': _("Car Reservation: %s") % self.name,
            'product_id': self.product_id.id,
            'product_uom_qty': self.qty_reserved,
            'product_uom': self.product_id.uom_id.id,
            'location_id': source_location.id,  # From main stock
            'location_dest_id': reserved_location.id,  # To reserved location
            'state': 'confirmed',
            'origin': self.name,
            # Link to the reservation record for traceability
            'reservation_id': self.id,
        })

        # Immediately process the move to update inventory
        stock_move._action_done()

        return stock_move

    def _create_return_move(self):
        """Creates a stock move to return the reserved car back to the saleable location."""
        self.ensure_one()

        # 1. Find the Reserved and Stock Locations (Must use the same location logic as _create_holding_move)
        reserved_location = self.env.ref('car_reservation.stock_location_reserved')
        source_location = self.env.ref('stock.stock_location_stock')

        # 2. Create the Stock Move (Reverse the holding move)
        stock_move = self.env['stock.move'].create({
            'name': _("Reservation Expired: %s") % self.name,
            'product_id': self.product_id.id,
            'product_uom_qty': self.qty_reserved,
            'product_uom': self.product_id.uom_id.id,
            'location_id': reserved_location.id,  # From reserved location
            'location_dest_id': source_location.id,  # To main stock
            'state': 'confirmed',
            'origin': self.name,
            'reservation_id': self.id,
        })

        stock_move._action_done()

    # @api.model
    # def _cron_expire_reservations(self):
    #     """Automated action to find and process expired reservations."""
    #     now = datetime.now()
    #     expired_reservations = self.search([
    #         ('state', '=', 'reserved'),
    #         ('date_end', '<=', now)
    #     ])
    #
    #     for reservation in expired_reservations:
    #         reservation.write({'state': 'expired'})
    #         reservation._create_return_move()
    #         reservation.message_post(body=_("Reservation expired. Car returned to available inventory."))
    #
    #     return True