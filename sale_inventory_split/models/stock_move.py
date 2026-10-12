from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    sale_split_group_key = fields.Char(
        string="Sale Split Group Key",
        readonly=True,
        index=True,
    )

    def _key_assign_picking(self):
        self.ensure_one()
        return (*super()._key_assign_picking(), self.sale_split_group_key)

    def _search_picking_for_assignation_domain(self):
        domain = super()._search_picking_for_assignation_domain()
        return domain + [
            ("sale_split_group_key", "=", self.sale_split_group_key or False)
        ]

    def _get_new_picking_values(self):
        values = super()._get_new_picking_values()
        values["sale_split_group_key"] = self[:1].sale_split_group_key
        return values

    def _prepare_procurement_values(self):
        values = super()._prepare_procurement_values()
        values["sale_split_group_key"] = self.sale_split_group_key
        if self.sale_split_group_key:
            values["partner_id"] = self.partner_id.id
        return values

    @api.model
    def _prepare_merge_moves_distinct_fields(self):
        fields_to_compare = super()._prepare_merge_moves_distinct_fields()
        if "sale_split_group_key" not in fields_to_compare:
            fields_to_compare.append("sale_split_group_key")
        return fields_to_compare
