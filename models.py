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

class ProductTemplate(models.Model):
    _inherit = 'product.template'


    magento_sync = fields.Boolean(string='Magento sync error')
    magento_sync_date = fields.Date(string='Sync error date')


    # @api.multi
    # def write(self, vals):
    #     result = super(ProductTemplate, self).write(vals)

    #     data = {}
    #     if 'list_price' in vals or 'extra_price' in vals:
    #         syncid = self.env['syncid.reference'].search([('model', '=', 190), ('source', '=', 1), ('odoo_id', '=', self.id)])
    #         if syncid and len(syncid) == 1:
    #             m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
    #             if 'list_price' in vals:
    #                 data['price'] = vals['list_price']
    #             if 'extra_price' in vals:
    #                 data['special_price'] = vals['extra_price'] or self.extra_price
    #             m.catalog_product.update(syncid[0].source_id, data)
                
    #     return result


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.multi
    def action_cancel(self):
        if 'MAG' in self.name and self.state == 'draft':
            print 'Canceling Magento Order...'
            m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
            magento_id = self.name[4:]
            order = m.sales_order.cancel(int(magento_id))
        self.write({'state': 'cancel'})

    @api.multi
    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        if 'MAG' in self.name and self.state == 'sale':
            m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
            magento_id = self.name[4:]
            order = m.sales_order.addComment(int(magento_id), 'processing', 'En proceso')

    @api.multi
    def update_magento_orders(self):
        print 'Updating Magento Orders from tree view'
        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
        con = 1
        for item in self:
            print 'Updating %s/%s' %  (con, len(self))
            con +=1
            if 'MAG' in item.name and item.state == 'draft':
                magento_id = item.name[4:]
                order = m.sales_order.info({'increment_id': magento_id})
                print order['increment_id']
                if order['status_history']:
                    note = '===============================\n'
                    for j in order['status_history']:
                        note += 'created_at: '+ j['created_at']
                        note += '\nentity_name: '+ j['entity_name']
                        note += '\nstatus: '+ j['status']
                        note += '\ncomment:'+ str(j['comment'])
                        note += '\n===============================\n'
                    if item.note != note:
                        item.note = note


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
    def create_partner_address(self, data, partner_id, mode, address_id=None):
        #method to create a delivery or invoice address given magento address data
        
        #dictionary to match spanish region_id with odoo state code
        region_states_spain = {
            130: '15', #A coruña
            131: '01', #Alava
            132: '02', #Albacete
            133: '03', #Alicante
            134: '04', #Almeria
            135: '33', #Asturias
            136: '05', #Avila
            137: '06', #Badajoz
            138: '07', #Baleares
            139: '08', #Barcelona
            140: '09', #Burgos
            141: '10', #Caceres
            142: '11', #Cadiz
            143: '39', #Cantabria
            144: '12', #Castellon
            145: '51', #Ceuta
            146: '13', #Ciudad Real
            147: '14', #Cordoba
            148: '16', #Cuenca
            149: '17', #Girona
            150: '18', #Granada
            151: '19', #Guadalajara
            152: '20', #Guipuzcoa
            153: '21', #Huelva
            154: '22', #Huesca
            155: '23', #Jaen
            156: '26', #La rioja
            157: '35', #Las Palmas
            158: '24', #Leon
            159: '25', #Lleida
            160: '27', #Lugo
            161: '28', #Madrid
            162: '29', #Malaga
            163: '52', #Melilla
            164: '30', #Murcia
            165: '31', #Navarra
            166: '32', #Ourense
            167: '34', #Palencia
            168: '36', #Pontevedra
            169: '37', #Salamanca
            170: '38', #Santa Cruz de Tenerife
            171: '40', #Segovia
            172: '41', #Sevilla
            173: '42', #Soria
            174: '43', #Tarragona
            175: '44', #Teruel
            176: '45', #Toledo
            177: '46', #Valencia
            178: '47', #Valladolid
            179: '48', #Vizcaya
            180: '49', #Zamora
            181: '50', #Zaragoza
        }

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
        country = self.env['res.country'].search([('code', '=', data['country_id'])])
        if country:
            address_data['country_id'] = country[0].id
        
        if data['country_id'] == 'ES':
            state_code = region_states_spain[int(data['region_id'])]
            state = self.env['res.country.state'].search([('code', '=', state_code)])
            if state:
                address_data['state_id'] = state[0].id
        
        if data['address_type'] == 'billing':
            address_data['type'] = 'invoice'
        elif data['address_type'] == 'shipping':
            address_data['type'] = 'delivery'


        if mode == 'create':
            res = self.env['res.partner'].create(address_data)
            #create syncid reference
            res_syncid = self.create_syncid_data(res, data['address_id'])
        
        else:
            address_data['id'] = address_id
            res = self.env['res.partner'].write(address_data)

        self.env.cr.commit()

        return address_id or res

    @api.model
    def create_partner(self, data):
        #method to create basic partner data
        #TODO: maybe add more accurate data in address
        customer_tags = {
            '0': None, #NOT LOGGED IN
            '1':1, #General
            '4':2, #Piloto
            '6':3, #Taller
            '7':4, #Taler NO VAT
            '8':5, #TTQ
        }

        address_data = {}
        address_data['name'] = data['customer_firstname'] + ' ' + data['customer_lastname']
        # address_data['street'] = data['street']
        # address_data['city'] = data['city']
        # address_data['zip'] = data['postcode']
        
        address_data['phone'] = data['billing_address']['telephone']
        address_data['email'] = data['customer_email']
        address_data['active'] = True
        address_data['customer'] = True
        address_data['category_id'] = [(6, 0, [customer_tags[data['customer_group_id']]])]

        # if 'vat_id' in data['billing_address']:
        #     if data['billing_address']['vat_id']:
        # address_data['vat'] = data['billing_address']['vat_id']

        res = self.env['res.partner'].create(address_data)

        res_syncid = self.create_syncid_data(res, data['customer_id'])
        self.env.cr.commit()

        return res

    #UPDATE SALEORDERS
    #UPDATE SALEORDERS
    @api.model
    def update_orders_from_magento(self):
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
        print 'Fetching magento orders to update...'
        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
        
        order_filter = {'created_at':{'from': date.today().strftime('%Y-%m-%d')}}

        #fetch a list of magent orders from date
        orders = m.sales_order.list(order_filter)

        #filter orders to process state in ['new', 'processing']
        m_orders_list = []
        for i in orders:
            if i['state'] in ['new', 'processing']:
                m_orders_list.append('MAG-'+i['increment_id'])

        #check which sale orders are allready imported in odoo
        orders_to_update = []
        for i in m_orders_list:
            o_saleorder = self.env['sale.order'].search([('name', '=', i)])
            if o_saleorder:
                orders_to_update.append(i)

        print 'Total orders to update', len(orders_to_update)
        
        for i in orders_to_update:
            print 'Processing...', i
            #checking sale order
            odoo_order = self.env['sale.order'].search([('name', '=', i),('state', '=', 'draft')])
            if odoo_order:
                #updating history...
                order = m.sales_order.info({'increment_id': i[4:]})
                if order['status_history']:
                    note = '===============================\n'
                    for j in order['status_history']:
                        note += 'created_at: '+ j['created_at']
                        note += '\nentity_name: '+ j['entity_name']
                        note += '\nstatus: '+ j['status']
                        note += '\ncomment:'+ str(j['comment'])
                        note += '\n===============================\n'

                    if odoo_order.note != note:
                        odoo_order.note = note

    #SYNC SALEORDERS
    #SYNC SALEORDERS
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

        S_IVA_21S = self.env['account.tax'].search([('description', '=', 'S_IVA21B')])
        PRODUCT_UOM = self.env['product.uom'].search([('id','=',1)]).id

        #first get de date range to check orders
        #TODO: today minus 10 days for safe check
        # order_filter = {'created_at':{'from': date.today().strftime('%Y-%m-%d')}}
        order_filter = {'created_at':{'from': '2017-09-01'}}

        #fetch a list of magent orders from date
        orders = m.sales_order.list(order_filter)

        #filter orders to process state in ['new', 'processing']
        m_orders_list = []
        for i in orders:
            if i['state'] in ['new', 'processing']:
                m_orders_list.append('MAG-'+i['increment_id'])

        #check which sale orders are allready imported in odoo
        orders_to_process = []
        for i in m_orders_list:
            o_saleorder = self.env['sale.order'].search([('name', '=', i)])
            if not o_saleorder:
                orders_to_process.append(i)
            
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
                o_billing_id = self.create_partner_address(order['billing_address'], o_customer_id, 'update', syncid_billing[0].odoo_id)

            else:
                o_billing_id = self.create_partner_address(order['billing_address'], o_customer_id, 'create', None).id
            
            #TODO:shipping
            m_shipping_addess_id = order['shipping_address_id']
            syncid_shipping = self.env['syncid.reference'].search([('source','=',1),('model','=',80),('source_id','=',m_shipping_addess_id)])
            if syncid_shipping:
                o_shipping_id = self.create_partner_address(order['shipping_address'], o_customer_id, 'update', syncid_customer[0].odoo_id)
            else:
                o_shipping_id = self.create_partner_address(order['shipping_address'], o_customer_id, 'create', None).id

            
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
            bundles = []
            configurable = {}
            for line in order['items']:
                saleorder_line_data = {}
                saleorder_line_data['price_unit'] = 0

                #simple, configurable and bundle logic
                if line['product_type'] == 'bundle':
                    bundles.append(int(line['item_id']))
                    continue
                if line['product_type'] == 'configurable':
                    configurable[line['item_id']] = float(line['base_original_price'])
                    continue
                if line['product_type'] == 'simple':
                    if line['parent_item_id']:
                        if line['parent_item_id'] in configurable:
                            saleorder_line_data['price_unit'] = configurable[line['parent_item_id']]
                        else:
                            if line['base_original_price']:
                                saleorder_line_data['price_unit'] = float(line['base_original_price'])
                    else:
                        if line['base_original_price']:
                            saleorder_line_data['price_unit'] = float(line['base_original_price'])
                
                saleorder_line_data['order_id'] = o_saleorder.id

                product = self.env['product.product'].search([('default_code', '=', line['sku'])])
                if product:
                    saleorder_line_data['product_id'] = product.id
                else:
                    saleorder_line_data['product_id'] = 15414 #sync-error product
                
                saleorder_line_data['name'] = line['name']
                saleorder_line_data['product_uom'] = PRODUCT_UOM
                saleorder_line_data['product_uom_qty'] = int(float(line['qty_ordered']))
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
        
        magento_filter = {'product_id':{'from':31579}}
        
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


#STOCK SYNC
#STOCK SYNC


class StockPicking(models.Model):

    _inherit = 'stock.picking'

    def write(self, cr, uid, ids, vals, context=None):
        res = super(StockPicking, self).write(cr, uid, ids, vals, context=context)
        if vals.get('carrier_tracking_ref'):
            print vals
            for i in self.browse(cr, uid, ids, context=context):
                if 'MAG' in i.origin:
                    print 'Adding tracking to Magento Order...', i.origin
                    m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
                    magento_id = i.origin[4:]
                    shipment = m.sales_order_shipment.create(int(magento_id))
                    track = m.sales_order_shipment.addTrack(int(shipment), 'custom', i.carrier_id.name, vals['carrier_tracking_ref'] )
                    order = m.sales_order.addComment(int(magento_id), 'completed', 'Completado')
        return res






#this controls de stock.moves when working with IN/OUT picking operations
class stock_move(models.Model):
    
    _inherit = 'stock.move'

    #inherited method to add MAGENTO STOCK SYNC when a IN/OUT picking operation is validated
    def action_done(self, cr, uid, ids, context=None):
        print 'entering stock_move action_dome - magento update'

        result = super(stock_move, self).action_done(cr, uid, ids,
                                                        context=context)
        destination = 0
        products_to_sync = []
        products_stock_dict = {}
        for move in self.browse(cr, uid, ids, context=context):
            if move.picking_id:
                destination = move.picking_id.location_dest_id.id
                products_to_sync.append(move.product_id.product_tmpl_id.id)
                products_stock_dict[move.product_id.product_tmpl_id.id] = move.product_id.qty_available

        syncid_obj = self.pool.get("syncid.reference")
        product_obj = self.pool.get("product.product")
        
        if destination in [19, 12, 25, 8, 9]:
            #update magento stock!
            m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
            con = 1
            for i in products_to_sync:
                print 'sync stock %s/%s - %s' % (con, len(products_to_sync), i)
                con +=1
                domain = [('model', '=', 190), ('source', '=', 1), ('odoo_id', '=' ,i)]
                product_syncid_references = syncid_obj.search(cr, uid, domain, context=context)
                if product_syncid_references:
                    product_syncid_reference = syncid_obj.browse(cr, uid, product_syncid_references, context=context)
                    is_in_stock = '0'
                    # print product_syncid_reference[0].source_id, products_stock_dict[i]
                    if products_stock_dict[i] > 0:
                        is_in_stock = '1'
                    # print 'is_in_stock', is_in_stock
                    m.cataloginventory_stock_item.update(product_syncid_reference[0].source_id, {'qty':str(products_stock_dict[i]),'is_in_stock':is_in_stock})
        
        return result

#This controls the inventory adjustment
class StockInventory(models.Model):

    _inherit = "stock.inventory"

    #inherited method to add MAGENTO STOCK SYNC when a Inventory Adjustments is validated
    def action_done(self, cr, uid, ids, context=None):
        """ Finish the inventory
        @return: True
        """

        result = super(StockInventory, self).action_done(cr, uid, ids, context=context)
        syncid_obj = self.pool.get("syncid.reference")

        for inv in self.browse(cr, uid, ids, context=context):
            print 'Initiating sync stock inventory adjustment - %s to process...' % len(inv.line_ids)
            con = 1
            m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)

            m_check = False
            m_plist = []
            if len(inv.line_ids) >1:
                print 'Multiple sync stock inventory adjunstment...Fetching catalog for checks'
                m_check = True
                m_products = m.catalog_product.list()
                for i in m_products:
                    m_plist.append(int(i['product_id']))
                print 'Catalog properly fetched!'


            for inventory_line in inv.line_ids:
                print 'Syncing inventory_line %s/%s - %s' % (con, len(inv.line_ids), inventory_line.product_id.id)
                con +=1
                domain = [('model', '=', 190), ('source', '=', 1), ('odoo_id', '=' ,inventory_line.product_id.product_tmpl_id.id)]
                product_syncid_references = syncid_obj.search(cr, uid, domain, context=context)
                if product_syncid_references:
                    product_syncid_reference = syncid_obj.browse(cr, uid, product_syncid_references, context=context)
                    is_in_stock = '0'
                    if inventory_line.product_id.qty_available > 0:
                        is_in_stock = '1'

                    #add error tolerance
                    if not m_check:
                        #found! update it!
                        m.cataloginventory_stock_item.update(product_syncid_reference[0].source_id, {'qty':str(inventory_line.product_id.qty_available),'is_in_stock':is_in_stock})
                    else:
                        if int(product_syncid_reference[0].source_id) in m_plist:
                            m.cataloginventory_stock_item.update(product_syncid_reference[0].source_id, {'qty':str(inventory_line.product_id.qty_available),'is_in_stock':is_in_stock})
                        else:
                            #not found! manage error
                            # self.pool.get("product.template").write(inventory_line.product_id.product_tmpl_id.id, {'magento_sync': True, 'magento_sync_date': datetime.now()})
                            inventory_line.product_id.product_tmpl_id.write({'magento_sync': True, 'magento_sync_date': datetime.now()})
        return True

                