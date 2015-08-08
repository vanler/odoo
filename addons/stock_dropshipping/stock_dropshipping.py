# coding: utf-8

from openerp import models, api, _
from openerp.exceptions import UserError

class purchase_order(models.Model):
    _inherit = 'purchase.order'

    @api.one
    def _check_invoice_policy(self):
        if self.invoice_method == 'picking' and self.location_id.usage == 'customer':
            for proc in self.order_line.mapped('procurement_ids'):
                if proc.sale_line_id.order_id.order_policy == 'picking':
                    raise UserError(_('In the case of a dropship route, it is not possible to have an invoicing control set on "Based on incoming shipments" and a sale order with an invoice creation on "On Delivery Order"'))

    @api.multi
    def wkf_confirm_order(self):
        """ Raise a warning to forbid to have both purchase and sale invoices
        policies at delivery in dropshipping. As it is not implemented.

        This check can be disabled setting 'no_invoice_policy_check' in context
        """
        if not self.env.context.get('no_invoice_policy_check'):
            self._check_invoice_policy()
        super(purchase_order, self).wkf_confirm_order()
