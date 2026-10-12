from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.addons.sale_stock.tests.common import TestSaleStockCommon


@tagged("post_install", "-at_install")
class TestSaleInventorySplit(TestSaleStockCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create(
            {
                "name": "Split Delivery Product",
                "is_storable": True,
                "list_price": 100.0,
            }
        )
        cls.second_product = cls.env["product.product"].create(
            {
                "name": "Second Split Delivery Product",
                "is_storable": True,
                "list_price": 50.0,
            }
        )
        cls.delivery_address_1 = cls.env["res.partner"].create(
            {
                "name": "First Delivery Address",
                "parent_id": cls.partner_a.id,
                "type": "delivery",
                "street": "1 First Street",
            }
        )
        cls.delivery_address_2 = cls.env["res.partner"].create(
            {
                "name": "Second Delivery Address",
                "parent_id": cls.partner_a.id,
                "type": "delivery",
                "street": "2 Second Street",
            }
        )

    def _create_order(self, quantity=10.0):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": quantity,
                        },
                    )
                ],
            }
        )
        return order

    def _open_split_wizard(self, order):
        action = order.action_open_inventory_split_wizard()
        return self.env["sale.inventory.split.wizard"].browse(action["res_id"])

    def test_standard_confirmation_is_unchanged(self):
        order = self._create_order()

        order.action_confirm()

        self.assertEqual(len(order.picking_ids), 1)
        self.assertFalse(order.picking_ids.sale_split_group_key)
        self.assertFalse(order.picking_ids.move_ids.sale_split_group_key)

    def test_confirm_with_split_creates_two_pickings(self):
        order = self._create_order()
        wizard = self._open_split_wizard(order)
        first_allocation = wizard.allocation_ids
        first_picking = wizard.planned_picking_ids
        first_picking.delivery_partner_id = self.delivery_address_1
        first_allocation.quantity = 4.0
        wizard.action_add_delivery()
        second_picking = wizard.planned_picking_ids.sorted("sequence")[-1]
        second_picking.delivery_partner_id = self.delivery_address_2
        self.env["sale.inventory.split.move"].create(
            {
                "wizard_id": wizard.id,
                "planned_picking_id": second_picking.id,
                "sale_line_id": order.order_line.id,
                "quantity": 6.0,
            }
        )

        wizard.action_confirm_with_split()

        pickings = order.picking_ids.filtered(lambda picking: picking.state != "cancel")
        self.assertEqual(len(pickings), 2)
        self.assertEqual(len(set(pickings.mapped("sale_split_group_key"))), 2)
        moves = pickings.move_ids.filtered(
            lambda move: move.sale_line_id == order.order_line
        )
        self.assertEqual(sorted(moves.mapped("product_uom_qty")), [4.0, 6.0])
        self.assertEqual(sum(moves.mapped("product_uom_qty")), 10.0)
        pickings_by_key = {
            picking.sale_split_group_key: picking for picking in pickings
        }
        self.assertEqual(
            pickings_by_key[first_picking.split_group_key].partner_id,
            self.delivery_address_1,
        )
        self.assertEqual(
            pickings_by_key[second_picking.split_group_key].partner_id,
            self.delivery_address_2,
        )
        self.assertEqual(
            pickings_by_key[first_picking.split_group_key].move_ids.partner_id,
            self.delivery_address_1,
        )
        self.assertEqual(
            pickings_by_key[second_picking.split_group_key].move_ids.partner_id,
            self.delivery_address_2,
        )

    def test_multiple_order_lines_share_the_planned_picking(self):
        order = self._create_order(quantity=3.0)
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.second_product.id,
                "product_uom_qty": 5.0,
            }
        )
        wizard = self._open_split_wizard(order)

        wizard.action_confirm_with_split()

        self.assertEqual(len(order.picking_ids), 1)
        self.assertEqual(len(order.picking_ids.move_ids), 2)
        self.assertEqual(
            set(order.picking_ids.move_ids.mapped("sale_split_group_key")),
            {wizard.planned_picking_ids.split_group_key},
        )

    def test_split_confirmation_keeps_standard_reservation_flow(self):
        order = self._create_order()
        self.env["stock.quant"]._update_available_quantity(
            self.product,
            order.warehouse_id.lot_stock_id,
            10.0,
        )
        wizard = self._open_split_wizard(order)
        wizard.allocation_ids.quantity = 4.0
        wizard.action_add_delivery()
        second_picking = wizard.planned_picking_ids.sorted("sequence")[-1]
        self.env["sale.inventory.split.move"].create(
            {
                "wizard_id": wizard.id,
                "planned_picking_id": second_picking.id,
                "sale_line_id": order.order_line.id,
                "quantity": 6.0,
            }
        )

        wizard.action_confirm_with_split()

        self.assertEqual(set(order.picking_ids.mapped("state")), {"assigned"})
        self.assertEqual(
            sum(order.picking_ids.move_ids.move_line_ids.mapped("quantity")),
            10.0,
        )

    def test_split_group_is_propagated_through_multi_step_route(self):
        order = self._create_order()
        order.warehouse_id = self.warehouse_3_steps_pull
        wizard = self._open_split_wizard(order)
        first_picking = wizard.planned_picking_ids
        first_picking.delivery_partner_id = self.delivery_address_1
        wizard.allocation_ids.quantity = 4.0
        wizard.action_add_delivery()
        second_picking = wizard.planned_picking_ids.sorted("sequence")[-1]
        second_picking.delivery_partner_id = self.delivery_address_2
        self.env["sale.inventory.split.move"].create(
            {
                "wizard_id": wizard.id,
                "planned_picking_id": second_picking.id,
                "sale_line_id": order.order_line.id,
                "quantity": 6.0,
            }
        )

        wizard.action_confirm_with_split()

        self.assertEqual(len(order.picking_ids), 6)
        split_keys = set(wizard.planned_picking_ids.mapped("split_group_key"))
        self.assertEqual(set(order.picking_ids.mapped("sale_split_group_key")), split_keys)
        for picking_type in order.picking_ids.picking_type_id:
            step_pickings = order.picking_ids.filtered(
                lambda picking: picking.picking_type_id == picking_type
            )
            self.assertEqual(len(step_pickings), 2)
            self.assertEqual(set(step_pickings.mapped("sale_split_group_key")), split_keys)
        for planned_picking, delivery_address in (
            (first_picking, self.delivery_address_1),
            (second_picking, self.delivery_address_2),
        ):
            split_pickings = order.picking_ids.filtered(
                lambda picking: (
                    picking.sale_split_group_key
                    == planned_picking.split_group_key
                )
            )
            self.assertEqual(split_pickings.partner_id, delivery_address)
            self.assertEqual(split_pickings.move_ids.partner_id, delivery_address)

    def test_split_plan_requires_exact_quantity(self):
        order = self._create_order()
        wizard = self._open_split_wizard(order)
        wizard.allocation_ids.quantity = 9.0

        with self.assertRaises(ValidationError):
            wizard.action_confirm_with_split()

        self.assertEqual(order.state, "draft")
