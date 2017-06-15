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

class ProductTemplate(modls.Model):
    _inherit = 'product.template'


    @api.multi
    def write(self, vals):
        result = super(ProductTemplate, self).write(vals)

        data = {}
        if vals['list_price'] or vals['extra_price']:
            syncid = self.env['suncid.reference'].search([('model', '=', 190), ('source', '=', 1), ('odoo_id', '=', self.id)])
            if syncid and len(syncid) == 1:
                
                m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
                data['price'] = vals['list_price'] or self.list_price
                data['special_price'] = vals['extra_price'] or self.extra_price
                m.catalog_product.update(syncid[0].source_id,{
                    'price': vals['list_price',
                    'special_price': vals['special_price']
                    })



# task to schedule
class magento_task(models.Model):
    _name = 'magento.task'

    #SALEORDERS
    #SALEORDERS
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
        address_data['street'] = data['street'].replace("\n", " ")
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
        self.env.cr.commit()

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
        self.env.cr.commit()

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
                    note += '\ncomment:'+ str(j['comment'])
                    note += '\n===============================\n'

                o_saleorder.note = note

    #PRODUCT BRAND
    #PRODUCT BRAND
    @api.model
    def sync_brands_from_magento(self):
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
        print 'Fetching magento brands...'
        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)

        magento_brands = m.catalog_product_attribute.info('manufacturer')['options']
        for b in magento_brands:
            reference = self.env['syncid.reference'].search([('model', '=', 329), ('source', '=', 1), ('source_id', '=' ,b['value'])])

            if not reference:
                #create brand and syncid
                print 'creating new brand!', b['label']
                data = {
                    'name': b['label'],
                }
                o_brand = self.env['product.brand'].create(data)

                data_sync = {
                    'model': 329,
                    'source': 1,
                    'odoo_id': o_brand.id,
                    'source_id': b['value']
                }
                o_syncidreference = self.env['syncid.reference'].create(data_sync)

    #PRODUCT CATEGORY
    #PRODUCT CATEGORY
    @api.model
    def sync_categorys_from_magento(self):
        reload(sys)
        sys.setdefaultencoding("utf-8")

        # check config and do nothing if it's missing some parameter
        if not config.domain or \
           not config.port or \
           not config.user or \
           not config.key or \
           not config.protocol:
           return

        def read_children(item):
            if item.has_key('children'):
                #print 'item', item['name'], item['category_id']
                categories[int(item['category_id'])] = {
                    'id': int(item['category_id']),
                    'name': item['name'],
                    'parent': int(item['parent_id']),
                    'item': item
                }
                read_category(item['children'], item)

        def read_category(data, parent=None):
            if type(data) is list:
                for item in data:
                    read_children(item)
            else:
                read_children(data)

        #testing
        print 'Fetching magento categorys...'
        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)

        # read categories
        categories = {}
        read_category(m.catalog_category.tree())

        # sync categories in Odoo
        for i in sorted([i for i in categories.keys()]):
            # check syncid referente before creation
            reference = self.env['syncid.reference'].search([('model', '=', 184), ('source', '=', 1), ('source_id', '=', i)])
            if len(reference) > 1:
                raise SystemExit('Category with many references: %s', categories[i]['name'])
            if not reference:
                data = {
                    'name': categories[i]['name'],
                    'active': True,
                }
                if categories[i]['parent']:
                    data['parent_id'] = self.env['syncid.reference'].search([('model', '=', 184), ('source', '=', 1), ('source_id', '=', categories[i]['parent'])])[0].odoo_id
                print '**', categories[i]['id'], categories[i]['name'], categories[i]['parent'], data
                category_id = self.env['product.category'].create(data)

                data_sync = {
                    'model': 184,
                    'source': 1,
                    'odoo_id': category_id.id,
                    'source_id': i
                }
                sync_id = self.env['syncid.reference'].create(data_sync)
                print 'new category...', categories[i]['name'], sync_id
            
    #PRODUCT SYNC
    #PRODUCT SYNC
    @api.model
    def sync_products_from_magento(self):
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
        print 'Fetching magento products...'

        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
        
        magento_filter = {'product_id':{'from':31227}}
        
        magento_products = m.catalog_product.list(magento_filter)
        
        print 'working...'
        con = 1
        for p in magento_products:
            print p['product_id']
            if con % 500 == 0:
                print 'Syncing magento products (%s - %s)' % (con, len(magento_products))
            con +=1
            # print 1
            reference = self.env['syncid.reference'].search([('model', '=', 190), ('source', '=', 1), ('source_id', '=' ,p['product_id'])])
            # print 2
            if not reference and p['type'] == 'simple':
                #create product and syncid
                print 'creating new product!', p['name']
                print 3
                pp = m.catalog_product.info(p['product_id'])
                print 4

                categ_ids = []
                categ_id = None
                for i in pp['category_ids']:
                    if i not in ['169']: # error in magento database
                        print 5
                        category = self.env['syncid.reference'].search([('model', '=', 184), ('source', '=', 1), ('source_id', '=', str(i))])
                        print 6
                        if len(category) > 1:
                            raise SystemExit('Product with many categories in syncid: %s' % pp['name'])
                        elif category:
                            categ_ids.append((6, 0, [category[0].odoo_id]))
                            categ_id = category[0].odoo_id

                data = {
                    'default_code': pp['sku'],
                    'name': pp['name'],
                    'sale_ok': True,
                    'purchase_ok': True,
                    'type': 'product',
                    'list_price': pp['price'],
                    'extra_price': pp['special_price'],
                    'categ_ids': categ_ids,
                    'categ_id': categ_id or 1,
                }

                if pp['manufacturer']:
                    product_brand_id = self.env['syncid.reference'].search([('model', '=', 329), ('source', '=', 1), ('source_id', '=', pp['manufacturer'])])
                    if product_brand_id:
                        data['product_brand_id'] = product_brand_id.odoo_id

                print 7
                o_product = self.env['product.template'].create(data)
                print 8
                data_sync = {
                    'model': 190,
                    'source': 1,
                    'odoo_id': o_product.id,
                    'source_id': pp['product_id'],
                }
                print 9
                sync_id = self.env['syncid.reference'].create(data_sync)
                print 'FINISH'
                