# Odoo 19 Custom Module Development Guide

## Table of Contents
1. [Module Structure](#module-structure)
2. [Creating a Custom Module](#creating-a-custom-module)
3. [Creating New Models](#creating-new-models)
4. [Creating Views](#creating-views)
5. [Overriding Existing Models](#overriding-existing-models)
6. [Overriding Existing Views](#overriding-existing-views)
7. [Linking Custom Modules with Existing Modules](#linking-custom-modules)
8. [Security Configuration](#security-configuration)
9. [Controllers](#controllers)
10. [Best Practices](#best-practices)

---

## 1. Module Structure

A standard Odoo 19 module follows this structure:

```
your_module/
├── __init__.py                 # Root initialization (imports models, controllers, etc.)
├── __manifest__.py             # Module metadata and dependencies
├── models/                     # Business logic layer
│   ├── __init__.py            # Import all model files
│   ├── your_model.py          # New models
│   └── existing_model.py      # Model inheritances/overrides
├── views/                      # XML view definitions
│   ├── model_views.xml        # Forms, trees, kanban, etc.
│   └── templates.xml          # QWeb templates
├── data/                       # Data files
│   ├── initial_data.xml       # Master data
│   └── cron_jobs.xml          # Scheduled actions
├── security/                   # Access rights
│   └── ir.model.access.csv    # Model access permissions
├── controller/                 # HTTP controllers
│   ├── __init__.py
│   └── main.py
├── static/                     # Frontend assets
│   ├── description/           # Module icon and screenshots
│   └── src/
│       ├── js/                # JavaScript files
│       ├── css/               # Stylesheets
│       └── xml/               # QWeb templates for frontend
├── wizard/                     # Transient models (wizards)
│   ├── __init__.py
│   └── wizard_model.py
└── tests/                      # Unit tests
    └── test_module.py
```

---

## 2. Creating a Custom Module

### Step 1: Create Module Directory Structure

Create a folder in your addons path (ea.g., `d:\odoo\custom_addons\your_module`):

```bash
mkdir your_module
cd your_module
```

### Step 2: Create `__init__.py`

```python
# __init__.py
from . import models
from . import controller
from . import wizard
```

### Step 3: Create `__manifest__.py`

```python
# __manifest__.py
{
    'name': 'Your Module Name',
    'version': '1.0.19',  # For Odoo 19
    'category': 'Category/Subcategory',
    'summary': 'Short description of your module',
    'description': """
Long Description
================
Detailed explanation of what your module does.
    """,
    'author': 'Your Company',
    'website': 'https://yourcompany.com',
    'license': 'LGPL-3',
    
    # Dependencies - list all Odoo modules your module depends on
    'depends': [
        'base',           # Always required
        'sale',           # If extending sales
        'account',        # If extending accounting
        'website',        # If adding website features
        'mail',           # If using chatter/messaging
    ],
    
    # Data files - loaded in order
    'data': [
        # Security must be loaded first
        'security/ir.model.access.csv',
        
        # Then data files
        'data/initial_data.xml',
        
        # Then views
        'views/model_views.xml',
        'views/menu_views.xml',
    ],
    
    # Frontend assets (JS, CSS)
    'assets': {
        'web.assets_backend': [
            'your_module/static/src/js/custom_widget.js',
            'your_module/static/src/xml/custom_template.xml',
        ],
        'web.assets_frontend': [
            'your_module/static/src/css/frontend_styles.css',
        ],
    },
    
    'installable': True,
    'application': True,      # True if standalone app, False if just extension
    'auto_install': False,    # True for automatic installation when dependencies met
    'sequence': 100,
}
```

---

## 3. Creating New Models

### Basic Model Example

```python
# models/__init__.py
from . import vehicle_financing

# models/vehicle_financing.py
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import date
import logging

_logger = logging.getLogger(__name__)

class VehicleFinancing(models.Model):
    """New model for vehicle financing management"""
    
    _name = 'vehicle.financing'              # Technical name (database table)
    _description = 'Vehicle Financing Management'  # User-friendly description
    _inherit = ['mail.thread', 'mail.activity.mixin']  # Add chatter support
    _order = 'bill_date desc'                # Default sort order
    _rec_name = 'product_id'                 # Field to use for display name
    
    # Field Types
    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    
    product_id = fields.Many2one(
        'product.template',
        string='Vehicle',
        required=True,
        ondelete='cascade',      # What happens when related record is deleted
        tracking=True,           # Track changes in chatter
    )
    
    bill_date = fields.Date(
        string='Bill Date',
        required=True,
        default=fields.Date.today,
    )
    
    interest_amount = fields.Monetary(
        string='Interest Amount',
        currency_field='currency_id',
        required=True,
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    
    bill_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
        readonly=True,
        ondelete='cascade'
    )
    
    # Computed fields
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_total_amount',
        store=True,              # Store in database for performance
        readonly=True,
    )
    
    # Related fields (shortcut to related record's field)
    partner_id = fields.Many2one(
        related='product_id.partner_id',
        string='Vendor',
        store=True,
        readonly=True,
    )
    
    # One2many (inverse of Many2one)
    transaction_ids = fields.One2many(
        'vehicle.financing.transaction',
        'financing_id',
        string='Transactions',
    )
    
    # Computed method
    @api.depends('interest_amount', 'transaction_ids.amount')
    def _compute_total_amount(self):
        for record in self:
            transaction_total = sum(record.transaction_ids.mapped('amount'))
            record.total_amount = record.interest_amount + transaction_total
    
    # Constraint
    @api.constrains('interest_amount')
    def _check_interest_amount(self):
        for record in self:
            if record.interest_amount < 0:
                raise ValidationError(_('Interest amount cannot be negative.'))
    
    # SQL Constraint
    _sql_constraints = [
        ('unique_bill', 'unique(bill_id)', 'Bill already linked to another financing record!'),
    ]
    
    # Onchange method
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            # Auto-fill partner based on product
            self.partner_id = self.product_id.partner_id
    
    # CRUD override
    @api.model
    def create(self, vals):
        """Override create to generate sequence"""
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('vehicle.financing') or _('New')
        return super(VehicleFinancing, self).create(vals)
    
    def unlink(self):
        """Override delete to add custom logic"""
        for record in self:
            if record.state == 'posted':
                raise UserError(_('Cannot delete posted financing records.'))
        return super(VehicleFinancing, self).unlink()
    
    # Action methods (button actions)
    def action_confirm(self):
        """Confirm the financing record"""
        self.ensure_one()  # Ensure single record
        self.state = 'confirmed'
        _logger.info('Financing %s confirmed', self.name)
    
    def action_post(self):
        """Post the financing record"""
        for record in self:
            if not record.bill_id:
                # Create vendor bill
                record._create_vendor_bill()
            record.state = 'posted'
    
    def _create_vendor_bill(self):
        """Private method to create vendor bill"""
        self.ensure_one()
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': self.bill_date,
            'invoice_line_ids': [(0, 0, {
                'name': f'Interest for {self.product_id.name}',
                'quantity': 1,
                'price_unit': self.interest_amount,
            })],
        }
        self.bill_id = self.env['account.move'].create(bill_vals)
```

### Transient Model (Wizard)

```python
# wizard/financing_wizard.py
from odoo import fields, models, api

class FinancingWizard(models.TransientModel):
    """Wizard for processing financing operations"""
    
    _name = 'financing.wizard'
    _description = 'Financing Wizard'
    
    financing_ids = fields.Many2many(
        'vehicle.financing',
        string='Financing Records',
    )
    
    operation = fields.Selection([
        ('approve', 'Approve'),
        ('reject', 'Reject'),
    ], string='Operation', required=True)
    
    notes = fields.Text(string='Notes')
    
    def action_process(self):
        """Process the selected financing records"""
        self.ensure_one()
        for financing in self.financing_ids:
            if self.operation == 'approve':
                financing.action_confirm()
            elif self.operation == 'reject':
                financing.state = 'cancel'
        return {'type': 'ir.actions.act_window_close'}
```

---

## 4. Creating Views

### Form View

```xml
<!-- views/vehicle_financing_views.xml -->
<odoo>
    <data>
        <!-- Form View -->
        <record id="view_vehicle_financing_form" model="ir.ui.view">
            <field name="name">vehicle.financing.form</field>
            <field name="model">vehicle.financing</field>
            <field name="arch" type="xml">
                <form string="Vehicle Financing">
                    <!-- Header with status bar and buttons -->
                    <header>
                        <button name="action_confirm" 
                                type="object" 
                                string="Confirm"
                                class="btn-primary"
                                invisible="state != 'draft'"/>
                        <button name="action_post" 
                                type="object" 
                                string="Post"
                                class="btn-primary"
                                invisible="state != 'confirmed'"/>
                        <field name="state" widget="statusbar" 
                               statusbar_visible="draft,confirmed,posted"/>
                    </header>
                    
                    <sheet>
                        <!-- Smart buttons -->
                        <div class="oe_button_box" name="button_box">
                            <button class="oe_stat_button" 
                                    type="object" 
                                    name="action_view_bill"
                                    icon="fa-file-text-o"
                                    invisible="not bill_id">
                                <span class="o_stat_text">View Bill</span>
                            </button>
                        </div>
                        
                        <!-- Ribbon for status -->
                        <widget name="web_ribbon" 
                                title="Cancelled" 
                                bg_color="text-bg-danger" 
                                invisible="state != 'cancel'"/>
                        
                        <!-- Main form content -->
                        <group>
                            <group string="Vehicle Information">
                                <field name="name"/>
                                <field name="product_id"/>
                                <field name="partner_id"/>
                            </group>
                            <group string="Financial Information">
                                <field name="bill_date"/>
                                <field name="interest_amount" 
                                       widget="monetary"/>
                                <field name="currency_id" 
                                       invisible="1"/>
                                <field name="total_amount" 
                                       widget="monetary"/>
                            </group>
                        </group>
                        
                        <!-- Notebook (tabs) -->
                        <notebook>
                            <page string="Transactions" name="transactions">
                                <field name="transaction_ids">
                                    <list>
                                        <field name="transaction_date"/>
                                        <field name="amount"/>
                                        <field name="description"/>
                                    </list>
                                </field>
                            </page>
                            <page string="Notes" name="notes">
                                <field name="notes" 
                                       placeholder="Add notes here..."/>
                            </page>
                        </notebook>
                    </sheet>
                    
                    <!-- Chatter (messages and activities) -->
                    <chatter/>
                </form>
            </field>
        </record>
```

### List/Tree View

```xml
        <!-- List View -->
        <record id="view_vehicle_financing_tree" model="ir.ui.view">
            <field name="name">vehicle.financing.list</field>
            <field name="model">vehicle.financing</field>
            <field name="arch" type="xml">
                <list string="Vehicle Financing" 
                      create="true" 
                      edit="true" 
                      delete="true"
                      multi_edit="1"
                      export_xlsx="1">
                    <!-- Decoration based on field values -->
                    <decoration-success="state == 'posted'"/>
                    <decoration-info="state == 'draft'"/>
                    <decoration-muted="state == 'cancel'"/>
                    
                    <field name="name"/>
                    <field name="product_id"/>
                    <field name="bill_date"/>
                    <field name="interest_amount" 
                           widget="monetary" 
                           sum="Total"/>
                    <field name="state" 
                           widget="badge" 
                           decoration-success="state == 'posted'"
                           decoration-info="state == 'draft'"/>
                    
                    <!-- Inline buttons -->
                    <button name="action_confirm" 
                            type="object" 
                            string="Confirm" 
                            icon="fa-check"
                            invisible="state != 'draft'"/>
                </list>
            </field>
        </record>
```

### Kanban View

```xml
        <!-- Kanban View -->
        <record id="view_vehicle_financing_kanban" model="ir.ui.view">
            <field name="name">vehicle.financing.kanban</field>
            <field name="model">vehicle.financing</field>
            <field name="arch" type="xml">
                <kanban default_group_by="state">
                    <field name="name"/>
                    <field name="product_id"/>
                    <field name="interest_amount"/>
                    <field name="state"/>
                    <templates>
                        <t t-name="card">
                            <div class="oe_kanban_global_click">
                                <div class="o_kanban_image">
                                    <img t-att-src="kanban_image('product.template', 'image_128', record.product_id.raw_value)" 
                                         alt="Product"/>
                                </div>
                                <div class="oe_kanban_details">
                                    <strong><field name="name"/></strong>
                                    <div><field name="product_id"/></div>
                                    <div>Amount: <field name="interest_amount"/></div>
                                </div>
                            </div>
                        </t>
                    </templates>
                </kanban>
            </field>
        </record>
```

### Search View (Filters and Group By)

```xml
        <!-- Search View -->
        <record id="view_vehicle_financing_search" model="ir.ui.view">
            <field name="name">vehicle.financing.search</field>
            <field name="model">vehicle.financing</field>
            <field name="arch" type="xml">
                <search>
                    <!-- Search fields -->
                    <field name="name" 
                           string="Reference" 
                           filter_domain="[('name', 'ilike', self)]"/>
                    <field name="product_id"/>
                    <field name="partner_id"/>
                    
                    <!-- Filters -->
                    <filter name="filter_draft" 
                            string="Draft" 
                            domain="[('state', '=', 'draft')]"/>
                    <filter name="filter_posted" 
                            string="Posted" 
                            domain="[('state', '=', 'posted')]"/>
                    
                    <separator/>
                    
                    <filter name="filter_this_month" 
                            string="This Month" 
                            domain="[('bill_date', '&gt;=', (context_today() - relativedelta(day=1)).strftime('%Y-%m-%d')),
                                    ('bill_date', '&lt;=', (context_today() + relativedelta(day=31)).strftime('%Y-%m-%d'))]"/>
                    
                    <!-- Group by -->
                    <group expand="0" string="Group By">
                        <filter name="group_product" 
                                string="Vehicle" 
                                context="{'group_by':'product_id'}"/>
                        <filter name="group_state" 
                                string="Status" 
                                context="{'group_by':'state'}"/>
                        <filter name="group_date" 
                                string="Bill Date" 
                                context="{'group_by':'bill_date:month'}"/>
                    </group>
                </search>
            </field>
        </record>
```

### Actions and Menu

```xml
        <!-- Action -->
        <record id="action_vehicle_financing" model="ir.actions.act_window">
            <field name="name">Vehicle Financing</field>
            <field name="res_model">vehicle.financing</field>
            <field name="view_mode">list,kanban,form</field>
            <field name="context">{'search_default_filter_draft': 1}</field>
            <field name="help" type="html">
                <p class="o_view_nocontent_smiling_face">
                    Create your first financing record
                </p>
                <p>
                    Track vehicle financing and interest payments here.
                </p>
            </field>
        </record>
        
        <!-- Menu Items -->
        <menuitem id="menu_vehicle_financing_root" 
                  name="Vehicle Financing" 
                  sequence="10"/>
        
        <menuitem id="menu_vehicle_financing" 
                  name="Financing" 
                  parent="menu_vehicle_financing_root" 
                  action="action_vehicle_financing" 
                  sequence="10"/>
    </data>
</odoo>
```

---

## 5. Overriding Existing Models

### Inheriting and Extending Models

```python
# models/sale_order.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    """Extend sale.order model with custom functionality"""
    
    _inherit = 'sale.order'  # Inherit existing model
    
    # Add new fields to existing model
    first_order_line_id = fields.Many2one(
        'sale.order.line',
        string='First Order Line',
        compute='_compute_first_order_line',
        store=True,
        readonly=True,
    )
    
    linked_car = fields.Many2one(
        'product.product',
        string='Linked Car',
        domain="[('categ_id.name', '=', 'Vehicles')]",
        tracking=True,
    )
    
    # Add computed field
    @api.depends('order_line.sequence')
    def _compute_first_order_line(self):
        """Compute the first order line based on sequence"""
        for order in self:
            if order.order_line:
                first_line = order.order_line.sorted('sequence')[:1]
                order.first_order_line_id = first_line
            else:
                order.first_order_line_id = False
    
    # Override existing method
    def action_confirm(self):
        """Override confirm action to add custom logic"""
        # Call parent method first
        res = super(SaleOrder, self).action_confirm()
        
        # Add your custom logic
        for order in self:
            _logger.info("Sale Order %s confirmed with custom logic", order.name)
            
            # Check for vehicle reservation
            appointment = self.env['calendar.event'].search([
                ('sale_order_line_ids', 'in', order.order_line.ids),
            ], limit=1)
            
            if appointment:
                appointment.action_confirm_reservation()
                _logger.info("Vehicle reservation confirmed for SO %s", order.name)
            
            # Process vehicle financing
            for line in order.order_line:
                product = line.product_template_id
                if product.financing_status == 'active':
                    product.financing_status = 'paid_off'
        
        return res
    
    # Extend existing method with additional parameters
    def _prepare_order_line_values(self, *args, calendar_booking_id=False, **kwargs):
        """
        Override to add reservation_vehicle_id from calendar.booking to SOL.
        """
        values = super()._prepare_order_line_values(
            *args,
            calendar_booking_id=calendar_booking_id,
            **kwargs,
        )
        
        if calendar_booking_id:
            booking_sudo = self.env['calendar.booking'].sudo().browse(calendar_booking_id)
            if booking_sudo.vehicle_template_id:
                values['reservation_vehicle_id'] = booking_sudo.vehicle_template_id.id
                _logger.info("Linked vehicle %s to SOL", booking_sudo.vehicle_template_id.display_name)
        
        return values
```

### Inheriting from Multiple Models

```python
class ProductTemplate(models.Model):
    """Extend product.template with vehicle-specific fields"""
    
    _inherit = 'product.template'
    
    # Vehicle-specific fields
    vin = fields.Char(string='VIN', help='Vehicle Identification Number')
    year = fields.Integer(string='Year')
    make = fields.Char(string='Make')
    model = fields.Char(string='Model')
    
    financing_status = fields.Selection([
        ('none', 'No Financing'),
        ('active', 'Active Financing'),
        ('paid_off', 'Paid Off'),
    ], string='Financing Status', default='none')
    
    last_interest_bill_date = fields.Date(
        string='Last Interest Bill Date',
        help='Date of the most recent interest bill'
    )
    
    financing_ids = fields.One2many(
        'vehicle.financing',
        'product_id',
        string='Financing History',
    )
```

---

## 6. Overriding Existing Views

### Inheriting Form Views

```xml
<odoo>
    <data>
        <!-- Inherit and extend sale.order form view -->
        <record id="view_order_form_inherit_vehicle" model="ir.ui.view">
            <field name="name">sale.order.form.inherit.vehicle</field>
            <field name="model">sale.order</field>
            <field name="inherit_id" ref="sale.view_order_form"/>
            <field name="arch" type="xml">
                
                <!-- Add field after specific field -->
                <xpath expr="//field[@name='partner_id']" position="after">
                    <field name="linked_car" 
                           domain="[('categ_id.name', '=', 'Vehicles')]"
                           options="{'no_create': True}"/>
                </xpath>
                
                <!-- Add field inside a group -->
                <xpath expr="//group[@name='sale_header']" position="inside">
                    <field name="first_order_line_id"/>
                </xpath>
                
                <!-- Add new page to notebook -->
                <xpath expr="//notebook" position="inside">
                    <page string="Vehicle Information" name="vehicle_info">
                        <group>
                            <field name="linked_car"/>
                            <field name="first_order_line_id"/>
                        </group>
                    </page>
                </xpath>
                
                <!-- Replace existing field -->
                <xpath expr="//field[@name='date_order']" position="replace">
                    <field name="date_order" readonly="1"/>
                </xpath>
                
                <!-- Add attributes to existing field -->
                <xpath expr="//field[@name='partner_id']" position="attributes">
                    <attribute name="required">1</attribute>
                    <attribute name="domain">[('customer_rank', '>', 0)]</attribute>
                </xpath>
                
            </field>
        </record>
```

### Inheriting List Views

```xml
        <!-- Inherit and extend product.template list view -->
        <record id="view_product_template_tree_inherit" model="ir.ui.view">
            <field name="name">product.template.tree.inherit</field>
            <field name="model">product.template</field>
            <field name="inherit_id" ref="product.product_template_tree_view"/>
            <field name="arch" type="xml">
                
                <!-- Add field after list_price -->
                <xpath expr="//field[@name='list_price']" position="after">
                    <field name="vin" optional="hide"/>
                    <field name="year" optional="hide"/>
                    <field name="make" optional="show"/>
                    <field name="model" optional="show"/>
                    <field name="financing_status" 
                           widget="badge"
                           decoration-success="financing_status == 'paid_off'"
                           decoration-warning="financing_status == 'active'"/>
                </xpath>
                
            </field>
        </record>
    </data>
</odoo>
```

### XPath Position Options

```xml
<!-- Examples of different position attributes -->

<!-- 1. after: Add after the target element -->
<xpath expr="//field[@name='partner_id']" position="after">
    <field name="custom_field"/>
</xpath>

<!-- 2. before: Add before the target element -->
<xpath expr="//field[@name='partner_id']" position="before">
    <field name="custom_field"/>
</xpath>

<!-- 3. inside: Add inside the target element (at the end) -->
<xpath expr="//group[@name='sale_header']" position="inside">
    <field name="custom_field"/>
</xpath>

<!-- 4. replace: Replace the target element -->
<xpath expr="//field[@name='partner_id']" position="replace">
    <field name="partner_id" required="1"/>
</xpath>

<!-- 5. attributes: Modify attributes of target element -->
<xpath expr="//field[@name='partner_id']" position="attributes">
    <attribute name="required">1</attribute>
    <attribute name="invisible">1</attribute>
</xpath>

<!-- 6. move: Move the target element (Odoo 17+) -->
<xpath expr="//field[@name='partner_id']" position="move" target="//group[@name='other_group']"/>
```

---

## 7. Linking Custom Modules with Existing Modules

### Dependencies in `__manifest__.py`

```python
{
    'name': 'Car Dealer Customizations',
    'depends': [
        # Core modules
        'base',                           # Always required
        'mail',                           # For chatter and messaging
        
        # Business modules
        'sale',                           # Sales management
        'purchase',                       # Purchase management
        'account',                        # Accounting
        'stock',                          # Inventory
        'website',                        # Website functionality
        'website_sale',                   # eCommerce
        
        # Specialized modules
        'appointment',                    # Appointment scheduling
        'appointment_account_payment',    # Paid appointments
        'website_appointment_sale',       # Website appointment integration
        'analytic',                       # Analytic accounting
        'stock_landed_costs',            # Landed costs
        
        # Enterprise modules (if using Enterprise edition)
        'account_accountant',            # Advanced accounting
        'web_mobile',                     # Mobile interface
    ],
}
```

### Checking Module Dependencies at Runtime

```python
# In your model or method
def action_some_function(self):
    # Check if a module is installed
    if self.env['ir.module.module'].search([('name', '=', 'sale'), ('state', '=', 'installed')]):
        # Execute code that depends on 'sale' module
        pass
    
    # Or use try/except for model availability
    try:
        self.env['sale.order'].search([])
    except KeyError:
        raise UserError(_('Sales module is not installed'))
```

### External ID References

```xml
<!-- Reference views/actions from other modules -->

<!-- Reference a view from sale module -->
<record id="view_custom_form" model="ir.ui.view">
    <field name="inherit_id" ref="sale.view_order_form"/>
</record>

<!-- Reference a menu from account module -->
<menuitem id="menu_custom" 
          parent="account.menu_finance"
          action="action_custom"/>

<!-- Reference data from base module -->
<field name="partner_id" ref="base.res_partner_1"/>

<!-- Reference security group -->
<field name="group_id" ref="sales_team.group_sale_manager"/>
```

### Conditional Dependencies (Optional Modules)

```python
# models/conditional_feature.py
from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    def action_with_optional_module(self):
        """Method that works with or without optional module"""
        self.ensure_one()
        
        # Check if analytic module is available
        if 'analytic.account' in self.env:
            # Execute analytic-specific code
            analytic_account = self.env['analytic.account'].search([], limit=1)
            self.analytic_account_id = analytic_account
        else:
            # Fallback behavior
            pass
```

---

## 8. Security Configuration

### Access Rights (`ir.model.access.csv`)

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_vehicle_financing_user,vehicle.financing.user,model_vehicle_financing,base.group_user,1,1,1,0
access_vehicle_financing_manager,vehicle.financing.manager,model_vehicle_financing,base.group_system,1,1,1,1
access_vehicle_financing_sale_user,vehicle.financing.sale.user,model_vehicle_financing,sales_team.group_sale_user,1,1,1,0
access_vehicle_financing_sale_manager,vehicle.financing.sale.manager,model_vehicle_financing,sales_team.group_sale_manager,1,1,1,1
```

**Column meanings:**
- `id`: Unique identifier
- `name`: Description
- `model_id:id`: Model external ID (format: `model_<model_name_with_underscores>`)
- `group_id:id`: Security group external ID
- `perm_read`: Read permission (1=yes, 0=no)
- `perm_write`: Write permission
- `perm_create`: Create permission
- `perm_unlink`: Delete permission

### Record Rules (Row-Level Security)

```xml
<!-- security/vehicle_financing_security.xml -->
<odoo>
    <data noupdate="1">
        
        <!-- Users can only see their own financing records -->
        <record id="vehicle_financing_user_rule" model="ir.rule">
            <field name="name">User Own Financing Records</field>
            <field name="model_id" ref="model_vehicle_financing"/>
            <field name="domain_force">[('create_uid', '=', user.id)]</field>
            <field name="groups" eval="[(4, ref('base.group_user'))]"/>
        </record>
        
        <!-- Manager can see all financing records -->
        <record id="vehicle_financing_manager_rule" model="ir.rule">
            <field name="name">Manager All Financing Records</field>
            <field name="model_id" ref="model_vehicle_financing"/>
            <field name="domain_force">[(1, '=', 1)]</field>
            <field name="groups" eval="[(4, ref('base.group_system'))]"/>
        </record>
        
        <!-- Sales team can see records for their customers -->
        <record id="vehicle_financing_sales_rule" model="ir.rule">
            <field name="name">Sales Team Customer Financing</field>
            <field name="model_id" ref="model_vehicle_financing"/>
            <field name="domain_force">[('partner_id.user_id', '=', user.id)]</field>
            <field name="groups" eval="[(4, ref('sales_team.group_sale_user'))]"/>
        </record>
        
    </data>
</odoo>
```

### Custom Security Groups

```xml
<!-- security/security_groups.xml -->
<odoo>
    <data>
        
        <!-- Create custom security category -->
        <record id="module_category_vehicle_financing" model="ir.module.category">
            <field name="name">Vehicle Financing</field>
            <field name="description">Manage vehicle financing permissions</field>
            <field name="sequence">20</field>
        </record>
        
        <!-- Create custom groups -->
        <record id="group_vehicle_financing_user" model="res.groups">
            <field name="name">User</field>
            <field name="category_id" ref="module_category_vehicle_financing"/>
            <field name="implied_ids" eval="[(4, ref('base.group_user'))]"/>
        </record>
        
        <record id="group_vehicle_financing_manager" model="res.groups">
            <field name="name">Manager</field>
            <field name="category_id" ref="module_category_vehicle_financing"/>
            <field name="implied_ids" eval="[(4, ref('group_vehicle_financing_user'))]"/>
            <field name="users" eval="[(4, ref('base.user_root')), (4, ref('base.user_admin'))]"/>
        </record>
        
    </data>
</odoo>
```

---

## 9. Controllers

### Basic Controller

```python
# controller/__init__.py
from . import web_appointment

# controller/web_appointment.py
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class VehicleController(http.Controller):
    """Controller for vehicle-related web requests"""
    
    @http.route('/vehicle/list', type='http', auth='public', website=True)
    def vehicle_list(self, **kwargs):
        """Display list of available vehicles"""
        vehicles = request.env['product.template'].sudo().search([
            ('categ_id.name', '=', 'Vehicles'),
            ('website_published', '=', True),
        ])
        return request.render('your_module.vehicle_list_template', {
            'vehicles': vehicles,
        })
    
    @http.route('/vehicle/<int:vehicle_id>', type='http', auth='public', website=True)
    def vehicle_detail(self, vehicle_id, **kwargs):
        """Display vehicle details"""
        vehicle = request.env['product.template'].sudo().browse(vehicle_id)
        if not vehicle.exists():
            return request.not_found()
        
        return request.render('your_module.vehicle_detail_template', {
            'vehicle': vehicle,
        })
    
    @http.route('/vehicle/reserve', type='json', auth='user', methods=['POST'])
    def vehicle_reserve(self, vehicle_id, **kwargs):
        """JSON endpoint for vehicle reservation"""
        try:
            vehicle = request.env['product.template'].browse(int(vehicle_id))
            if not vehicle.exists():
                return {'error': 'Vehicle not found'}
            
            # Create reservation logic
            reservation = request.env['calendar.booking'].create({
                'vehicle_template_id': vehicle.id,
                'partner_id': request.env.user.partner_id.id,
            })
            
            return {
                'success': True,
                'reservation_id': reservation.id,
            }
        except Exception as e:
            _logger.error('Error reserving vehicle: %s', e)
            return {'error': str(e)}
```

### Inheriting Existing Controllers

```python
# controller/website_sale.py
from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale
import logging

_logger = logging.getLogger(__name__)


class WebsiteSaleExtended(WebsiteSale):
    """Extend website_sale controller"""
    
    @http.route()
    def cart(self, **post):
        """Override cart method to add custom logic"""
        # Call parent method
        response = super(WebsiteSaleExtended, self).cart(**post)
        
        # Add custom data to response context
        if hasattr(response, 'qcontext'):
            order = response.qcontext.get('website_sale_order')
            if order:
                # Add vehicle information to cart
                vehicle_lines = order.order_line.filtered(
                    lambda l: l.product_id.categ_id.name == 'Vehicles'
                )
                response.qcontext['vehicle_lines'] = vehicle_lines
        
        return response
    
    @http.route('/shop/cart/update', type='http', auth='public', methods=['POST'], website=True, csrf=False)
    def cart_update(self, product_id, add_qty=1, set_qty=0, **kwargs):
        """Override cart update to add vehicle-specific logic"""
        # Check if product is a vehicle
        product = request.env['product.product'].sudo().browse(int(product_id))
        
        if product.categ_id.name == 'Vehicles':
            # Check if vehicle is available
            if not product.website_published:
                return request.redirect('/shop?error=vehicle_unavailable')
        
        # Call parent method
        return super(WebsiteSaleExtended, self).cart_update(
            product_id=product_id,
            add_qty=add_qty,
            set_qty=set_qty,
            **kwargs
        )
```

---

## 10. Best Practices

### Code Organization

1. **One model per file**: Keep each model in its own file
2. **Logical naming**: Use descriptive names for files and variables
3. **Import order**: Standard library → Odoo → Local imports
4. **Comments**: Add docstrings to all classes and complex methods

```python
# Good structure
from datetime import datetime, timedelta  # Standard library
from odoo import api, fields, models, _   # Odoo
from odoo.exceptions import UserError     # Odoo exceptions
from .vehicle_utils import calculate_interest  # Local imports
```

### Field Naming Conventions

- **Many2one**: End with `_id` (e.g., `partner_id`, `product_id`)
- **One2many/Many2many**: End with `_ids` (e.g., `line_ids`, `tag_ids`)
- **Booleans**: Start with `is_` or `has_` (e.g., `is_active`, `has_financing`)
- **Dates**: Use `_date` suffix (e.g., `start_date`, `bill_date`)
- **Datetimes**: Use `_datetime` suffix (e.g., `create_datetime`)

### Performance Optimization

```python
# Bad: Multiple database calls in loop
for order in orders:
    partner = order.partner_id  # DB query for each order
    print(partner.name)

# Good: Prefetch related records
orders = orders.with_prefetch()  # or
orders = self.env['sale.order'].search([...])
for order in orders:
    print(order.partner_id.name)  # No additional DB queries

# Bad: Repeated searches
for product in products:
    financing = self.env['vehicle.financing'].search([('product_id', '=', product.id)])

# Good: Single search with grouped results
financings = self.env['vehicle.financing'].search([
    ('product_id', 'in', products.ids)
])
financing_by_product = {f.product_id.id: f for f in financings}
```

### Error Handling

```python
from odoo.exceptions import UserError, ValidationError, AccessError

def action_confirm(self):
    """Confirm with proper error handling"""
    self.ensure_one()  # Ensure single record
    
    # Validation
    if not self.partner_id:
        raise ValidationError(_('Partner is required'))
    
    # User error (business logic)
    if self.state != 'draft':
        raise UserError(_('Only draft orders can be confirmed'))
    
    # Access control
    if not self.env.user.has_group('sales_team.group_sale_manager'):
        raise AccessError(_('Only sales managers can confirm'))
    
    try:
        self.state = 'confirmed'
    except Exception as e:
        _logger.error('Error confirming order %s: %s', self.name, e)
        raise UserError(_('Unable to confirm order: %s') % str(e))
```

### Logging

```python
import logging

_logger = logging.getLogger(__name__)

class VehicleFinancing(models.Model):
    _name = 'vehicle.financing'
    
    def action_post(self):
        # Debug level: Detailed information for debugging
        _logger.debug('Posting financing %s with amount %s', self.name, self.interest_amount)
        
        # Info level: General informational messages
        _logger.info('Financing %s posted successfully', self.name)
        
        # Warning level: Warning messages
        if not self.bill_id:
            _logger.warning('Financing %s posted without bill', self.name)
        
        # Error level: Error messages
        try:
            self._create_bill()
        except Exception as e:
            _logger.error('Error creating bill for financing %s: %s', self.name, e)
            raise
```

### Translation Support

```python
from odoo import _

# In Python code
raise UserError(_('Vehicle financing cannot be negative'))
error_msg = _('Unable to process payment for %s') % self.name

# In XML views
<button string="Confirm" />  # Will be translated automatically
<field name="name" string="Reference"/>
```

```xml
<!-- In XML templates -->
<t t-esc="'Hello'"/>  <!-- Not translated -->
<t t-esc="_t('Hello')"/>  <!-- Translated -->
```

### Testing

```python
# tests/__init__.py
from . import test_vehicle_financing

# tests/test_vehicle_financing.py
from odoo.tests import tagged, TransactionCase
from odoo.exceptions import UserError

@tagged('post_install', '-at_install')
class TestVehicleFinancing(TransactionCase):
    
    def setUp(self):
        super(TestVehicleFinancing, self).setUp()
        self.product = self.env['product.template'].create({
            'name': 'Test Vehicle',
            'list_price': 25000.00,
        })
    
    def test_create_financing(self):
        """Test financing record creation"""
        financing = self.env['vehicle.financing'].create({
            'product_id': self.product.id,
            'bill_date': '2026-01-01',
            'interest_amount': 500.00,
        })
        self.assertEqual(financing.state, 'draft')
        self.assertEqual(financing.product_id, self.product)
    
    def test_confirm_financing(self):
        """Test financing confirmation"""
        financing = self.env['vehicle.financing'].create({
            'product_id': self.product.id,
            'bill_date': '2026-01-01',
            'interest_amount': 500.00,
        })
        financing.action_confirm()
        self.assertEqual(financing.state, 'confirmed')
    
    def test_negative_amount_raises_error(self):
        """Test that negative amounts raise validation error"""
        with self.assertRaises(ValidationError):
            self.env['vehicle.financing'].create({
                'product_id': self.product.id,
                'bill_date': '2026-01-01',
                'interest_amount': -500.00,
            })
```

---

## Summary

This guide covers the essential aspects of Odoo 19 custom module development:

1. **Module Structure**: Proper organization of files and folders
2. **Creating Models**: New models, transient models, and field types
3. **Creating Views**: Forms, lists, kanban, search views, and actions
4. **Overriding Models**: Inheriting and extending existing models
5. **Overriding Views**: XPath inheritance patterns
6. **Linking Modules**: Dependencies and external references
7. **Security**: Access rights, record rules, and custom groups
8. **Controllers**: HTTP routes and JSON endpoints
9. **Best Practices**: Code organization, performance, error handling

For more information, refer to the official Odoo documentation at https://www.odoo.com/documentation/19.0/
