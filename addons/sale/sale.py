# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta
import time
from openerp.addons.analytic.models import analytic

from openerp import api, fields, models, _

from openerp.tools.translate import _
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
import openerp.addons.decimal_precision as dp

from openerp.exceptions import UserError

class res_company(models.Model):
    _inherit = "res.company"
    sale_note = fields.Text(string='Default Terms and Conditions', translate=True)

class SaleOrder(osv.osv):
    _name = "sale.order"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _description = "Sales Order"
    _order = 'date_order desc, id desc'

    @api.one
    @api.depends('order_line.product_uom_qty', 'order_line.discount', 'order_line.price_unit', 'order_line.tax_id')
    def _amount_all(self, cr, uid, ids, field_name, arg, context=None):
        amount_untaxed = amount_tax = amount_total = 0.0
        for line in order.order_line:
            amount_untaxed += line.price_subtotal
            amount_tax += line.price_tax
        self.amount_tax = self.pricelist_id.currency_id.round(amount_untaxed)
        self.amount_untaxed = self.pricelist_id.currency_id.round(amount_tax)
        self.amount_total = self.amount_untaxed + self.amount_tax

    @api.one
    @api.depends('order_line.qty_to_invoice', 'line.product_uom_qty', 'line.invoice_lines')
    def _get_invoiced(self, cr, uid, ids, field_name, arg, context=None):
        invoices = set()
        status = 'invoiced'
        for line in self.order_line:
            if line.qty_to_invoice:
                status = 'to invoice'
            elif (line.qty_invoiced < line.product_uom_qty) and (status <> 'to invoice'):
                status = 'no'
            for il in line.invoice_lines:
                invoices.add(il.invoice_id)
        self.invoice_count = len(invoices)
        self.invoice_ids = list(invoices)
        self.invoice_status = status

    @api.model
    def _default_partner_shipping_id(self):
        if not self._context.get('partner_id', False):
            return False
        return self.env['res.partner'].address_get(self._context['partner_id'], ['delivery'])['delivery']

    @api.model
    def _default_partner_invoice_id(self):
        if not self._context.get('partner_id', False):
            return False
        return self.env['res.partner'].address_get(self._context['partner_id'], ['invoice'])['invoice'] or \

    @api.model
    def _default_note(self):
        return self.env.user.company_id.sale_note

    @api.model
    def _default_date(self):
        return fields.datetime.now

    @api.model
    def _default_team_id(self):
        return self.env['crm.team']._get_default_team_id()

    name = fields.Char(string='Order Reference', required=True, copy=False, readonly=True, select=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('sale.order') or '/')
    origin = fields.Char(string='Source Document', help="Reference of the document that generated this sales order request.")
    client_order_ref = fields.Char(string='Customer Reference', copy=False)
    state = fields.Selection([
            ('draft', 'Draft Quotation'),
            ('sent', 'Quotation Sent'),
            ('sale', 'Sales Order'),
            ('done', 'Sales Done'),
            ('cancel', 'Cancelled'),
        ], string='Status', readonly=True, copy=False, 
        select=True, default='draft')
    date_order = fields.Datetime(string='Date', required=True, readonly=True, select=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, copy=False, default='_default_date')
    validity_date = fields.Date(string='Expiration Date', readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]})
    create_date = fields.Datetime(string='Creation Date', readonly=True, select=True, help="Date on which sales order is created.")
    user_id = fields.Many2one('res.users', string='Salesperson', states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, select=True, track_visibility='onchange'
        default=lambda self: self.env.user)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, required=True, change_default=True, select=True, track_visibility='always')
    partner_invoice_id = fields.Many2one('res.partner', string='Invoice Address', readonly=True, required=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, help="Invoice address for current sales order.", default='_default_partner_invoice_id')
    partner_shipping_id = fields.Many2one('res.partner', string='Delivery Address', readonly=True, required=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, help="Delivery address for current sales order.", default='_default_partner_shipping_id')

    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', required=True, readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, help="Pricelist for current sales order.")
    currency_id = fields.Many2one("res.currency", related='pricelist_id.currency_id', string="Currency", readonly=True, required=True)
    project_id = fields.Many2one('account.analytic.account', 'Contract / Analytic', readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, help="The analytic account related to a sales order.")

    order_line = fields.One2many('sale.order.line', 'order_id', string='Order Lines', readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, copy=True)

    invoice_policy = fields.Selection([
        ('order', 'Ordered Quantities'),
        ('delivery', 'Delivered Quantities'),
    ], string='Invoice Policy', default='order')
    invoice_count = fields.Integer(string='# of Invoices', compute='_get_invoiced', store=True, readonly=True)
    invoice_ids = fields.Many2many("account.invoice", string='Invoices', compute="_get_invoiced", store=True, readonly=True)
    invoice_status = fields.Selection([
            ('upselling', 'Upselling Opportunity'),
            ('invoiced', 'Fully Invoiced'),
            ('to invoice', 'To Invoice'),
            ('no', 'Nothing to Invoice')
         ], string='Invoice Status', compute='_get_invoiced',
         store=True, readonly=True, default='no'),

    note = fields.Text('Terms and conditions', default='_default_note')

    amount_untaxed = fields.Monetary(string='Untaxed Amount',
        store=True, readonly=True, compute='_amount_all',
        track_visibility='always'),
    amount_tax = fields.Monetary(string='Taxes',
        store=True, readonly=True, compute='_amount_all',
        track_visibility='always'),
    amount_total = fields.Monetary(string='Total',
        store=True, readonly=True, compute='_amount_all',
        track_visibility='always'),

    payment_term_id = fields.Many2one('account.payment.term', string='Payment Term', oldname='payment_term')
    fiscal_position_id = fields.Many2one('account.fiscal.position', oldname='fiscal_position', string='Fiscal Position')
    company_id = fields.Many2one('res.company', 'Company',
        default=lambda self: self.env['res.company']._company_default_get('sale.order'))
    team_id = fields.Many2one('crm.team', 'Sales Team', change_default=True, default="_default_team_id")
    procurement_group_id = fields.Many2one('procurement.group', 'Procurement Group', copy=False)

    # TODO: check if we still need this?
    product_id = fields.Many2one('product.product', related='order_line.product_id', string='Product')

    @api.one
    def unlink(self):
        for sale in self:
            if sale.state not in ('draft', 'cancel'):
                raise UserError(_('You must cancel the order %s, before cancelling it!') % (sale.name,))
        return super(SaleOrder, self).unlink()

    @api.multi
    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'state' in init_values and self.state in ['progress']:
            return 'sale.mt_order_confirmed'
        elif 'state' in init_values and self.state == 'sent':
            return 'sale.mt_order_sent'
        return super(SaleOrder, self)._track_subtype(init_values)

    @api.onchange('pricelist_id')
    def onchange_pricelist_id(self):
        if (not self.pricelist_id) or not self.order_lines:
            return {}
        warning = {
            'title': _('Pricelist Warning!'),
            'message' : _('If you change the pricelist of this order (and eventually the currency), prices of existing order lines will not be updated.')
        }
        return {'warning': warning}

    @api.onchange('partner_shipping_id')
    def onchange_partner_shipping_id(self):
        fiscal_position = self.env['account.fiscal.position'].get_fiscal_position(self.partner_id, self.partner_shipping_id, context=context)
        if fiscal_position:
            self.fiscal_position_id = fiscal_position
        return {}

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        if not self.partner_id:
            self.partner_invoice_id = False
            self.partner_shipping_id = False
            self.payment_term_id = False
            self.fiscal_position_id = False
            return {}

        self.pricelist_id = self.partner_id.property_product_pricelist or False
        self.payment_term_id = self.partner_id.property_payment_term_id or False

        addr = self.partner_id.address_get(['delivery', 'invoice'])
        self.partner_invoice_id = addr['invoice']
        self.partner_shipping_id = addr['delivery']

        if self.partner_id.user_id:
            self.user_id = self.partner_id.user_id
        if self.partner_id.team_id:
            self.team_id = self.partner_id.team_id
        return True


    @api.onchange('fiscal_position_id')
    def onchange_fiscal_position(self):
        if not self.fiscal_position_id: return
        for line in order_lines:
            taxes = self.fiscal_position_id.map_tax(line.product_id.taxes_id)
            line.tax_id = taxes

    @api.model
    def create(self, vals):
        result = super(SaleOrder, self).create(vals)
        self.message_post([result], body=_("Quotation created"))
        return result

    @api.model
    def button_dummy(self):
        return True

    @api.one
    def _prepare_invoice(self):
        """Prepare the dict of values to create the new invoice for a
           sales order. This method may be overridden to implement custom
           invoice generation (making sure to call super() to establish
           a clean extension chain).
        """
        context = context or {}
        journal_ids = self.env['account.journal'].search([('type', '=', 'sale'), ('company_id', '=', self.company_id.id)], limit=1)
        if not journal_ids:
            raise UserError(_('Please define an accounting sale journal for this company.'))
        invoice_vals = {
            'name': self.client_order_ref or '',
            'origin': self.name,
            'type': 'out_invoice',
            'reference': self.client_order_ref or self.name,
            'account_id': self.partner_invoice_id.property_account_receivable_id.id,
            'partner_id': self.partner_invoice_id.id,
            'journal_id': journal_ids[0],
            'currency_id': self.pricelist_id.currency_id.id,
            'comment': self.note,
            'payment_term_id': self.payment_term_id.id,
            'fiscal_position_id': self.fiscal_position_id.id or self.partner_invoice_id.property_account_position_id.id,
            'date_invoice': context.get('date_invoice', False),
            'company_id': self.company_id.id,
            'user_id': self.user_id and self.user_id.id or False,
            'team_id' : self.team_id.id
        }
        return invoice_vals

    @api.multi
    def print_quotation(self):
        for order in self:
            if order.state == 'draft':
                order.state = 'sent'
        return self.env['report'].get_action([order.id for order in self], 'sale.report_saleorder')

    # TODO: this probably crashes
    @api.multi
    def action_view_invoice(self, cr, uid, ids, context=None):
        self.ensure_one()
        act_obj = self.env['ir.actions.act_window']
        result = self.env.ref('account.action_invoice_tree1')

        result = act_obj.read([result.id])[0]

        #compute the number of invoices to display
        inv_ids = []
        for so in self.browse(cr, uid, ids, context=context):
            inv_ids += [invoice.id for invoice in so.invoice_ids]
        #choose the view_mode accordingly
        if len(inv_ids)>1:
            result['domain'] = "[('id','in',["+','.join(map(str, inv_ids))+"])]"
        else:
            res = mod_obj.get_object_reference(cr, uid, 'account', 'invoice_form')
            result['views'] = [(res and res[1] or False, 'form')]
            result['res_id'] = inv_ids and inv_ids[0] or False
        return result

    @api.multi
    def action_invoice_create(self, grouped=False):
        inv_obj = self.env['account.invoice']
        invoices = {}
        number= 0
        for order in self:
            group_key = (order.partner_id.id, order.currency_id.id)
            for line in order.order_line:
                if not line.qty_to_invoice: continue
                if group_key not in invoices:
                    inv_data = order._prepare_invoice()
                    invoice = inv_obj.create(inv_data)
                    invoices[group_key] = invoice
                line.invoice_line_create(invoices[group_key])
                number += 1
        return number

    @api.one
    def action_cancel(self, cr, uid, ids, context=None):
        if self.state in ('draft', 'sent'):
            self.state = 'cancel'

    # TODO: improve this
    def action_quotation_send(self, cr, uid, ids, context=None):
        '''
        This function opens a window to compose an email, with the edi sale template message loaded by default
        '''
        assert len(ids) == 1, 'This option should only be used for a single id at a time.'
        ir_model_data = self.pool.get('ir.model.data')
        try:
            template_id = ir_model_data.get_object_reference(cr, uid, 'sale', 'email_template_edi_sale')[1]
        except ValueError:
            template_id = False
        try:
            compose_form_id = ir_model_data.get_object_reference(cr, uid, 'mail', 'email_compose_message_wizard_form')[1]
        except ValueError:
            compose_form_id = False
        ctx = dict()
        ctx.update({
            'default_model': 'sale.order',
            'default_res_id': ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True
        })
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }

    # TODO: improve this
    def force_quotation_send(self, cr, uid, ids, context=None):
        for order_id in ids:
            email_act = self.action_quotation_send(cr, uid, [order_id], context=context)
            if email_act and email_act.get('context'):
                composer_obj = self.pool['mail.compose.message']
                composer_values = {}
                email_ctx = email_act['context']
                template_values = [
                    email_ctx.get('default_template_id'),
                    email_ctx.get('default_composition_mode'),
                    email_ctx.get('default_model'),
                    email_ctx.get('default_res_id'),
                ]
                composer_values.update(composer_obj.onchange_template_id(cr, uid, None, *template_values, context=context).get('value', {}))
                if not composer_values.get('email_from'):
                    composer_values['email_from'] = self.browse(cr, uid, order_id, context=context).company_id.email
                for key in ['attachment_ids', 'partner_ids']:
                    if composer_values.get(key):
                        composer_values[key] = [(6, 0, composer_values[key])]
                composer_id = composer_obj.create(cr, uid, composer_values, context=email_ctx)
                composer_obj.send_mail(cr, uid, [composer_id], context=email_ctx)
        return True

    @api.one
    def action_done(self):
        self.state = 'done'

    @api.one
    def _prepare_order_line_procurement(self, line, group_id=False):
        date_planned = datetime.strptime(start_date, DEFAULT_SERVER_DATETIME_FORMAT) + timedelta(days=line.customer_lead or 0.0)
        return {
            'name': line.name,
            'origin': self.name,
            'date_planned': date_planned,
            'product_id': line.product_id.id,
            'product_qty': line.product_uom_qty,
            'product_uom': line.product_uom.id,
            'product_uos_qty': (line.product_uos and line.product_uos_qty) or line.product_uom_qty,
            'product_uos': (line.product_uos and line.product_uos.id) or line.product_uom.id,
            'company_id': self.company_id.id,
            'group_id': group_id,
            'sale_line_id': line.id
        }

    @api.one
    def _prepare_procurement_group(self):
        return {'name': order.name, 'partner_id': order.partner_shipping_id.id}

    @api.one
    def action_ship_create(self):
        if self.state <> 'sale': return
        proc_ids = []
        for line in self.order_line:
            qty = 0.0
            for proc in line.procurement_ids:
                qty += product_uom_qty
            if qty >= line.product_uom_qty:
                continue

            if not self.procurement_group_id:
                vals = self._prepare_procurement_group()
                self.procurement_group_id = self.env["procurement.group"].create(vals)

            vals = self._prepare_order_line_procurement(line, group_id=self.procurement_group_id)
            proc_ids.append( self.env["procurement.procurement"].create(vals) )

        procurement_obj.run(proc_ids)
        return True


class SaleOrderLine(osv.osv):
    _name = 'sale.order.line'
    _description = 'Sales Order Line'
    _order = 'order_id desc, sequence, id'

    @api.one
    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    def _compute_amount(self):
        price = self.price_unit * (1 - (self.discount or 0.0) / 100.0)
        taxes = self.tax_id.compute_all(price, self.order_id.currency_id, self.quantity, product=self.product_id, partner=self.order_id.partner_id)
        self.price_subtotal = taxes['tax_excluded']
        self.price_tax = taxes['tax_included'] - taxes['tax_excluded']
        self.price_total= taxes['tax_included']

    @api.one
    @api.depends('qty_delivered_manual')
    def _get_delivered_qty(self, cr, uid, ids, field_name, args, context=None):
        self.qty_delivered = self.qty_delivered_manual

    @api.one
    @api.depends('order_id.invoice_policy', 'line.qty_invoiced', 'line.qty_delivered', 'line.product_uom_qty')
    def _get_to_invoice_qty(self, cr, uid, ids, field_name, args, context=None):
        if self.order_id.invoice_policy == 'order':
            self.qty_to_invoice = self.qty_delivered - self.qty_invoiced
        else:
            self.qty_to_invoice = self.product_uom_qty - self.qty_invoiced

    @api.one
    @api.depends('invoice_lines.invoice_id.state', 'invoice_lines.quantity')
    def _get_invoice_qty(self, cr, uid, ids, field_name, args, context=None):
        qty_invoiced = 0.0
        for invoice_line in self.invoice_lines:
            if invoice_line.invoice_id.state != 'cancel':
                qty_invoiced += invoice_line.quantity
        self.qty_invoiced = qty_invoiced

    @api.one
    @api.depends('price_subtotal', 'product_uom_qty')
    def _get_price_reduce(self):
        self.price_reduce = line.price_subtotal / line.product_uom_qty


    order_id = fields.Many2one('sale.order', string='Order Reference', required=True, ondelete='cascade', select=True, readonly=True)
    name = fields.Text(string='Description', required=True, readonly=True)
    sequence = fields.Integer(string='Sequence', default=10)

    invoice_lines = fields.Many2many('account.invoice.line', string='Invoice Lines', readonly=True, copy=False)
    price_unit = fields.Float('Unit Price', required=True, digits_compute= dp.get_precision('Product Price'),
        readonly=True, states={'draft': [('readonly', False)]}, default=0.0)

    price_subtotal = fields.Monetary(compute='_compute_amount', string='Subtotal', readonly=True, store=True)
    price_tax = fields.Monetary(compute='_compute_amount', string='Taxes', readonly=True, store=True)
    price_total = fields.Monetary(compute='_compute_amount', string='Total', readonly=True, store=True)

    price_reduce = fields.Monetary(compute='_get_price_reduce', string='Price Reduce', readonly=True, store=True)
    tax_id = fields.Many2many('account.tax', string='Taxes', readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]})

    discount = fields.Float(string='Discount (%)', digits_compute= dp.get_precision('Discount'),
        readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]},
        default=0.0)

    product_id = fields.Many2one('product.product', string='Product', domain=[('sale_ok', '=', True)], change_default=True, readonly=True, states={'draft': [('readonly', False)]}, ondelete='restrict', required=True)
    product_uom_qty = fields.Float(string='Quantity', digits_compute= dp.get_precision('Product UoS'),
        required=True, readonly=True, states={'draft': [('readonly', False)]}, default=1.0)
    product_uom = fields.Many2one('product.uom', string='Unit of Measure ', required=True, readonly=True, states={'draft': [('readonly', False)]})

    qty_delivered_manual = fields.Float(string='Delivered Qty', digits_compute= dp.get_precision('Product UoS')
            help="Delivered quantity for fields where it's set manually", default=0.0),
    qty_delivered = fields.Float(compute='_get_delivery_qty', string='Delivered Qty',
            digits_compute=dp.get_precision('Product UoS'), default=0.0)
    qty_to_invoice = fields.Float(
        compute='_get_to_invoice_qty', string='Qty To Invoice',
        digits_compute=dp.get_precision('Product UoS'), default=0.0)
    qty_invoiced = fields.Float(compute='_get_invoice_qty', string='Invoiced Qty',
        digits_compute=dp.get_precision('Product UoS'), default=0.0)

        # TODO: remove this, quantities is the only stuff that matters
    salesman_id=fields.Many2one(related='order_id.user_id', store=True, string='Salesperson')
    company_id= fields.Many2one(related='order_id.company_id', string='Company', store=True, readonly=True)
    order_partner_id= fields.Many2one(related='order_id.partner_id', store=True, string='Customer')

        # TODO: can we rename into customer lead time?
    customer_lead= fields.Float('Delivery Lead Time', required=True, default=0.0,
        help="Number of days between the order confirmation and the shipping of the products to the customer",
        readonly=True, states={'draft': [('readonly', False)]})
    procurement_ids= fields.One2many('procurement.order', 'sale_line_id', string='Procurements')

    @api.model
    def _prepare_invoice_line(self, line):
        """Prepare the dict of values to create the new invoice line for a
           sales order line. This method may be overridden to implement custom
           invoice generation (making sure to call super() to establish
           a clean extension chain).

           :param browse_record line: sale.order.line record to invoice
        """
        res = {}
        account_id = line.product_id.property_account_income_id.id
        if not account_id:
            account_id = line.product_id.categ_id.property_account_income_categ_id.id
        if not account_id:
            raise UserError(_('Please define income account for this product: "%s" (id:%d).') % \
                    (line.product_id.name, line.product_id.id,))

        fpos = line.order_id.fiscal_position_id or False
        account_id = line.order_id.fiscal_position_id.map_account(cr, uid, fpos, account_id)
        if not account_id:
            raise UserError(_('There is no Fiscal Position defined or Income category account defined for default properties of Product categories.'))

        res = {
            'name': line.name,
            'sequence': line.sequence,
            'origin': line.order_id.name,
            'account_id': account_id,
            'price_unit': line.price_unit,
            'quantity': qty,
            'discount': line.discount,
            'uos_id': line.product_uom_id,
            'product_id': line.product_id.id or False,
            'invoice_line_tax_ids': line.tax_id,
            'account_analytic_id': line.order_id.project_id,
        }
        return res

    @api.one
    def invoice_line_create(invoice_id, negative=False):
        qty = self.qty_to_invoice
        if (qty>0) or (qty<0 and negative):
            vals = self._prepare_invoice_line()
            vals['invoice_id'] = invoice_id
            inv_id = self.env['account.invoice.line'].create(vals)
            self.write({'invoice_lines': [(4, inv_id)]})

    @api.onchange('product_id')
    def product_id_change(self):
        if not self.product_id:
            return {'domain': {'product_uom': []}}

        domain = {'product_uom': [('category_id', '=', self.product_id.uom_id.category_id.id)]}
        if not (self.uom_id and (self.product_id.uom_id.category_id.id == self.uom_id.category_id.id)):
            self.uom_id = self.product_id.uom_id

        product = self.product_id.with_context(
            lang = self.order_id.partner_id.lang,
            partner_id = self.order_id.partner_id.id,
            date_order = self.order_id.date_order,
            priclist_id = self.order_id.pricelist_id.id,
            uom = self.uom_id
        )

        fpos = self.fiscal_position_id or self.order_id.partner_id.property_account_position_id
        self.tax_id = fpos.map_tax(product.taxes_id)

        name = product.name_get()[1]
        if product.description_sale:
            name += '\n'+product.description_sale
        self.name = name

        if self.pricelist_id and self.partner_id:
            self.price_unit = product.price
        return {'domain': domain}

    @api.onchange('product_uom')
    def product_uom_change(self):
        if not self.product_uom:
            self.price_unit = 0.0
            return {}
        if self.pricelist_id and self.partner_id:
            product = self.product_id.with_context(
                lang = self.order_id.partner_id.lang,
                partner_id = self.order_id.partner_id.id,
                date_order = self.order_id.date_order,
                priclist_id = self.order_id.pricelist_id.id,
                uom = self.uom_id
            )
            self.price_unit = product.price
        return {}

    @api.multi
    def unlink(self):
        if self.qty_invoiced or self.qty_delivered:
            raise UserError(_('Cannot delete a sales order line that is invoiced or delivered.'))
        return super(SaleOrderLine, self).unlink()


class MailComposeMessage(models.Model):
    _inherit = 'mail.compose.message'

    @api.multi
    def send_mail(self, auto_commit=False):
        if self.context.get('default_model') == 'sale.order' and context.get('default_res_id') and context.get('mark_so_as_sent'):
            context = dict(context, mail_post_autofollow=True)
            order = self.env['sale.order'].browse([context['default_res_id']])
            if order.state =='draft':
                order.state = 'sent'
        return super(MailComposeMessage, self).send_mail(context=context)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'
    team_id = fields.Many2one('crm.team', string='Sales Team', default='_default_team_id'),

    @api.model
    def _default_team_id(self):
        self.team_id = self.env['crm.team']._get_default_team_id()

    @api.multi
    def confirm_paid(self):
        res = super(AccountInvoice, self).confirm_paid()
        todo = {}
        for invoice in self:
            for line in invoice.line_ids:
                for sale_line in line.sale_line_ids:
                    for sale in sale_line.order_id:
                        todo[sale] = invoice.name
        sale_order_obj = self.env.get('sale.order')
        for so_id,name in todo.items():
            sale.message_post(body=_("Invoice %s paid") % (name,), context=context)
        return res

class account_invoice_line(osv.Model):
    _inherit = 'account.invoice.line'
    _columns= {
        'sale_line_ids': fields.many2many('sale.order.line', 'sale_order_line_invoice_rel', 'invoice_id', 'order_line_id',
                                          'Sale Order Lines', readonly=True, copy=False)
    }

class procurement_order(osv.osv):
    _inherit = 'procurement.order'
    _columns = {
        'sale_line_id': fields.many2one('sale.order.line', string='Sale Order Line'),
    }

class product_product(osv.Model):
    _inherit = 'product.product'

    def _sales_count(self, cr, uid, ids, field_name, arg, context=None):
        r = dict.fromkeys(ids, 0)
        domain = [
            ('state', 'in', ['confirmed', 'done']),
            ('product_id', 'in', ids),
        ]
        for group in self.pool['sale.report'].read_group(cr, uid, domain, ['product_id', 'product_uom_qty'], ['product_id'], context=context):
            r[group['product_id'][0]] = group['product_uom_qty']
        return r

    # TODO: can we remove that?
    def action_view_sales(self, cr, uid, ids, context=None):
        result = self.pool['ir.model.data'].xmlid_to_res_id(cr, uid, 'sale.action_order_line_product_tree', raise_if_not_found=True)
        result = self.pool['ir.actions.act_window'].read(cr, uid, [result], context=context)[0]
        result['domain'] = "[('product_id','in',[" + ','.join(map(str, ids)) + "])]"
        return result

    _columns = {
        'sales_count': fields.function(_sales_count, string='# Sales', type='integer'),
    }

class product_template(osv.Model):
    _inherit = 'product.template'

    def _sales_count(self, cr, uid, ids, field_name, arg, context=None):
        res = dict.fromkeys(ids, 0)
        for template in self.browse(cr, uid, ids, context=context):
            res[template.id] = sum([p.sales_count for p in template.product_variant_ids])
        return res

    # TODO: can we remove that?
    def action_view_sales(self, cr, uid, ids, context=None):
        act_obj = self.pool.get('ir.actions.act_window')
        mod_obj = self.pool.get('ir.model.data')
        product_ids = []
        for template in self.browse(cr, uid, ids, context=context):
            product_ids += [x.id for x in template.product_variant_ids]
        result = mod_obj.xmlid_to_res_id(cr, uid, 'sale.action_order_line_product_tree',raise_if_not_found=True)
        result = act_obj.read(cr, uid, [result], context=context)[0]
        result['domain'] = "[('product_id','in',[" + ','.join(map(str, product_ids)) + "])]"
        return result

    _columns = {
        'sales_count': fields.function(_sales_count, string='# Sales', type='integer'),

    }
