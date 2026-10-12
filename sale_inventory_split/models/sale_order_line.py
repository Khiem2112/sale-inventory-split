from odoo import _, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _create_procurements(self, product_qty, procurement_uom, origin, values):
        self.ensure_one()
        split_plan = self.env.context.get("sale_inventory_split_plan", {}).get(
            self.id
        )
        if not split_plan:
            return super()._create_procurements(
                product_qty, procurement_uom, origin, values
            )

        expected_sale_qty = procurement_uom._compute_quantity(
            product_qty,
            self.product_uom,
            round=False,
        )
        planned_sale_qty = sum(
            allocation.get("quantity", 0.0) for allocation in split_plan
        )
        if float_compare(
            planned_sale_qty,
            expected_sale_qty,
            precision_rounding=self.product_uom.rounding,
        ):
            raise ValidationError(
                _("The split plan quantity does not match the quantity to procure.")
            )
        if any(
            not allocation.get("split_group_key")
            or not allocation.get("delivery_partner_id")
            or float_compare(
                allocation.get("quantity", 0.0),
                0.0,
                precision_rounding=self.product_uom.rounding,
            )
            <= 0
            for allocation in split_plan
        ):
            raise ValidationError(
                _(
                    "Every split allocation must have a group, a delivery "
                    "address, and a positive quantity."
                )
            )

        procurements = []
        remaining_qty = product_qty
        rounding = procurement_uom.rounding
        for index, allocation in enumerate(split_plan):
            if index == len(split_plan) - 1:
                allocation_qty = remaining_qty
            else:
                allocation_qty = self.product_uom._compute_quantity(
                    allocation["quantity"],
                    procurement_uom,
                    rounding_method="HALF-UP",
                )
                remaining_qty -= allocation_qty

            if float_compare(allocation_qty, 0.0, precision_rounding=rounding) <= 0:
                raise ValidationError(
                    _(
                        "Every split allocation must be representable in the "
                        "procurement unit of measure."
                    )
                )

            allocation_values = dict(values)
            allocation_values["sale_split_group_key"] = allocation[
                "split_group_key"
            ]
            allocation_values["partner_id"] = allocation["delivery_partner_id"]
            procurements += super()._create_procurements(
                allocation_qty,
                procurement_uom,
                origin,
                allocation_values,
            )
        return procurements
