# -*- coding: utf-8 -*-

from openerp import models, fields, api
from pprint import pprint
import json
import sys
from datetime import datetime, date
from magento import MagentoAPI
import config

# http://stackoverflow.com/questions/1305532/convert-python-dict-to-object (last one)
class dict2obj(dict):
    def __init__(self, dict_):
        super(dict2obj, self).__init__(dict_)
        for key in self:
            item = self[key]
            if isinstance(item, list):
                for idx, it in enumerate(item):
                    if isinstance(it, dict):
                        item[idx] = dict2obj(it)
            elif isinstance(item, dict):
                self[key] = dict2obj(item)

    def __getattr__(self, key):
        return self[key]

    def __getstate__(self):
        return self.__dict__.copy()

    def __setstate__(self, state):
        self.__dict__.update(state)

# task to schedule
class magento_task(models.Model):
    _name = 'magento.task'

    @api.model
    def create_syncid_data(self, odoo_id, magento_id):
        syncid_data = {}
        syncid_data['model'] = 80 #res.partner model
        syncid_data['source'] = 1 #syncid magento source
        syncid_data['odoo_id'] = odoo_id
        syncid_data['source_id'] = magento_id
        res = self.env['syncid.reference'].create(syncid_data)

    @api.model
    def create_partner_address(self, data, partner_id):
        #method to create a delivery or invoice address given magento address data
        
        address_data = {}
        address_data['name'] = data['firstname'] + ' ' + data['lastname']
        address_data['street'] = data['street']
        address_data['city'] = data['city']
        address_data['zip'] = data['postcode']
        address_data['phone'] = data['telephone']
        address_data['email'] = data['email']
        address_data['active'] = True
        address_data['customer'] = False
        address_data['parent_id'] = partner_id
        if data['address_type'] == 'billing':
            address_data['type'] = 'invoice'
        elif data['address_type'] == 'shipping':
            address_data['type'] = 'delivery'

        res = self.env['res.partner'].create(address_data)

        #create syncid reference
        res_syncid = self.create_syncid_data(res, data['address_id'])

        return res

    @api.model
    def create_partner(self, data):
        #method to create basic partner data
        #TODO: maybe add more accurate data in address
        address_data = {}
        address_data['name'] = data['customer_firstname'] + ' ' + data['customer_lastname']
        # address_data['street'] = data['street']
        # address_data['city'] = data['city']
        # address_data['zip'] = data['postcode']
        # address_data['phone'] = data['telephone']
        address_data['email'] = data['customer_email']
        address_data['active'] = True
        address_data['customer'] = True

        res = self.env['res.partner'].create(address_data)

        res_syncid = self.create_syncid_data(res, data['customer_id'])

        return res

    @api.model
    def sync_orders_from_magento(self):
        reload(sys)
        sys.setdefaultencoding("utf-8")

        # check config and do nothing if it's missing some parameter
        if not config.domain or \
           not config.port or \
           not config.user or \
           not config.key or \
           not config.protocol:
           return

        #testing
        print 'Fetching magento orders...'
        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
        # orders = m.sales_order.list({'created_at': {'from': date.today().strftime('%Y-%m-%d')}})

        # for order in orders:
        #     print order
        #END testing


        S_IVA_21S = self.env['account.tax'].search([('description', '=', 'S_IVA21S')])
        PRODUCT_UOM = self.env['product.uom'].search([('id','=',1)]).id

        #first get de date range to check orders
        #TODO: today minus 10 days for safe check
        order_filter = {'created_at':{'from': date.today().strftime('%Y-%m-%d')}}

        #fetch a list of magent orders from date
        orders = m.sales_order.list(order_filter)

        #filter orders to process state in ['new', 'processing']
        m_orders_list = []
        for i in orders:
            if i['state'] in ['new', 'processing']:
                m_orders_list.append('MAG-'+i['increment_id'])

        #check which sale orders are allready imported in odoo
        orders_to_process = []
        orders_to_update = []
        for i in m_orders_list:
            o_saleorder = self.env['sale.order'].search([('name', '=', i)])
            if not o_saleorder:
                orders_to_process.append(i)
            else:
                orders_to_update.append(i)


        #processing sale orders:
        print 'Total orders to process', len(orders_to_process)

        for i in orders_to_process:
            print 'Processing...', i
            #fetching order info
            order = m.sales_order.info({'increment_id': i[4:]})

            #checking partner, invoice address and shipping address
            #if not exist on odoo, create it!

            #TODO:partner
            m_customer_id = order['customer_id']
            syncid_customer = self.env['syncid.reference'].search([('source','=',1),('model','=',80),('source_id','=',m_customer_id)])
            if syncid_customer:
                o_customer_id = syncid_customer[0].odoo_id
            else:
                o_customer_id = self.create_partner(order).id

            #TODO:billing
            m_billing_address_id = order['billing_address_id']
            syncid_billing = self.env['syncid.reference'].search([('source','=',1),('model','=',80),('source_id','=',m_billing_address_id)])
            if syncid_billing:
                o_billing_id = syncid_customer[0].odoo_id
            else:
                o_billing_id = self.create_partner_address(order['billing_address'], o_customer_id).id
            
            #TODO:shipping
            m_shipping_addess_id = order['shipping_address_id']
            syncid_shipping = self.env['syncid.reference'].search([('source','=',1),('model','=',80),('source_id','=',m_shipping_addess_id)])
            if syncid_shipping:
                o_shipping_id = syncid_customer[0].odoo_id
            else:
                o_shipping_id = self.create_partner_address(order['shipping_address'], o_customer_id).id

            
            #Create sale order:
            saleorder_data = {}
            saleorder_data['name'] = i
            saleorder_data['partner_id'] = o_customer_id
            saleorder_data['partner_invoice_id'] = o_billing_id
            saleorder_data['partner_shipping_id'] = o_shipping_id
            saleorder_data['date_order'] = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S')
            #TODO: add payment_mode info to saleorder
            o_saleorder = self.env['sale.order'].create(saleorder_data)

            #Create sale order lines data:
            for line in order['items']:
                saleorder_line_data = {}
                saleorder_line_data['order_id'] = o_saleorder.id

                product = self.env['product.product'].search([('default_code', '=', line['sku'])])
                if product:
                    saleorder_line_data['product_id'] = product.id
                else:
                    saleorder_line_data['product_id'] = 15414 #sync-error product
                
                saleorder_line_data['name'] = line['name']
                saleorder_line_data['product_uom'] = PRODUCT_UOM
                saleorder_line_data['product_uom_qty'] = int(float(line['qty_ordered']))
                if line['base_original_price']:
                    saleorder_line_data['price_unit'] = float(line['base_original_price'])
                else:
                    saleorder_line_data['price_unit'] = 0
                saleorder_line_data['tax_id'] = [(6, 0, [S_IVA_21S.id])]
                o_saleorder_line = self.env['sale.order.line'].create(saleorder_line_data)


            #check cod_fee & shipment fee and add it as products
            if order['cod_fee']:
                saleorder_line_data = {}
                saleorder_line_data['order_id'] = o_saleorder.id
                saleorder_line_data['name'] = 'Contrarembolso'
                saleorder_line_data['product_uom'] = PRODUCT_UOM
                saleorder_line_data['product_id'] = 15413 #product 'gastos de envio'
                saleorder_line_data['product_uom_qty'] = 1
                saleorder_line_data['price_unit'] = float(order['cod_fee'])
                saleorder_line_data['tax_id'] = [(6, 0, [S_IVA_21S.id])]
                o_saleorder_line = self.env['sale.order.line'].create(saleorder_line_data)

            if order['shipping_amount']:
                saleorder_line_data = {}
                saleorder_line_data['order_id'] = o_saleorder.id
                saleorder_line_data['product_uom'] = PRODUCT_UOM
                saleorder_line_data['name'] = 'Gastos de envio'
                saleorder_line_data['product_id'] = 15413 #product 'gastos de envio'
                saleorder_line_data['product_uom_qty'] = 1
                saleorder_line_data['price_unit'] = float(order['shipping_amount'])
                saleorder_line_data['tax_id'] = [(6, 0, [S_IVA_21S.id])]
                o_saleorder_line = self.env['sale.order.line'].create(saleorder_line_data)

            #adding payment_mode_id
            if order['payment']:
                payment_method = self.env['account.payment.mode'].search([('name','=', order['payment']['method'])])
                # print payment_method, order['payment']['method']
                if payment_method:
                    o_saleorder.payment_mode_id = payment_method[0]

            #adding order comments:
            if order['status_history']:
                note = '===============================\n'
                for j in order['status_history']:
                    note += 'created_at: '+ j['created_at']
                    note += '\nentity_name: '+ j['entity_name']
                    note += '\nstatus: '+ j['status']
                    note += '\n===============================\n'

                o_saleorder.note = note
