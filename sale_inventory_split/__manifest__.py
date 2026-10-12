{
    "name": "Sale Inventory Split",
    "summary": "Split sales order quantities across multiple delivery orders",
    "version": "18.0.1.0.0",
    "category": "Sales/Sales",
    "author": "khiem nguyen",
    "license": "LGPL-3",
    "depends": ["sale_stock"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/sale_inventory_split_wizard_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
}
