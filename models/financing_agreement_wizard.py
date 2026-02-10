from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FinancingAgreementWizard(models.TransientModel):
    _name = 'financing.agreement.wizard'
    _description = 'Create Financing Agreement Wizard'

    partner_id = fields.Many2one('res.partner', string='Lender', required=True)
    dealer_id = fields.Many2one('res.partner', string='Dealer', required=True)
    agreement_date = fields.Date(string='Agreement Date', default=fields.Date.today, required=True)
    interest_rate = fields.Float(string='Annual Interest Rate (%)', required=True, default=0.0)
    
    multiple_vehicles = fields.Boolean(string='Finance Multiple Vehicles', default=False)
    vehicle_id = fields.Many2one(
        'product.template',
        string='Vehicle',
        domain="[('categ_id.name', '=', 'Vehicles')]"
    )
    financed_amount = fields.Monetary(string='Amount to Finance', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    
    vehicle_line_ids = fields.One2many('financing.agreement.wizard.line', 'wizard_id', string='Vehicles to Finance')
    
    expense_account_id = fields.Many2one(
        'account.account',
        string='Interest Expense Account',
        domain="[('account_type', '=', 'expense')]",
        default=lambda self: self.env.ref('nexus_odoo_car_dealer.account_interest_expense', raise_if_not_found=False),
    )
    liability_account_id = fields.Many2one(
        'account.account',
        string='Floor Plan Liability Account',
        domain="[('account_type', 'in', ['liability_current', 'liability_non_current', 'liability_payable'])]",
        default=lambda self: self.env.ref('nexus_odoo_car_dealer.account_floor_plan_payable', raise_if_not_found=False),
    )

    @api.model
    def _get_eligible_vehicles(self):
        """Get vehicles with outstanding bills eligible for financing.
        
        Excludes:
        - Vehicles that already have financing set up (financing_type != 'none')
        - Vehicles with no outstanding bill balance (total_bills_residual == 0, i.e., paid off)
        - Vehicles that are already in an active financing agreement line
        """
        # Get vehicles in the Vehicles category without existing financing
        products = self.env['product.template'].search([
            ('categ_id.name', '=', 'Vehicles'),
            ('financing_type', '=', 'none')
        ])
        
        # Find vehicles already in active financing agreement lines
        already_financed_vehicles = self.env['financing.agreement.line'].search([
            ('state', 'in', ['draft', 'active'])
        ]).mapped('vehicle_id').ids
        
        # Filter: must have outstanding bills AND not already in a financing agreement
        eligible = products.filtered(
            lambda p: p.total_bills_residual > 0 and p.id not in already_financed_vehicles
        )
        return eligible

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        """Set financed amount when vehicle is selected"""
        if self.vehicle_id:
            self.financed_amount = self.vehicle_id.total_bills_residual
        # Return domain to filter eligible vehicles in the dropdown
        eligible_vehicles = self._get_eligible_vehicles()
        return {
            'domain': {
                'vehicle_id': [('id', 'in', eligible_vehicles.ids)]
            }
        }
    
    @api.onchange('multiple_vehicles')
    def _onchange_multiple_vehicles(self):
        """Load available vehicles with outstanding bills when multiple vehicles is enabled"""
        if self.multiple_vehicles:
            # Find all vehicles with outstanding bills that aren't already financed
            eligible_vehicles = self._get_eligible_vehicles()
            
            lines = []
            for product in eligible_vehicles:
                lines.append((0, 0, {
                    'vehicle_id': product.id,
                    'financed_amount': product.total_bills_residual,
                    'selected': False,
                }))
            
            self.vehicle_line_ids = lines
        else:
            self.vehicle_line_ids = [(5, 0, 0)]  # Clear all lines

    def action_create_agreement(self):
        """Create the financing agreement and lines for selected vehicles"""
        # Collect vehicles to finance
        vehicles_to_finance = []
        
        if self.multiple_vehicles:
            selected_lines = self.vehicle_line_ids.filtered(lambda l: l.selected)
            if not selected_lines:
                raise UserError(_('Please select at least one vehicle to finance.'))
            vehicles_to_finance = selected_lines
        else:
            if not self.vehicle_id:
                raise UserError(_('Please select a vehicle to finance.'))
            if self.financed_amount <= 0:
                raise UserError(_('Financed amount must be greater than zero.'))
            # Create a temporary line object for single vehicle mode
            vehicles_to_finance = [type('obj', (object,), {
                'vehicle_id': self.vehicle_id,
                'financed_amount': self.financed_amount
            })]
        
        # Create the agreement
        agreement = self.env['financing.agreement'].create({
            'dealer_id': self.dealer_id.id,
            'partner_id': self.partner_id.id,
            'agreement_date': self.agreement_date,
            'state': 'draft',
        })
        
        # Create agreement lines for each vehicle
        for line in vehicles_to_finance:
            self.env['financing.agreement.line'].create({
                'agreement_id': agreement.id,
                'vehicle_id': line.vehicle_id.id,
                'financed_amount': line.financed_amount,
                'interest_rate': self.interest_rate,
                'start_date': self.agreement_date,
                'current_balance': line.financed_amount,
                'state': 'draft',
                'expense_account_id': self.expense_account_id.id,
                'liability_account_id': self.liability_account_id.id,
            })
            
            # Update the vehicle's financing info
            line.vehicle_id.write({
                'financing_type': 'internal',
                'financing_amount': line.financed_amount,
                'financing_rate': self.interest_rate,
                'financing_partner_id': self.partner_id.id,
                'financing_dealer_id': self.dealer_id.id,
                'financing_start_date': self.agreement_date,
                'financing_status': 'active',
                'financing_balance': line.financed_amount,
                'financing_expense_account_id': self.expense_account_id.id,
                'financing_liability_account_id': self.liability_account_id.id,
            })
        
        # Return action to open the created agreement
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'financing.agreement',
            'res_id': agreement.id,
            'view_mode': 'form',
            'target': 'current',
        }


class FinancingAgreementWizardLine(models.TransientModel):
    _name = 'financing.agreement.wizard.line'
    _description = 'Financing Agreement Wizard Line'

    wizard_id = fields.Many2one('financing.agreement.wizard', string='Wizard', required=True, ondelete='cascade')
    vehicle_id = fields.Many2one(
        'product.template',
        string='Vehicle',
        required=True,
        domain="[('categ_id.name', '=', 'Vehicles')]"
    )
    financed_amount = fields.Monetary(string='Amount to Finance', currency_field='currency_id', required=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    selected = fields.Boolean(string='Select', default=True)
    
    # Display fields
    vendor_bill_amount = fields.Monetary(related='vehicle_id.total_bills_amount', string='Total Bill Amount', readonly=True)
    outstanding_amount = fields.Monetary(related='vehicle_id.total_bills_residual', string='Outstanding Amount', readonly=True)
