from odoo import _, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_open_inventory_split_wizard(self):
        self.ensure_one()
        confirmation_error = self._confirmation_error_message()
        if confirmation_error:
            raise UserError(confirmation_error)

        wizard = self.env["sale.inventory.split.wizard"].create(
            {"order_id": self.id}
        )
        wizard._initialize_split_plan()
        if not wizard.allocation_ids:
            wizard.unlink()
            raise UserError(
                _("This sales order has no stockable quantities to split.")
            )
        return wizard._get_wizard_action()
