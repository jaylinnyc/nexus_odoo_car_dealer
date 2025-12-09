from odoo import api, fields, models, _


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _create_analytic_account_for_vehicle(self):
        """Create an analytic account (project) for the purchased vehicle."""
        self.ensure_one()
        
        # Only create if this is a vehicle product (has vehicle-specific fields)
        if not (self.product_id.make or self.product_id.model or self.product_id.vin):
            return False
        
        # Check if analytic account already exists
        if self.product_id.analytic_account_id:
            return self.product_id.analytic_account_id
        
        # Create the project/analytic account
        project_vals = {
            'name': self._get_vehicle_project_name(),
            'company_id': self.company_id.id,
            'active': True,
        }
        
        project = self.env['project.project'].create(project_vals)
        
        # Link the analytic account to the product
        self.product_id.write({
            'analytic_account_id': project.analytic_account_id.id,
        })
        
        return project.analytic_account_id
    
    def _get_vehicle_project_name(self):
        """Generate a descriptive name for the vehicle project."""
        product = self.product_id
        name_parts = []
        
        if product.year:
            name_parts.append(str(product.year))
        if product.make:
            name_parts.append(product.make)
        if product.model:
            name_parts.append(product.model)
        
        if name_parts:
            base_name = ' '.join(name_parts)
        else:
            base_name = product.name
        
        # Add VIN if available for uniqueness
        if product.vin:
            return f"{base_name} (VIN: {product.vin})"
        
        return base_name
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to auto-generate analytic accounts for vehicles."""
        lines = super().create(vals_list)
        
        for line in lines:
            # Only process if the purchase order is confirmed
            if line.state in ('purchase', 'done'):
                line._create_analytic_account_for_vehicle()
        
        return lines
    
    def write(self, vals):
        """Override write to handle analytic account creation when PO is confirmed."""
        res = super().write(vals)
        
        # Check if state changed to purchase or done
        if 'state' in vals and vals.get('state') in ('purchase', 'done'):
            for line in self:
                line._create_analytic_account_for_vehicle()
        
        return res


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    
    def button_confirm(self):
        """Override to create analytic accounts when PO is confirmed."""
        res = super().button_confirm()
        
        for order in self:
            for line in order.order_line:
                line._create_analytic_account_for_vehicle()
        
        return res
