{
    'name': 'Car Dealer Customizations',
    'summary': 'Car dealer enhancements: first order line field, vehicle management, etc.',
    'version': '1.0.19',
    'license': 'LGPL-3',
    'category': 'Sales/Sales',          # or 'Automotive' if you prefer
    'description': """
Car Dealer Customizations
=========================
- Adds first_order_line_id computed field on Sales Orders
- Vehicle management (if you added models)
- Custom sale order views, templates, reports, etc.
- All car dealership specific features
    """,
    'author': 'nexus',
    'website': 'https://mynexussolution.com',

    # IMPORTANT: Add all modules you now depend on
    'depends': [
        'base',
        'sale',              # needed for sale.order, sale.order.line
        'website',
        'website_sale',
        'payment',
        'mail',
        'appointment',
        'appointment_account_payment',  # for paid appointment flow
        'website_appointment_sale',
        'purchase',          # for vehicle purchase tracking
        'purchase_stock',    # for purchase operations
        'analytic',          # for analytic accounting
        'stock_landed_costs', # landed costs module
        'account',           # for bill date sync
    ],

    # All your files — add every folder/file you have
    'data': [
        # Security
        'security/ir.model.access.csv',

        # Data
        'data/account_data.xml',
        'data/tax_data.xml',
        'data/appointment_data.xml',
        'data/financing_cron.xml',
        'data/migration_action.xml',

        # Views
        'views/test.xml',
        'views/vehicle_show.xml',
        'views/financing_views.xml',
        'views/financing_topup_wizard.xml',
        'views/financing_paydown_wizard.xml',
        'views/reserve_now_btn.xml',
        'views/cart_vehicle_info.xml',
        'views/reservation_views.xml',
        'views/financing_agreement_views.xml',
        'views/financing_agreement_wizard_views.xml',
    ],

    # Only if you created new models and want demo data
    # 'demo': [
    #     'demo/demo_data.xml',
    # ],

    'installable': True,
    'application': True,         # ← set to True because this is now a real app
    'auto_install': False,
    'sequence': 100,
}