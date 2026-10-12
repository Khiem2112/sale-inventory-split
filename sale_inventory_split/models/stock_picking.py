from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    sale_split_group_key = fields.Char(
        string="Sale Split Group Key",
        readonly=True,
        index=True,
    )
