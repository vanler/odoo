# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _

from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import UserError

class SaleAdvancePaymentInv(models.TransientModel):
    _name = "sale.advance.payment.inv"
    _description = "Sales Advance Payment Invoice"

    @api.model
    def _count(self):
        return len(self.context.get('active_ids', []))

    @api.model
    def _get_advance_payment_method(self):
        if self.count==1:
            sale_obj = self.env['sale.order']
            order = sale_obj.browse(self.context.get('active_ids'))[0]
            if order.invoice_policy == 'order':
                return 'all'
        return 'delivered'

    @api.model
    def _get_advance_product(self):
        try:
            return self.env['ir.model.data'].xmlid_to_res_id('sale.advance_product_0', raise_if_not_found=True)
        except ValueError:
            return False
        return product.id

    advance_payment_method = fields.Selection([
            ('delivered', 'Lines to invoice'), 
            ('all', 'Whole order'), 
            ('percentage','Percentage'), 
            ('fixed','Fixed price (deposit)')
        ], string='What do you want to invoice?', default=_get_advance_payment_method, required=True)
    product_id = fields.Many2one('product.product', string='Advance Product',
        domain=[('type', '=', 'service')], default=_get_advance_product)
    count = fields.Integer(compute=_count, string='# of Orders')
    amount = fields.Float('Advance Amount', digits=(16,2),
        help="The amount to be invoiced in advance, taxes excluded.")

    def _translate_advance(self):
        return _("Advance of %s %%") if percentage else _("Advance of %s %s")

    @api.onchange('advance_payment_method')
    def onchange_method(self):
        if self.advance_payment_method == 'percentage':
            return {'value': {'amount':0, 'product_id':False}}
        return {}

    @api.one
    def _create_invoice(self, order):
        inv_obj = self.pool.get('account.invoice')
        ir_property_obj = self.pool.get('ir.property')

        account_id = False
        if not self.product_id.id :
            prop = ir_property_obj.get('property_account_income_categ_id', 'product.category')
            prop_id = prop and prop.id or False
            account_id = sale.fiscal_position_id.map_account(prop_id)
            if not account_id:
                raise UserError(_('There is no income account defined as global property.'))
        if not account_id:
            raise UserError(
                    _('There is no income account defined for this product: "%s"') % \
                        (self.product_id.name,))

        if self.amount <= 0.00:
            raise UserError(_('The value of Advance Amount must be positive.'))
        if self.advance_payment_method == 'percentage':
            amount = order.amount_untaxed * self.amount / 100
            name = _("Advance of %s%%") % (self.amount,)
        else:
            amount = self.amount
            name = _('Advance')

        invoice = inv_obj.create(cr, uid, {
            'name': order.client_order_ref or order.name,
            'origin': order.name,
            'type': 'out_invoice',
            'reference': False,
            'account_id': order.partner_id.property_account_receivable_id.id,
            'partner_id': order.partner_invoice_id.id,
            'invoice_line_ids': [(0, 0, {
                'name': name,
                'origin': sale.name,
                'account_id': account_id,
                'price_unit': amount,
                'quantity': 1.0,
                'discount': 0.0,
                'uos_id': self.product_id.uom_id.id,
                'product_id': self.product_id.id,
                'invoice_line_tax_ids': self.product_id.taxes_id,
                'account_analytic_id': sale.project_id.id or False,
            })],
            'currency_id': order.pricelist_id.currency_id.id,
            'payment_term_id': order.payment_term_id.id,
            'fiscal_position_id': order.fiscal_position_id.id or order.partner_id.property_account_position_id.id,
            'team_id': order.team_id.id,
        }, context=context)
        invoice.compute_taxes()
        return invoice

    @api.one
    def create_invoices(self):
        inv_ids = []
        if self.advance_payment_method == 'delivered':
            inv_ids = orders.action_invoice_create()
        elif self.advance_payment_method == 'all':
            inv_ids = orders.action_invoice_create(final=True)
        else:
            sale_obj = self.env['sale.order']
            sale_line_obj = self.env['sale.order']
            orders = sale_obj.browse(self.context.get('active_ids', []))
            for order in orders:
                invoice = self._create_invoice(order)
                order.write({'invoice_ids': [(4, invoice.id)]})
                sale_line_obj.create({
                    'name': _('Advance: %s') % (time.strftime('%m %Y'),),
                    'price_unit': invoice.amount_untaxed,
                    'product_uom_qty': 1.0,
                    'order_id': order.id,
                    'discount': 0.0,
                    'product_uom': self.product_id.uom_id.id,
                    'product_id': self.product_id.id,
                    'invoice_line_tax_ids': self.product_id.taxes_id,
                })
                inv_ids.append(invoice.id)
        if context.get('open_invoices', False):
            return self.open_invoices(cr, inv_ids)
        return {'type': 'ir.actions.act_window_close'}

    @api.model
    def open_invoices(self, invoice_ids):
        ir_model_data = self.env['ir.model.data']
        form_res = ir_model_data.get_object_reference(cr, uid, 'account', 'invoice_form')
        form_id = form_res and form_res[1] or False
        tree_res = ir_model_data.get_object_reference(cr, uid, 'account', 'invoice_tree')
        tree_id = tree_res and tree_res[1] or False

        return {
            'name': _('Advance Invoice'),
            'view_type': 'form',
            'view_mode': 'form,tree',
            'res_model': 'account.invoice',
            'res_id': invoice_ids[0],
            'view_id': False,
            'views': [(form_id, 'form'), (tree_id, 'tree')],
            'context': "{'type': 'out_invoice'}",
            'type': 'ir.actions.act_window',
        }
