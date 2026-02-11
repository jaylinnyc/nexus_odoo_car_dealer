# Nexus Odoo Car Dealer Module - Complete Documentation

## Module Information
- **Module Name**: nexus_odoo_car_dealer
- **Version**: 1.0.19
- **Odoo Version**: 19.0 Enterprise Edition
- **Author**: Nexus
- **License**: LGPL-3
- **Category**: Sales/Automotive

---

## Table of Contents
1. [Module Purpose](#module-purpose)
2. [Key Features](#key-features)
3. [Models and Their Responsibilities](#models-and-their-responsibilities)
4. [Views and UI Components](#views-and-ui-components)
5. [Controllers](#controllers)
6. [External Module Dependencies](#external-module-dependencies)
7. [Data Files and Automation](#data-files-and-automation)
8. [How to Make Changes](#how-to-make-changes)
9. [Code Reading Order](#code-reading-order)
10. [Common Customization Scenarios](#common-customization-scenarios)

---

## 1. Module Purpose

The **Nexus Odoo Car Dealer** module is a comprehensive solution designed specifically for automotive dealerships running on Odoo 19 Enterprise Edition. It transforms Odoo into a complete car dealership management system.

### Primary Objectives:

1. **Vehicle Management**: Track vehicles with extended automotive-specific fields (VIN, Make, Model, Year, Mileage)

2. **Reservation System**: Enable customers to reserve vehicles through online appointment booking with paid or free appointments

3. **Floor Plan Financing**: Manage vehicle inventory financing (floor plan) with automatic interest calculation and bill generation

4. **Purchase Tracking**: Track vehicle purchases from vendors with automatic analytic account creation for cost tracking

5. **Sales Integration**: Seamlessly integrate vehicle reservations with the sales process, linking appointments to sales orders

6. **Financial Management**: Handle financing agreements, top-ups, pay-downs, and automatic monthly interest billing

---

## 2. Key Features

### ✅ Vehicle Reservation System
- Online appointment booking for viewing reserved vehicles
- Vehicle reservation status tracking (Available/Reserved)
- Integration with website appointment booking
- Automatic vehicle unpublishing after purchase confirmation

### ✅ Floor Plan Financing Management
- Track vehicle financing from banks or internal sources
- Support for multiple financing agreements with different lenders
- Automatic monthly interest calculation and bill generation
- Financing top-up and pay-down wizards
- Complete transaction history tracking

### ✅ Vehicle-Specific Fields
- Make, Model, Year, VIN, Mileage
- Reservation status and customer tracking
- Financing status and balance tracking
- Analytic account integration for cost tracking

### ✅ Sales Order Integration
- First order line computation for quick access
- Vehicle linking to sales orders
- Appointment-to-cart flow with vehicle details
- Automatic vehicle status updates on sale confirmation

### ✅ Purchase Order Integration
- Automatic analytic account creation per vehicle
- Vendor bill tracking and synchronization
- Total cost calculation (including landed costs)

### ✅ Accounting Integration
- Automatic journal entries for financing transactions
- Interest expense tracking
- Vendor bill date synchronization with accounting date

---

## 3. Models and Their Responsibilities

### 3.1 Core Models

#### **vehicle.financing** (`models/vehicle_financing.py`)
**Purpose**: Track individual interest bills for financed vehicles

**Key Fields**:
- `product_id`: Link to the vehicle (product.template)
- `bill_date`: Date of the interest bill
- `interest_amount`: Amount of interest charged
- `bill_id`: Link to the generated vendor bill
- `agreement_line_id`: Link to financing agreement line

**Key Methods**:
- `unlink()`: Delete bill and update vehicle's last interest date

**Responsibility**: Records each monthly interest bill generated for a financed vehicle and maintains the connection between the financing record and the vendor bill.

---

#### **vehicle.financing.transaction** (`models/vehicle_financing.py`)
**Purpose**: Track all financing transactions (initial, top-up, pay-down, interest, reversals)

**Key Fields**:
- `product_id`: Vehicle being financed
- `transaction_type`: initial/topup/paydown/interest/reversal
- `amount`: Transaction amount
- `balance_after`: Vehicle balance after transaction
- `journal_entry_id`: Link to accounting entry
- `is_reversed`: Whether transaction was reversed
- `reversed_by_id`: Reversing transaction reference
- `reverses_id`: Original transaction being reversed

**Key Methods**:
- `action_reverse_transaction()`: Reverse a top-up or pay-down with journal entry
- `create()`: Automatically compute balance after transaction

**Responsibility**: Maintains complete audit trail of all financing activities with accounting integration.

---

#### **financing.agreement** (`models/financing_agreement.py`)
**Purpose**: Group multiple vehicles under a single financing agreement with a lender

**Key Fields**:
- `partner_id`: Lender/Bank partner
- `agreement_date`: Date agreement was signed
- `line_ids`: One2many to financing.agreement.line (vehicles)
- `total_financed_amount`: Sum of all vehicle financing
- `total_balance`: Current total balance
- `state`: draft/active/closed/cancelled

**Key Methods**:
- `action_activate()`: Activate agreement and create all vehicle financing
- `action_generate_interest_bills()`: Generate monthly interest for all active vehicles
- `unlink()`: Clean up all related transactions and journal entries

**Responsibility**: Manages the relationship between dealership and financing partner, allowing bulk operations on multiple vehicles financed by the same lender.

---

#### **financing.agreement.line** (`models/financing_agreement.py`)
**Purpose**: Represents one vehicle in a financing agreement

**Key Fields**:
- `agreement_id`: Parent financing agreement
- `vehicle_id`: The financed vehicle (product.template)
- `financed_amount`: Original loan amount
- `current_balance`: Outstanding balance
- `accumulated_interest`: Total interest paid to date
- `monthly_interest_rate`: Interest rate per month
- `journal_entry_id`: Initial financing journal entry

**Key Methods**:
- `action_generate_interest_bill()`: Generate one month's interest bill
- `action_topup_balance()`: Open wizard to add to loan balance
- `action_paydown_balance()`: Open wizard to reduce loan balance

**Responsibility**: Tracks individual vehicle financing within an agreement, maintains balance, and handles interest calculations.

---

#### **product.template** (Extended - `models/product_template.py`)
**Purpose**: Extend standard product to support vehicle-specific features

**Vehicle-Specific Fields**:
- `make`, `model`, `year`, `vin`, `mileage`: Vehicle attributes
- `reservation_status`: available/reserved
- `reserved_by_partner_id`: Customer who reserved
- `reservation_date`: When reservation was made
- `financing_type`: none/internal/external
- `financing_amount`, `financing_rate`, `financing_balance`: Financing details
- `financing_status`: active/paid_off
- `analytic_account_id`: Cost tracking account

**Key Methods**:
- `action_unreserve_vehicle()`: Remove reservation and make available
- `action_view_financing_history()`: View all interest bills
- `action_view_transactions()`: View all financing transactions
- `_cron_generate_monthly_interest_bills()`: Scheduled job to generate interest
- `_compute_vendor_bill_info()`: Calculate total purchase costs

**Responsibility**: Serves as the central vehicle record with all automotive-specific data, reservation status, and financing information.

---

#### **sale.order** (Extended - `models/sale_order.py`)
**Purpose**: Connect vehicle reservations to sales orders

**Additional Fields**:
- `first_order_line_id`: Computed field pointing to first line
- `linked_car`: Direct link to vehicle product

**Key Methods**:
- `_prepare_order_line_values()`: Add vehicle info from appointment booking
- `action_confirm()`: Mark vehicle as sold and update financing status

**Responsibility**: Links appointment-based vehicle reservations to sales orders and updates vehicle status when sale is confirmed.

---

#### **calendar.event** (Extended - `models/calendar_event.py`)
**Purpose**: Store vehicle reservation information in appointments

**Additional Fields**:
- `vehicle_template_id`: Reserved vehicle
- `sale_order_id`: Computed link to sales order

**Key Methods**:
- `action_confirm_reservation_and_unpublish_product()`: Mark vehicle as reserved

**Responsibility**: Connects appointment bookings to specific vehicles and manages reservation confirmation.

---

#### **calendar.booking** (Extended - `models/calendar_booking.py`)
**Purpose**: Handle paid appointment bookings for vehicle viewings

**Additional Fields**:
- `vehicle_template_id`: Vehicle being reserved

**Key Methods**:
- `_make_event_from_paid_booking()`: Transfer vehicle to event after payment

**Responsibility**: Handles the paid appointment workflow, transferring vehicle information to calendar.event after payment confirmation.

---

#### **purchase.order.line** (Extended - `models/purchase_order_line.py`)
**Purpose**: Auto-create analytic accounts for vehicle purchases

**Key Methods**:
- `_create_analytic_account_for_vehicle()`: Create/assign analytic account
- `_get_vehicle_project_name()`: Generate descriptive project name

**Responsibility**: Automatically sets up cost tracking for each purchased vehicle by creating an analytic account (project).

---

#### **account.move** (Extended - `models/account_move.py`)
**Purpose**: Synchronize vendor bill dates with accounting dates

**Key Methods**:
- `_onchange_invoice_date_sync_accounting()`: Sync dates on change
- `create()`: Sync dates on creation
- `write()`: Sync dates on update

**Responsibility**: Ensures vendor bill dates always match accounting dates for accurate financial reporting.

---

### 3.2 Wizard Models (Transient)

#### **financing.agreement.wizard** (`models/financing_agreement_wizard.py`)
**Purpose**: Wizard to create financing agreements with multiple vehicles

**Key Fields**:
- `partner_id`: Lender/Bank
- `agreement_date`: Agreement date
- `line_ids`: One2many wizard lines

**Key Methods**:
- `action_create_agreement()`: Create agreement from wizard data

---

#### **vehicle.financing.topup.wizard** (`models/vehicle_financing.py`)
**Purpose**: Wizard to increase vehicle financing balance

**Key Methods**:
- `action_topup()`: Process top-up and create journal entry

---

#### **vehicle.financing.paydown.wizard** (`models/vehicle_financing.py`)
**Purpose**: Wizard to reduce vehicle financing balance

**Key Methods**:
- `action_paydown()`: Process pay-down and create journal entry

---

## 4. Views and UI Components

### 4.1 Vehicle Financing Views

**File**: `views/financing_views.xml`

- **List View** (`view_vehicle_financing_tree`): Shows all interest bills
- **Form View** (`view_vehicle_financing_form`): Interest bill details (read-only)
- **Transaction List** (`view_vehicle_financing_transaction_tree`): All financing transactions with reverse button
- **Transaction Form** (`view_vehicle_financing_transaction_form`): Transaction details with journal entry access

### 4.2 Financing Agreement Views

**File**: `views/financing_agreement_views.xml`

- **List View** (`view_financing_agreement_tree`): All financing agreements with totals
- **Form View** (`view_financing_agreement_form`): 
  - Header with state workflow buttons
  - Smart buttons (Vehicles, Bills, Journal Entries, Transactions)
  - Financing agreement lines with inline actions
  - Notebook tabs for transactions, interest bills, accounting entries
- **Search View**: Filters by state, lender, date
- **Custom List View** (JavaScript): Custom rendering with icons and buttons

### 4.3 Reservation Views

**File**: `views/reservation_views.xml`

- **Product Form Extension** (`view_product_template_reservation_form`):
  - Reserved banner at top of form
  - Unreserve button
  - Reservation status group with customer and date
- **Reserved Vehicles Action**: Lists all reserved vehicles
- **Menu Item**: Under Sales menu

### 4.4 Vehicle Show Views

**File**: `views/vehicle_show.xml`

- **Product Form Extension**: Vehicle-specific fields (Make, Model, Year, VIN, Mileage)
- **Financing Section**: Complete financing information
- **Smart Buttons**: Purchase orders, vendor bills, financing history, transactions

### 4.5 Cart Integration

**File**: `views/cart_vehicle_info.xml`

- QWeb template to display vehicle information in shopping cart

### 4.6 Wizard Views

**Files**: 
- `views/financing_agreement_wizard_views.xml`: Agreement creation wizard
- `views/financing_topup_wizard.xml`: Top-up wizard
- `views/financing_paydown_wizard.xml`: Pay-down wizard

---

## 5. Controllers

### 5.1 WebsiteAppointmentExtended

**File**: `controller/web_appointment.py`

**Parent Class**: `AppointmentAccountPayment` (from appointment_account_payment module)

**Key Routes & Methods**:

1. **`_check_vehicle_already_in_cart(vehicle_template_id)`**
   - Checks if vehicle is already in cart
   - Returns existing SOL if found
   - Purpose: Prevent duplicate vehicle reservations

2. **`appointment_form(appointment_type_id, **kwargs)`**
   - Override to pass vehicle_template_id through appointment flow
   - Adds vehicle to URL parameters
   - Purpose: Maintain vehicle context throughout booking

3. **`appointment_create_meeting(appointment_type_id, **kwargs)`**
   - Override to store vehicle_template_id in calendar.booking
   - Purpose: Link vehicle to appointment before payment

4. **`appointment_validate_booking(booking_data, bookingId)`**
   - Override to add vehicle to cart from calendar.event
   - Creates cart with vehicle details if doesn't exist
   - Purpose: Add vehicle to cart after appointment payment confirmation

**Responsibility**: Manages the complete vehicle reservation flow from website through appointment booking to cart addition.

---

## 6. External Module Dependencies

### 6.1 Core Odoo Modules (Required)

| Module | Purpose | Integration Points |
|--------|---------|-------------------|
| **base** | Foundation | Partners, Companies, Users |
| **mail** | Messaging | Chatter on financing agreements |
| **sale** | Sales Management | Sale orders, order lines, vehicle linking |
| **website** | Website Framework | Online vehicle browsing |
| **website_sale** | eCommerce | Shopping cart, vehicle purchase flow |

### 6.2 Appointment Modules (Required)

| Module | Purpose | Integration Points |
|--------|---------|-------------------|
| **appointment** | Appointment Booking | Vehicle viewing appointments |
| **appointment_account_payment** | Paid Appointments | Payment before viewing reserved vehicles |
| **website_appointment_sale** | Web Appointment Integration | Online vehicle reservation booking |

**Why**: These modules enable customers to book appointments to view specific vehicles online, with payment collection before reservation confirmation.

**How**: 
- Controller extends `AppointmentAccountPayment`
- `calendar.event` and `calendar.booking` extended with `vehicle_template_id`
- Appointment resources and types configured in `data/appointment_data.xml`

### 6.3 Purchase & Inventory Modules (Required)

| Module | Purpose | Integration Points |
|--------|---------|-------------------|
| **purchase** | Purchase Management | Vehicle acquisition tracking |
| **purchase_stock** | Purchase-Stock Link | Inventory receipt of vehicles |
| **stock_landed_costs** | Landed Costs | Additional vehicle costs (shipping, customs) |

**Why**: Track vehicle purchases from vendors/auctions with complete cost visibility.

**How**:
- `purchase.order.line` extended to create analytic accounts
- `product.template` computes total costs from purchase bills
- Landed costs added to vehicle's analytic account

### 6.4 Accounting Modules (Required)

| Module | Purpose | Integration Points |
|--------|---------|-------------------|
| **account** | Accounting | Vendor bills, journal entries, accounts |
| **analytic** | Analytic Accounting | Per-vehicle cost tracking |

**Why**: 
- Track all costs per vehicle using analytic accounts
- Generate journal entries for financing transactions
- Manage interest expense and floor plan liability accounts

**How**:
- Custom accounts created: Interest Payable, Floor Plan Payable
- Journal entries auto-created for financing top-ups/pay-downs
- Each vehicle gets an analytic account for cost aggregation
- `account.move` extended to sync bill dates

### 6.5 Payment Module (Required)

| Module | Purpose | Integration Points |
|--------|---------|-------------------|
| **payment** | Payment Processing | Appointment payment collection |

**Why**: Process online payments for paid vehicle viewing appointments.

---

## 7. Data Files and Automation

### 7.1 Accounting Data

**File**: `data/account_data.xml`

**Contents**:
- **Interest Payable Account** (`account_interest_payable`): Liability account for accrued interest
- **Floor Plan Payable Account** (`account_floor_plan_payable`): Liability account for vehicle financing

**Purpose**: Create specialized accounts for dealership floor plan financing.

### 7.2 Tax Data

**File**: `data/tax_data.xml`

**Contents**: Custom tax configurations for vehicle sales (if applicable)

### 7.3 Appointment Data

**File**: `data/appointment_data.xml`

**Contents**:
- **Reservation Product**: Service product for appointment booking
- **Showroom Resource**: Appointment resource with capacity
- **Vehicle Reservation Appointment Type**: Configured appointment type

**Purpose**: Enable online booking for vehicle viewings.

### 7.4 Scheduled Actions (Cron Jobs)

**File**: `data/financing_cron.xml`

**Job**: Generate Monthly Interest Bills
- **Model**: product.template
- **Method**: `_cron_generate_monthly_interest_bills()`
- **Frequency**: Daily
- **Purpose**: Automatically generate interest bills on the 1st of each month for all active financed vehicles

---

## 8. How to Make Changes

### 8.1 Prerequisites

Before making changes:
1. Ensure you're on the correct git branch
2. Understand the affected module's purpose
3. Check dependencies to avoid breaking linked modules
4. Review existing code patterns

### 8.2 Development Workflow

```bash
# 1. Create a feature branch
git switch -c feature/description

# 2. Make your changes (see sections below)

# 3. Update the module
# In Odoo: Apps > Your Module > Upgrade

# 4. Test thoroughly
# - Test affected features
# - Check for errors in log
# - Verify accounting entries

# 5. Commit changes
git add .
git commit -m "Description of changes"

# 6. Push to repository
git push origin feature/description
```

### 8.3 Module Upgrade After Changes

After modifying files, upgrade the module in Odoo:
1. Go to Apps menu
2. Remove "Apps" filter, search for "nexus_odoo_car_dealer"
3. Click "Upgrade" button
4. Clear browser cache (Ctrl+Shift+R)

---

## 9. Code Reading Order

When learning or modifying this module, follow this order:

### Phase 1: Foundation (Start Here)
1. **`__manifest__.py`** - Understand dependencies and module structure
2. **`README.md`** - High-level overview
3. **`models/__init__.py`** - See all model files

### Phase 2: Core Vehicle Management
4. **`models/product_template.py`** - Vehicle fields and financing basics
5. **`views/vehicle_show.xml`** - UI for vehicle management
6. **`views/reservation_views.xml`** - Reservation UI

### Phase 3: Financing System
7. **`models/vehicle_financing.py`** - Interest bills and transactions
8. **`models/financing_agreement.py`** - Agreements and lines
9. **`views/financing_views.xml`** - Financing UI
10. **`views/financing_agreement_views.xml`** - Agreement UI
11. **`data/financing_cron.xml`** - Automated interest generation

### Phase 4: Sales Integration
12. **`models/sale_order.py`** - Sales order extensions
13. **`models/calendar_event.py`** - Appointment integration
14. **`models/calendar_booking.py`** - Paid appointment handling
15. **`controller/web_appointment.py`** - Reservation flow controller
16. **`views/cart_vehicle_info.xml`** - Cart display

### Phase 5: Purchase & Accounting
17. **`models/purchase_order_line.py`** - Purchase integration
18. **`models/account_move.py`** - Accounting extensions
19. **`data/account_data.xml`** - Chart of accounts

### Phase 6: Frontend Assets
20. **`static/src/views/financing_agreement_list_view.js`** - Custom JS
21. **`static/src/views/financing_agreement_list_view.xml`** - Custom templates

---

## 10. Common Customization Scenarios

### 10.1 Adding New Vehicle Fields

**Files to Modify**:
1. `models/product_template.py` - Add field definition
2. `views/vehicle_show.xml` - Add field to form view
3. `security/ir.model.access.csv` - If creating new model

**Example**:
```python
# In product_template.py
color = fields.Char(string='Color')
interior_color = fields.Char(string='Interior Color')
transmission = fields.Selection([
    ('automatic', 'Automatic'),
    ('manual', 'Manual'),
], string='Transmission')
```

```xml
<!-- In vehicle_show.xml -->
<xpath expr="//field[@name='year']" position="after">
    <field name="color"/>
    <field name="interior_color"/>
    <field name="transmission"/>
</xpath>
```

### 10.2 Modifying Interest Calculation

**File**: `models/financing_agreement.py` (FinancingAgreementLine class)

**Method**: `action_generate_interest_bill()`

**Example**: Change from simple to compound interest
```python
def action_generate_interest_bill(self):
    # Current: Simple interest
    interest = self.current_balance * (self.monthly_interest_rate / 100)
    
    # Change to: Compound interest with daily compounding
    days_in_month = 30
    daily_rate = self.monthly_interest_rate / 100 / days_in_month
    interest = self.current_balance * ((1 + daily_rate) ** days_in_month - 1)
```

### 10.3 Adding Custom Appointment Validation

**File**: `controller/web_appointment.py`

**Method**: `appointment_validate_booking()`

**Example**: Check if customer is approved for financing
```python
def appointment_validate_booking(self, booking_data, bookingId):
    result = super().appointment_validate_booking(booking_data, bookingId)
    
    # Add custom validation
    booking = request.env['calendar.booking'].sudo().browse(bookingId)
    if booking.vehicle_template_id:
        customer = booking.partner_id
        if not customer.credit_approved:
            return {'error': 'Customer must be pre-approved for financing'}
    
    return result
```

### 10.4 Customizing Financing Agreement Workflow

**File**: `models/financing_agreement.py`

**Add new state**:
```python
state = fields.Selection([
    ('draft', 'Draft'),
    ('pending_approval', 'Pending Approval'),  # NEW
    ('active', 'Active'),
    ('closed', 'Closed'),
    ('cancelled', 'Cancelled')
], string='Status', default='draft', tracking=True)

def action_submit_for_approval(self):
    """Submit agreement for manager approval"""
    self.state = 'pending_approval'
    # Send notification to manager
    self.activity_schedule(...)

def action_approve(self):
    """Manager approves agreement"""
    if not self.env.user.has_group('base.group_system'):
        raise AccessError(_('Only managers can approve'))
    self.action_activate()
```

### 10.5 Adding Smart Button to Product

**File**: `views/vehicle_show.xml`

**Example**: Add button to view sale history
```xml
<xpath expr="//div[@name='button_box']" position="inside">
    <button class="oe_stat_button" 
            type="object" 
            name="action_view_sale_history"
            icon="fa-shopping-cart">
        <field name="sale_count" widget="statinfo" string="Sales"/>
    </button>
</xpath>
```

```python
# In product_template.py
sale_count = fields.Integer(compute='_compute_sale_count')

def _compute_sale_count(self):
    for product in self:
        product.sale_count = self.env['sale.order.line'].search_count([
            ('product_id', 'in', product.product_variant_ids.ids),
            ('state', '=', 'sale')
        ])

def action_view_sale_history(self):
    return {
        'type': 'ir.actions.act_window',
        'name': 'Sale History',
        'res_model': 'sale.order',
        'view_mode': 'tree,form',
        'domain': [('order_line.product_id', 'in', self.product_variant_ids.ids)],
    }
```

### 10.6 Modifying Automated Interest Bill Generation

**File**: `models/product_template.py`

**Method**: `_cron_generate_monthly_interest_bills()`

**Example**: Skip weekends
```python
@api.model
def _cron_generate_monthly_interest_bills(self):
    from datetime import datetime
    today = fields.Date.today()
    
    # Skip if weekend
    if datetime.now().weekday() in [5, 6]:  # Saturday, Sunday
        _logger.info("Skipping interest generation on weekend")
        return
    
    # Continue with existing logic...
```

### 10.7 Adding Report

Create new file: `report/vehicle_financing_report.xml`

```xml
<odoo>
    <template id="report_vehicle_financing">
        <t t-call="web.html_container">
            <t t-foreach="docs" t-as="o">
                <t t-call="web.external_layout">
                    <div class="page">
                        <h2>Financing Statement</h2>
                        <div class="row">
                            <div class="col-6">
                                <strong>Vehicle:</strong>
                                <span t-field="o.vehicle_id.display_name"/>
                            </div>
                            <div class="col-6">
                                <strong>Balance:</strong>
                                <span t-field="o.current_balance"/>
                            </div>
                        </div>
                        <!-- More content -->
                    </div>
                </t>
            </t>
        </t>
    </template>
    
    <record id="action_report_vehicle_financing" model="ir.actions.report">
        <field name="name">Financing Statement</field>
        <field name="model">financing.agreement.line</field>
        <field name="report_type">qweb-pdf</field>
        <field name="report_name">nexus_odoo_car_dealer.report_vehicle_financing</field>
        <field name="binding_model_id" ref="model_financing_agreement_line"/>
        <field name="binding_type">report</field>
    </record>
</odoo>
```

Don't forget to add to `__manifest__.py`:
```python
'data': [
    ...
    'report/vehicle_financing_report.xml',
],
```

---

## Summary

This module provides a complete car dealership solution with:
- ✅ Vehicle inventory management with automotive fields
- ✅ Online reservation system with appointment booking
- ✅ Floor plan financing with automatic interest billing
- ✅ Complete accounting integration
- ✅ Purchase and cost tracking per vehicle
- ✅ Sales order integration with vehicle linking

**Key Integration Points**:
- Appointment modules for reservations
- Accounting modules for financial tracking
- Purchase modules for acquisition
- Website modules for online presence

**When Making Changes**:
1. Follow the code reading order to understand context
2. Test all related features after modifications
3. Verify accounting entries are correct
4. Update module in Odoo after file changes
5. Check logs for errors or warnings

For detailed Odoo 19 development guidance, refer to [ODOO_19_DEVELOPMENT_GUIDE.md](ODOO_19_DEVELOPMENT_GUIDE.md).
