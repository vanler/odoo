# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime, timedelta
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, DATETIME_FORMATS_MAP, float_compare

from openerp import api, fields, models, _

from openerp.tools.safe_eval import safe_eval as eval
from openerp.tools.translate import _
import pytz
from openerp import SUPERUSER_ID
from openerp.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def _get_default_warehouse(self):
        company = self.env.user.company_id.id
        warehouse_ids = self.env['stock.warehouse'].search([('company_id', '=', company)])
        return warehouse_ids

    # ----------------- / Move to Sale Order Line --------------------------------------

    @api.one
    @api.depends('procurement_group_id')
    def _get_picking_ids(self):
        if not self.procurement_group_id:
            self.picking_ids = []
            self.delivery_count = 0
            return
        StockPicking = self.env['stock.picking']
        picking_ids = StockPicking.search([('group_id', '=', self.procurement_group_id.id)])
        self.picking_ids = map(lambda x: x.id, picking_ids)
        self.delivery_count = len(self.picking_ids)

    @api.multi
    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals['incoterms_id'] = self.incoterm.id or False
        return invoice_vals

    incoterm = fields.Many2one('stock.incoterms', 'Incoterms', help="International Commercial Terms are a series of predefined commercial terms used in international transactions.")
    picking_policy = fields.Selection([
        ('direct', 'Deliver each product when available'), 
        ('one', 'Deliver all products at once')],
        string='Shipping Policy', required=True, readonly=True, default='direct',
        states={'draft': [('readonly', False)], 'sent': [('readonly', False)]})
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse',
        required=True, readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]},
        default=_get_default_warehouse)
    picking_ids = fields.One2many('stock.picking', compute='_get_picking_ids', string='Picking associated to this sale')
    delivery_count = fields.Integer(string='Delivery Orders', compute='_get_picking_ids')


    @api.onchange('warehouse_id')
    def onchange_warehouse_id(self):
        if self.warehouse_id.company_id:
            self.company_id = warehouse.company_id.id

    def action_view_delivery(self, cr, uid, ids, context=None):
        '''
        This function returns an action that display existing delivery orders
        of given sales order ids. It can either be a in a list or in a form
        view, if there is only one delivery order to show.
        '''
        
        mod_obj = self.pool.get('ir.model.data')
        act_obj = self.pool.get('ir.actions.act_window')

        result = mod_obj.get_object_reference(cr, uid, 'stock', 'action_picking_tree_all')
        id = result and result[1] or False
        result = act_obj.read(cr, uid, [id], context=context)[0]

        #compute the number of delivery orders to display
        pick_ids = []
        for so in self.browse(cr, uid, ids, context=context):
            pick_ids += [picking.id for picking in so.picking_ids]

        #choose the view_mode accordingly
        if len(pick_ids) > 1:
            result['domain'] = "[('id','in',[" + ','.join(map(str, pick_ids)) + "])]"
        else:
            res = mod_obj.get_object_reference(cr, uid, 'stock', 'view_picking_form')
            result['views'] = [(res and res[1] or False, 'form')]
            result['res_id'] = pick_ids and pick_ids[0] or False
        return result

    @api.model
    def _prepare_procurement_group(self):
        res = super(SaleOrder, self)._prepare_procurement_group()
        res.update({'move_type': self.picking_policy, 'partner_id': self.partner_shipping_id.id})
        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    product_packaging = fields.Many2one('product.packaging', string='Packaging', default=False)
    route_id = fields.Many2one('stock.location.route', string='Route', domain=[('sale_selectable', '=', True)])
    product_tmpl_id = fields.Many2one('product.template', related='product_id.product_tmpl_id', string='Product Template')

    @api.multi
    def _prepare_order_line_procurement(self, group_id=False):
        vals = super(SaleOrderLine, self)._prepare_order_line_procurement(group_id=group_id)
        date_planned = vals['date_planned']
        vals.update({
            'date_planned': (date_planned - timedelta(days=self.order_id.company_id.security_lead)).strftime(DEFAULT_SERVER_DATETIME_FORMAT),
            'location_id': self.order_id.partner_shipping_id.property_stock_customer.id,
            'route_ids': self.route_id and [(4, self.route_id.id)] or [],
            'warehouse_id': self.order_id.warehouse_id and self.order_id.warehouse_id.id or False,
            'partner_dest_id': self.order_id.partner_shipping_id.id
        })
        return vals

    @api.one
    @api.depends('product_id', 'order_id.state')
    def _get_delivered_updateable(self):
        if self.product_id.type not in ('consu','product'):
            return super(SaleOrderLine, self)._get_delivered_updateable()
        self.qty_delivered_updateable = False

    @api.one
    @api.depends('procurement_ids.state')
    def _get_delivered_qty(self):
        if self.product_id.type not in ('consu','product'):
            return super(SaleOrderLine, self)._get_delivered_qty()
        qty = 0
        for proc in self.procurement_ids:
            if proc.state in ('done',):
                qty += proc.product_qty
        self.qty_delivered = qty

    @api.onchange('product_packaging')
    def product_packaging_change(self):
        if self.product_packaging:
            return self._check_package()
        return {}

    @api.multi
    def _check_package(self):
        default_uom = self.product_id.product_uom
        pack = self.product_packaging
        qty = self.product_uom_qty
        q = self.product_id.product_uom._compute_qty(pack.qty, default_uom)
        if qty and q and (qty % q):
            newqty = qty - (qty % q) + q
            warning = {
               'title': _('Warning!'),
               'message': _("This product is packaged by %d %s. You should sell %d %s.") % (pack.qty, default_uom, newqty, default_uom)
            }
        return {}

    @api.onchange('product_uom_qty')
    @api.onchange('product_id')
    def product_id_change_check_availability(self):
        if not self.product_id:
            self.product_packaging = False
            return
        self.product_tmpl_id = self.product_id.product_tmpl_id
        if self.product_id.type == 'product':
            product = self.product_id.with_context(
                lang = self.order_id.partner_id.lang,
                partner_id = self.order_id.partner_id.id,
                date_order = self.order_id.date_order,
                pricelist_id = self.order_id.pricelist_id.id,
                uom = self.product_uom.id,
                warehouse_id = self.order_id.warehouse_id.id
            )
            if float_compare(product.virtual_available, self.product_uom_qty, precision_rounding=self.product_uom.rounding) == -1:
                # Check if MTO, Cross-Dock or Drop-Shipping
                is_available = False
                for route in self.route_id+self.product_id.route_ids:
                    for pull in route.pull_ids:
                        if pull.location_id.id == self.order_id.warehouse_id.lot_stock_id.id:
                            is_available = True
                if not is_available:
                    return {
                       'title': _('Not anough inventory!'),
                       'message' : _('You plan to sell %.2f %s but you only have %.2f %s available!\nThe stock on hand is %.2f %s.') % \
                           (self.product_uom_qty, self.product_uom.name, product.virtual_available, self.product_uom.name,
                            product.qty_available, self.product_uom.name)
                    }
        return {}


class stock_location_route(models.Model):
    _inherit = "stock.location.route"
    sale_selectable = fields.Boolean(string="Selectable on Sales Order Line")

class account_invoice(models.Model):
    _inherit = 'account.invoice'
    incoterms_id = fields.Many2one('stock.incoterms', string="Incoterms",
        help="Incoterms are series of sales terms. They are used to divide transaction costs and responsibilities between buyer and seller and reflect state-of-the-art transportation practices.",
        readonly=True, states={'draft': [('readonly', False)]})

class sale_advance_payment_inv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    @api.multi
    def _prepare_advance_invoice_vals(self):
        res = super(sale_advance_payment_inv,self)._prepare_advance_invoice_vals()
        sale_obj = self.env['sale.order']
        sale_ids = context.get('active_ids', [])
        for sale in sale_obj.browse(sale_ids):
            elem = filter(lambda t: t[0] == sale.id, result)[0]
            elem[1]['incoterms_id'] = sale.incoterm.id or False
            res.append(elem)
        return res


class procurement_order(models.Model):
    _inherit = "procurement.order"

    @api.model
    def _run_move_create(self, procurement):
        print '***', procurement
        vals = super(procurement_order, self)._run_move_create(procurement)
        if self.sale_line_id:
            vals.update({'sequence': self.sale_line_id.sequence})
        return vals
