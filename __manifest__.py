{
    'name': 'Car Dealer Customizations',
    'summary': 'Car dealer enhancements: first order line field, vehicle management, etc.',
    'version': '1.0.0',
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
        'website_appointment_sale'
        # 'stock',           # uncomment if you added vehicle stock/lots
        # 'account',         # if you touch invoices
    ],

    # All your files — add every folder/file you have
    'data': [
        # Security (add if you created any)

        # Views
        # 'views/reservation_sequence.xml',
        'data/appointment_data.xml',
        'views/test.xml',
        # your existing website templates
        # 'views/vehicle_views.xml',        # if you added vehicle model

        # Reports / QWeb templates (if any)
        # 'report/sale_report_templates.xml',

        # Data (if you added demo/data)
        # 'data/vehicle_data.xml',
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