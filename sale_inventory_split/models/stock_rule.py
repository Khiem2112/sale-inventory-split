from odoo import models


class StockRule(models.Model):
    _inherit = "stock.rule"

    def _get_stock_move_values(
        self,
        product_id,
        product_qty,
        product_uom,
        location_dest_id,
        name,
        origin,
        company_id,
        values,
    ):
        move_values = super()._get_stock_move_values(
            product_id,
            product_qty,
            product_uom,
            location_dest_id,
            name,
            origin,
            company_id,
            values,
        )
        if values.get("sale_split_group_key") and values.get("partner_id"):
            partner = values["partner_id"]
            move_values["partner_id"] = getattr(partner, "id", partner)
        return move_values

    def _get_custom_move_fields(self):
        custom_fields = super()._get_custom_move_fields()
        if "sale_split_group_key" not in custom_fields:
            custom_fields.append("sale_split_group_key")
        return custom_fields
