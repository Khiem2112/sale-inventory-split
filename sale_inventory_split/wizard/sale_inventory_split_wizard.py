import uuid
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class SaleInventorySplitWizard(models.TransientModel):
    _name = "sale.inventory.split.wizard"
    _description = "Confirm Sales Order with Split Deliveries"

    order_id = fields.Many2one(
        "sale.order",
        string="Sales Order",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    planned_picking_ids = fields.One2many(
        "sale.inventory.split.picking",
        "wizard_id",
        string="Planned Pickings",
    )
    allocation_ids = fields.One2many(
        "sale.inventory.split.move",
        "wizard_id",
        string="Planned Stock Moves",
    )

    def _get_wizard_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Confirm Sales Order with Split Deliveries"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "view_id": self.env.ref(
                "sale_inventory_split.sale_inventory_split_wizard_view_form"
            ).id,
            "target": "new",
        }

    def _get_eligible_line_quantities(self):
        self.ensure_one()
        eligible_quantities = {}
        for line in self.order_id.order_line:
            if (
                line.display_type
                or line.is_downpayment
                or not line.product_id
                or line.product_id.type != "consu"
            ):
                continue
            outstanding_qty = line.product_uom_qty - line._get_qty_procurement()
            if (
                float_compare(
                    outstanding_qty,
                    0.0,
                    precision_rounding=line.product_uom.rounding,
                )
                > 0
            ):
                eligible_quantities[line] = outstanding_qty
        return eligible_quantities

    def _initialize_split_plan(self):
        self.ensure_one()
        if self.planned_picking_ids or self.allocation_ids:
            return

        planned_picking = self.env["sale.inventory.split.picking"].create(
            {
                "wizard_id": self.id,
                "name": _("Delivery 1"),
                "sequence": 10,
                "delivery_partner_id": self.order_id.partner_shipping_id.id,
            }
        )
        allocation_values = []
        for line, outstanding_qty in self._get_eligible_line_quantities().items():
            allocation_values.append(
                {
                    "wizard_id": self.id,
                    "planned_picking_id": planned_picking.id,
                    "sale_line_id": line.id,
                    "quantity": outstanding_qty,
                }
            )
        if allocation_values:
            self.env["sale.inventory.split.move"].create(allocation_values)

    def action_add_delivery(self):
        self.ensure_one()
        next_sequence = (
            max(self.planned_picking_ids.mapped("sequence"), default=0) + 10
        )
        delivery_number = next_sequence // 10
        self.env["sale.inventory.split.picking"].create(
            {
                "wizard_id": self.id,
                "name": _("Delivery %(number)s", number=delivery_number),
                "sequence": next_sequence,
                "delivery_partner_id": self.order_id.partner_shipping_id.id,
            }
        )
        return self._get_wizard_action()

    def _validate_split_plan(self):
        self.ensure_one()
        confirmation_error = self.order_id._confirmation_error_message()
        if confirmation_error:
            raise ValidationError(confirmation_error)

        if not self.planned_picking_ids:
            raise ValidationError(_("Add at least one planned picking."))

        eligible_quantities = self._get_eligible_line_quantities()
        eligible_lines = (
            self.env["sale.order.line"].concat(*eligible_quantities.keys())
            if eligible_quantities
            else self.env["sale.order.line"]
        )
        allocations_by_line = defaultdict(
            lambda: self.env["sale.inventory.split.move"]
        )

        split_group_keys = self.planned_picking_ids.mapped("split_group_key")
        if len(set(split_group_keys)) != len(split_group_keys):
            raise ValidationError(
                _("Every planned picking must have a unique split group key.")
            )

        for allocation in self.allocation_ids:
            if allocation.planned_picking_id.wizard_id != self:
                raise ValidationError(
                    _("Every stock move allocation must use a picking from this plan.")
                )
            if allocation.sale_line_id.order_id != self.order_id:
                raise ValidationError(
                    _("Every stock move allocation must belong to this sales order.")
                )
            if allocation.sale_line_id not in eligible_lines:
                raise ValidationError(
                    _(
                        "The order line %(line)s is not eligible for a split delivery.",
                        line=allocation.sale_line_id.display_name,
                    )
                )
            if (
                float_compare(
                    allocation.quantity,
                    0.0,
                    precision_rounding=allocation.product_uom_id.rounding,
                )
                <= 0
            ):
                raise ValidationError(
                    _("Every allocated quantity must be greater than zero.")
                )
            allocations_by_line[allocation.sale_line_id] |= allocation

        empty_pickings = self.planned_picking_ids.filtered(
            lambda picking: not picking.allocation_ids
        )
        if empty_pickings:
            raise ValidationError(
                _(
                    "The following planned pickings do not contain any stock move "
                    "allocations: %(pickings)s",
                    pickings=", ".join(empty_pickings.mapped("name")),
                )
            )

        for line, outstanding_qty in eligible_quantities.items():
            allocated_qty = sum(allocations_by_line[line].mapped("quantity"))
            if (
                float_compare(
                    allocated_qty,
                    outstanding_qty,
                    precision_rounding=line.product_uom.rounding,
                )
                != 0
            ):
                raise ValidationError(
                    _(
                        "The allocated quantity for %(product)s must equal "
                        "%(quantity)s %(uom)s.",
                        product=line.product_id.display_name,
                        quantity=outstanding_qty,
                        uom=line.product_uom.name,
                    )
                )

    def _build_split_plan(self):
        self.ensure_one()
        split_plan = defaultdict(list)
        allocations = self.allocation_ids.sorted(
            key=lambda allocation: (
                allocation.planned_picking_id.sequence,
                allocation.id,
            )
        )
        for allocation in allocations:
            split_plan[allocation.sale_line_id.id].append(
                {
                    "quantity": allocation.quantity,
                    "split_group_key": allocation.planned_picking_id.split_group_key,
                    "delivery_partner_id": (
                        allocation.planned_picking_id.delivery_partner_id.id
                    ),
                }
            )
        return dict(split_plan)

    def action_confirm_with_split(self):
        self.ensure_one()
        self._validate_split_plan()
        order = self.order_id
        order.with_context(
            sale_inventory_split_plan=self._build_split_plan()
        ).action_confirm()
        return {
            "type": "ir.actions.act_window",
            "name": _("Sales Order"),
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }


class SaleInventorySplitPicking(models.TransientModel):
    _name = "sale.inventory.split.picking"
    _description = "Planned Split Picking"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        "sale.inventory.split.wizard",
        string="Split Wizard",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(string="Delivery", required=True)
    sequence = fields.Integer(default=10)
    delivery_partner_id = fields.Many2one(
        "res.partner",
        string="Delivery Address",
        required=True,
    )
    split_group_key = fields.Char(
        string="Split Group Key",
        required=True,
        readonly=True,
        default=lambda self: str(uuid.uuid4()),
    )
    allocation_ids = fields.One2many(
        "sale.inventory.split.move",
        "planned_picking_id",
        string="Stock Move Allocations",
    )


class SaleInventorySplitMove(models.TransientModel):
    _name = "sale.inventory.split.move"
    _description = "Planned Split Stock Move"
    _order = "planned_picking_id, id"

    wizard_id = fields.Many2one(
        "sale.inventory.split.wizard",
        string="Split Wizard",
        required=True,
        ondelete="cascade",
    )
    planned_picking_id = fields.Many2one(
        "sale.inventory.split.picking",
        string="Delivery",
        required=True,
        ondelete="cascade",
    )
    sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Order Line",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        related="sale_line_id.product_id",
        string="Product",
        readonly=True,
    )
    product_uom_id = fields.Many2one(
        related="sale_line_id.product_uom",
        string="Unit of Measure",
        readonly=True,
    )
    outstanding_qty = fields.Float(
        string="Outstanding Quantity",
        compute="_compute_outstanding_qty",
        digits="Product Unit of Measure",
    )
    quantity = fields.Float(
        string="Allocated Quantity",
        required=True,
        digits="Product Unit of Measure",
    )

    @api.depends("sale_line_id", "sale_line_id.product_uom_qty")
    def _compute_outstanding_qty(self):
        for allocation in self:
            line = allocation.sale_line_id
            allocation.outstanding_qty = (
                line.product_uom_qty - line._get_qty_procurement() if line else 0.0
            )
