 # -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
 
from openerp.osv import fields, osv
from openerp import tools

class sale_report(osv.osv):
    _inherit = "sale.report"
    _columns = {
        'warehouse_id': fields.many2one('stock.warehouse', 'Warehouse',readonly=True)
    }

    def _select(self):
        return super(sale_report, self)._select() + ", s.warehouse_id as warehouse_id"

    def _group_by(self):
        return super(sale_report, self)._group_by() + ", s.warehouse_id"
