from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FinancingAgreementWizard(models.TransientModel):
    _name = 'financing.agreement.wizard'
    _description = 'Create Financing Agreement Wizard'

    partner_id = fields.Many2one('res.partner', string='Lender', required=True)
    agreement_date = fields.Date(string='Agreement Date', default=fields.Date.today, required=True)
    interest_rate = fields.Float(string='Annual Interest Rate (%)', required=True, default=0.0)
    
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

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Load available vehicles with outstanding bills when lender is selected"""
        if self.partner_id:
            # Find all products with purchase orders that have outstanding vendor bills
            products = self.env['product.template'].search([
                ('purchase_order_line_ids', '!=', False),
                ('total_bills_residual', '>', 0),
                ('financing_type', '=', 'none'),  # Not already financed
            ])
            
            lines = []
            for product in products:
                # Get the outstanding bill amount
                if product.total_bills_residual > 0:
                    lines.append((0, 0, {
                        'vehicle_id': product.id,
                        'financed_amount': product.total_bills_residual,
                        'selected': False,
                    }))
            
            self.vehicle_line_ids = lines

    def action_create_agreement(self):
        """Create the financing agreement and lines for selected vehicles"""
        selected_lines = self.vehicle_line_ids.filtered(lambda l: l.selected)
        
        if not selected_lines:
            raise UserError(_('Please select at least one vehicle to finance.'))
        
        # Create the agreement
        agreement = self.env['financing.agreement'].create({
            'partner_id': self.partner_id.id,
            'agreement_date': self.agreement_date,
            'state': 'draft',
        })
        
        # Create agreement lines for each selected vehicle
        for line in selected_lines:
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
    vehicle_id = fields.Many2one('product.template', string='Vehicle', required=True)
    financed_amount = fields.Monetary(string='Amount to Finance', currency_field='currency_id', required=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    selected = fields.Boolean(string='Select', default=True)
    
    # Display fields
    vendor_bill_amount = fields.Monetary(related='vehicle_id.total_bills_amount', string='Total Bill Amount', readonly=True)
    outstanding_amount = fields.Monetary(related='vehicle_id.total_bills_residual', string='Outstanding Amount', readonly=True)
