# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from odoo.exceptions import UserError
from pprint import pprint
import json
import sys
from datetime import datetime, date, timedelta
from magento import MagentoAPI
from . import config
import logging
import importlib
import mysql.connector

_logger = logging.getLogger(__name__)

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

    def write(self, vals):
        result = super(ProductTemplate, self).write(vals)

        data = {}
        if 'list_price' in vals or 'extra_price' in vals:
            syncid = self.env['syncid.reference'].search([('model', '=', 190), ('source', '=', 1), ('odoo_id', '=', self.id)])
            if syncid and len(syncid) == 1:
                # m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
                if 'list_price' in vals:
                    data['price'] = vals['list_price']
                    if True:
                    # if syncid[0].source_id == '29436':
                        # print 'Entro exclusion DAVIDTESTSTOCK'
                        # database = 'motoscoot_production'
                        # motoscoot_db = self.env['base.external.dbsource'].search([('name', '=', database)])
                        cnx = mysql.connector.connect(user=config.mysqluser, password=config.mysqlpassword, host=config.mysqlhost, database=config.mysqldatabase)
                        motoscoot_db = cnx.cursor()
                        motoscoot_db.execute("""update catalog_product_entity_decimal set value = %s where entity_id=%s and attribute_id=%s;""", (vals['list_price'], int(syncid[0].source_id), 75))
                        cnx.commit()
                        cnx.close()
                if 'extra_price' in vals:
                    data['special_price'] = vals['extra_price'] or self.extra_price
                    if True:
                    # if syncid[0].source_id == '29436':
                    #     print 'Entro exclusion DAVIDTESTSTOCK'
                        # database = 'motoscoot_production'
                        # motoscoot_db = self.env['base.external.dbsource'].search([('name', '=', database)])
                        cnx = mysql.connector.connect(user=config.mysqluser, password=config.mysqlpassword, host=config.mysqlhost, database=config.mysqldatabase)
                        motoscoot_db = cnx.cursor()
                        motoscoot_db.execute("""update catalog_product_entity_decimal set value = %s where entity_id=%s and attribute_id=%s;""", (vals['extra_price'], int(syncid[0].source_id), 76))
                        cnx.commit()
                        cnx.close()
                # m.catalog_product.update(syncid[0].source_id, data)
        return result


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_cancel(self):
        res = super(SaleOrder, self).action_cancel()
        if 'MAG' in self.name:# and self.state == 'draft':
            _logger.info('*** Canceling Magento Order...')
            m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
            magento_id = self.name[4:]
            order = m.sales_order.info(magento_id)
            if order:
                if order['status'] != 'canceled':
                    try:
                        order = m.sales_order.cancel(magento_id)
                    except:
                        _logger.info('*** Canceling Magento Order Error!...')
        self.write({'state': 'cancel'})
        return res


    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        if 'MAG' in self.name and self.state == 'sale':
            m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
            magento_id = self.name[4:]
            order = m.sales_order.addComment(magento_id, 'processing', 'En proceso')
        return res

    def update_magento_orders(self):
        _logger.info('*** Updating Magento Orders from tree view')
        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
        con = 1
        for item in self:
            _logger.info('*** Updating %s/%s' %  (con, len(self)))
            con +=1
            if 'MAG' in item.name and item.state == 'draft':
                magento_id = item.name[4:]
                order = m.sales_order.info({'increment_id': magento_id})
                _logger.info('*** %s' % order['increment_id'])
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

    def check_magento_order_data(self):
        _logger.info('*** Chequing Magento Order Data')
        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
        error = ''
        errors_shipping = 'Shipping address errors:\n'
        errors_billing = '\nBilling address errors:\n'
        if 'MAG' in self.name:
            magento_id = self.name[4:]
            order = m.sales_order.info({'increment_id': magento_id})
            if order:
                #checking shipping_address:
                if 'shipping_address' in order:
                    name = ('%s %s' % (order['shipping_address']['firstname'], order['shipping_address']['lastname']))
                    if self.partner_shipping_id.name != name:
                        errors_shipping += ('\n name mismatch! odoo: %s magento: %s' % (self.partner_shipping_id.name, order['shipping_address']['firstname']))
                    if self.partner_shipping_id.street != order['shipping_address']['street'].replace('\n', ' '):
                        errors_shipping += ('\n street mismatch! odoo: %s magento: %s' % (self.partner_shipping_id.street, order['shipping_address']['street']))
                    if self.partner_shipping_id.zip != order['shipping_address']['postcode']:
                        errors_shipping += ('\n zip mismatch! odoo: %s magento: %s' % (self.partner_shipping_id.zip, order['shipping_address']['postcode']))
                    if self.partner_shipping_id.city != order['shipping_address']['city']:
                        errors_shipping += ('\n city mismatch! odoo: %s magento: %s' % (self.partner_shipping_id.city, order['shipping_address']['city']))
                else:
                    errors_shipping += 'Missing magento shipping address!\n'
                if 'billing_address' in order:
                    name = ('%s %s' % (order['billing_address']['firstname'], order['billing_address']['lastname']))
                    if self.partner_invoice_id.name != name:
                        errors_billing += ('\n name mismatch! odoo: %s magento: %s' % (self.partner_invoice_id.name, order['billing_address']['firstname']))
                    if self.partner_invoice_id.street != order['billing_address']['street'].replace('\n', ' '):
                        errors_billing += ('\n street mismatch! odoo: %s magento: %s' % (self.partner_invoice_id.street, order['billing_address']['street']))
                    if self.partner_invoice_id.zip != order['billing_address']['postcode']:
                        errors_billing += ('\n zip mismatch! odoo: %s magento: %s' % (self.partner_invoice_id.zip, order['billing_address']['postcode'])) 
                    if self.partner_invoice_id.city != order['billing_address']['city']:
                        errors_billing += ('\n city mismatch! odoo: %s magento: %s' % (self.partner_shipping_id.city, order['billing_address']['city']))      
                else:
                    errors_billing += 'Missing magento billing address!\n'
            else:
                error += 'MAGENTO ORDER NOT FOUND!\n'
        else:
            error += 'MAGENTO ORDER NOT FOUND!\n'

        raise exceptions.Warning(error + '\n' + errors_shipping + '\n' + errors_billing)
  

                


# task to schedule
class magento_task(models.Model):
    _name = 'magento.task'
    _description = 'Module to manage magento tasks'

    #SALEORDERS
    #SALEORDERS
    def get_bom_product(self, product_ids):
        res = None
        product_ids.sort()
        boms =[obj.bom_id for obj in self.env['mrp.bom.line'].search([('product_id', '=', product_ids[0])])]
        for bom in boms:
            # _logger.info('*** ', bom, boms)
            bom_products = [obj.product_id.id for obj in bom.bom_line_ids]
            if product_ids == sorted(bom_products):
                res = bom.product_id
                # _logger.info('*** bingo!', res)
                break
        return res

    def create_syncid_data(self, odoo_id, magento_id, scope=None):
        syncid_data = {}
        syncid_data['model'] = 80 #res.partner model
        syncid_data['source'] = 1 #syncid magento source
        syncid_data['odoo_id'] = odoo_id
        syncid_data['source_id'] = magento_id
        syncid_data['scope'] = scope
        res = self.env['syncid.reference'].create(syncid_data)

    def create_partner_address(self, data, partner_id, mode, address_id=None, scope=None):
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
        # address_data['customer'] = False
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
            if scope != None:
                res_syncid = self.create_syncid_data(res, data['customer_address_id'], scope)
            else:
                res_syncid = self.create_syncid_data(res, data['address_id'], scope)
        
        else:
            address_data['id'] = address_id
            res = self.env['res.partner'].write(address_data)
            #maybe use this sometime in the future
            # o_rp = self.env['res.partner'].browse(address_id)
            # o_rp.write(address_data)
            

        self.env.cr.commit()

        return address_id or res #check commit da511f4ab1...

    def create_partner(self, data, scope=None):
        #method to create basic partner data
        #TODO: maybe add more accurate data in address
        customer_tags = {
            '0': None, #NOT LOGGED IN
            '1':1, #General
            '4':2, #Piloto
            '6':3, #Taller
            '7':4, #Taler NO VAT
            '8':5, #TTQ
            '9':11,#TTQ NO VAT

        }

        address_data = {}
        address_data['name'] = (data['customer_firstname'] or '') + ' ' + (data['customer_lastname'] or '')
        # address_data['street'] = data['street']
        # address_data['city'] = data['city']
        # address_data['zip'] = data['postcode']
        
        address_data['phone'] = data['billing_address']['telephone']
        address_data['email'] = data['customer_email']
        address_data['active'] = True
        # address_data['customer'] = True
        address_data['category_id'] = [(6, 0, [customer_tags[data['customer_group_id']]])]

        # if 'vat_id' in data['billing_address']:
        #     if data['billing_address']['vat_id']:
        # address_data['vat'] = data['billing_address']['vat_id']

        res = self.env['res.partner'].create(address_data)

        res_syncid = self.create_syncid_data(res, data['customer_id'], scope)
        self.env.cr.commit()

        return res

    #UPDATE SALEORDERS
    #UPDATE SALEORDERS
    def update_orders_from_magento(self):
        importlib.reload(sys)

        # check config and do nothing if it's missing some parameter
        if not config.domain or \
           not config.port or \
           not config.user or \
           not config.key or \
           not config.protocol:
           return

        #testing
        _logger.info('*** Fetching magento orders to update...')
        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
        
        order_filter = {'created_at':{'from': date.today().strftime('%Y-%m-%d')}}

        #fetch a list of magent orders from date
        orders = m.sales_order.list(order_filter)

        #filter orders to process state in ['new', 'processing']
        m_orders_list = []
        for i in orders:
            if i['state'] in ['new', 'processing', 'payment_review']:
                m_orders_list.append('MAG-'+i['increment_id'])
            elif i['state'] in ['pending_payment']:
                order = m.sales_order.info({'increment_id': i['increment_id']})
                if order:
                    if order['payment']:
                        if order['payment']['method'] == 'paypal_standard':
                            m_orders_list.append('MAG-'+i['increment_id'])
            elif i['state'] in ['complete'] and i['status'] in ['processing']:
                order = m.sales_order.info({'increment_id': i['increment_id']})
                if order:
                    if order['payment']:
                        if order['payment']['method'] == 'multibanco':
                            m_orders_list.append('MAG-'+i['increment_id'])


        #check which sale orders are allready imported in odoo
        orders_to_update = []
        for i in m_orders_list:
            o_saleorder = self.env['sale.order'].search([('name', '=', i)])
            if o_saleorder:
                orders_to_update.append(i)

        _logger.info('*** Total orders to update %i' % len(orders_to_update))
        
        for i in orders_to_update:
            _logger.info('*** Processing... %s' % i)
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

    #OSS STUFF
    def detect_oss_fiscal_position(self, country_id, order_lines):
        for line in order_lines:
            if line['tax_percent'] == '0.0000':
                return 2, 80 #intra 0 exent
        oss_fiscal_position = self.env['account.fiscal.position'].search([
            ('country_id', '=', country_id),
            ('name', 'like', 'Intra-EU B2C')
        ])
        if oss_fiscal_position:
            return oss_fiscal_position[0].id, oss_fiscal_position[0].tax_ids[0].tax_dest_id.id

                    

    def sync_orders_from_magento(self):
        importlib.reload(sys)

        # check config and do nothing if it's missing some parameter
        if not config.domain or \
           not config.port or \
           not config.user or \
           not config.key or \
           not config.protocol:
           return

        #testing
        _logger.info('*** Fetching magento orders...')
        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)

        S_IVA_21S = self.env['account.tax'].search([('description', '=', 'S_IVA21B')])
        #PRODUCT_UOM = self.env['product.uom'].search([('id','=',1)]).id

        #first get de date range to check orders
        #TODO: today minus 10 days for safe check
        # order_filter = {'created_at':{'from': date.today().strftime('%Y-%m-%d')}}
        # order_filter = {'created_at':{'from': '2017-10-15'}}
        order_filter = {'created_at':{'from': (date.today()-timedelta(7)).strftime('%Y-%m-%d')}}

        #fetch a list of magent orders from date
        orders = m.sales_order.list(order_filter)

        #filter orders to process state in ['new', 'processing']
        m_orders_list = []
        for i in orders:
            if i['state'] in ['new', 'processing', 'payment_review']:
                m_orders_list.append('MAG-'+i['increment_id'])
            elif i['state'] in ['pending_payment']:
                order = m.sales_order.info({'increment_id': i['increment_id']})
                if order:
                    if order['payment']:
                        if order['payment']['method'] in ['paypal_standard', 'mbway']:
                            m_orders_list.append('MAG-'+i['increment_id'])
            elif i['state'] in ['complete'] and i['status'] in ['processing']:
                order = m.sales_order.info({'increment_id': i['increment_id']})
                if order:
                    if order['payment']:
                        if order['payment']['method'] == 'multibanco':
                            m_orders_list.append('MAG-'+i['increment_id'])



        #check which sale orders are allready imported in odoo
        orders_to_process = []
        for i in m_orders_list:
            o_saleorder = self.env['sale.order'].search([('name', '=', i)])
            if not o_saleorder:
                orders_to_process.append(i)
            
        #processing sale orders:
        _logger.info('*** Total orders to process %s' % len(orders_to_process))

        for i in orders_to_process:
            _logger.info('*** Processing... %s' % i)
            #fetching order info
            order = m.sales_order.info({'increment_id': i[4:]})

            #manual override of specific order uncomment if necesary
            # if i[4:] == '100150732':
            #     _logger.info('*** Excluding... %s' % i)
            #     continue

            #checking partner, invoice address and shipping address
            #if not exist on odoo, create it!
            if order['state'] == 'new':
                if not order['customer_id']:
                    continue
            #TODO:partner
            m_customer_id = order['customer_id']
            #new clients hack to prevent bad assign while cleaning
            im_customer_id = int(order['customer_id'])
            
            if im_customer_id > 63972:
                #its a new client, use the new logic
                syncid_customer = self.env['syncid.reference'].search([('scope', '=', 'client'),('source','=',1),('model','=',80),('source_id','=',m_customer_id)])
                if syncid_customer:
                    o_customer_id = syncid_customer[0].odoo_id
                else:
                    o_customer_id = self.create_partner(order, 'client').id

                #TODO:billing
                m_billing_address_id = order['billing_address']['customer_address_id']
                if m_billing_address_id != None:
                    syncid_billing = self.env['syncid.reference'].search([('scope', '=', 'billing'),('source','=',1),('model','=',80),('source_id','=',m_billing_address_id)])
                    if syncid_billing:
                        o_billing_id = self.create_partner_address(order['billing_address'], o_customer_id, 'update', syncid_billing[0].odoo_id)
                    else:
                        o_billing_id = self.create_partner_address(order['billing_address'], o_customer_id, 'create', None, 'billing').id
                else:
                    o_billing_id = o_customer_id

                #TODO:shipping
                m_shipping_addess_id = order['shipping_address']['customer_address_id']
                if m_shipping_addess_id != None:
                    syncid_shipping = self.env['syncid.reference'].search([('scope', '=', 'shipment'),('source','=',1),('model','=',80),('source_id','=',m_shipping_addess_id)])
                    if syncid_shipping:
                        o_shipping_id = self.create_partner_address(order['shipping_address'], o_customer_id, 'update', syncid_shipping[0].odoo_id)
                    else:
                        o_shipping_id = self.create_partner_address(order['shipping_address'], o_customer_id, 'create', None, 'shipment').id
                else:
                    o_shipping_id = o_customer_id

            else:#old way
                syncid_customer = self.env['syncid.reference'].search([('scope','=', None),('source','=',1),('model','=',80),('source_id','=',m_customer_id)])
                if syncid_customer:
                    o_customer_id = syncid_customer[0].odoo_id
                else:
                    o_customer_id = self.create_partner(order).id

                #TODO:billing
                m_billing_address_id = order['billing_address_id']
                syncid_billing = self.env['syncid.reference'].search([('scope','=', None),('source','=',1),('model','=',80),('source_id','=',m_billing_address_id)])
                if syncid_billing:
                    o_billing_id = self.create_partner_address(order['billing_address'], o_customer_id, 'update', syncid_billing[0].odoo_id)
                else:
                    o_billing_id = self.create_partner_address(order['billing_address'], o_customer_id, 'create', None).id
                
                #TODO:shipping
                m_shipping_addess_id = order['shipping_address_id']
                syncid_shipping = self.env['syncid.reference'].search([('scope','=', None),('source','=',1),('model','=',80),('source_id','=',m_shipping_addess_id)])
                if syncid_shipping:
                    o_shipping_id = self.create_partner_address(order['shipping_address'], o_customer_id, 'update', syncid_shipping[0].odoo_id)
                else:
                    o_shipping_id = self.create_partner_address(order['shipping_address'], o_customer_id, 'create', None).id

            
            #Create sale order:
            saleorder_data = {}
            saleorder_data['name'] = i
            saleorder_data['partner_id'] = o_customer_id
            saleorder_data['partner_invoice_id'] = o_billing_id
            saleorder_data['partner_shipping_id'] = o_shipping_id
            saleorder_data['date_order'] = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S')
            saleorder_data['user_id'] = 59
            #TODO: add payment_mode info to saleorder

            #detect OSS fiscal position
            euro_tax_id = False
            GLOBAL_TAX_ID = 1
            euro_customer_id = self.env['res.partner'].browse(o_customer_id)
            if euro_customer_id.country_id and euro_customer_id.country_id.id in [
                13, 21, 23, 56, 57, 58, 60, 65, 89, 71, 76, 98, 100, 102, 110, 
                133, 134, 135, 153, 166, 180, 185, 190, 198, 201, 203 ]:#OSS EUROZONE
                fiscal_position_id, euro_tax_id = self.detect_oss_fiscal_position(euro_customer_id.country_id.id, order['items'])
                saleorder_data['fiscal_position_id'] = fiscal_position_id
            if euro_tax_id:
                GLOBAL_TAX_ID = euro_tax_id

            o_saleorder = self.env['sale.order'].create(saleorder_data)


            #Create sale order lines data:            
            bundle_product = None
            to_ignore = []
            configurable = {}
            done = True
            for line in order['items']:

                if line['item_id'] in to_ignore:
                    continue

                saleorder_line_data = {}
                saleorder_line_data['price_unit'] = 0
                saleorder_line_data['order_id'] = o_saleorder.id
                #saleorder_line_data['product_uom'] = PRODUCT_UOM
                saleorder_line_data['product_qty'] = int(float(line['qty_ordered']))
                saleorder_line_data['product_uom_qty'] = int(float(line['qty_ordered']))
                saleorder_line_data['tax_id'] = [(6, 0, [GLOBAL_TAX_ID])]

                #simple, configurable and bundle logic
                
                if line['product_type'] == 'bundle':
                    bundle_ok = False
                    bundles_parts = []
                    to_ignore.append(line['item_id'])

                    #search all the items of this bundle in the order
                    for bline in order['items']:
                        if bline['parent_item_id'] == line['item_id']:
                            p = self.env['product.product'].search([('default_code', '=', bline['sku']),('active','=',True)])
                            if p:
                                bundles_parts.append(p.id)
                            to_ignore.append(bline['item_id'])

                    #search for the proper bom and result product and save it
                    if bundles_parts:
                        _logger.info('*** entro if bundles_parts')
                        bundle_product = self.get_bom_product(bundles_parts)
                        # _logger.info('*** vuelvo get_bom_product', bundle_product)
                        if bundle_product:
                            saleorder_line_data['price_unit'] = line['base_original_price']
                            saleorder_line_data['product_id'] = bundle_product.id
                            if bundle_product.default_code:
                                saleorder_line_data['name'] = '[%s] %s' % (bundle_product.default_code, line['name'])
                            else:
                                saleorder_line_data['name'] = line['name']
                            o_saleorder_line = self.env['sale.order.line'].create(saleorder_line_data)
                            bundle_ok = True
                    
                    #if everything went OK skip following logic     
                    if bundle_ok:
                        continue
                    #else save a sync-error line
                    else:
                        saleorder_line_data['product_id'] = 15414 #sync-error product
                        saleorder_line_data['name'] = '[BUNDLE] ' + line['name']
                        o_saleorder_line = self.env['sale.order.line'].create(saleorder_line_data)
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
                
                

                product = self.env['product.product'].search([('default_code', '=', line['sku']),('active','=',True)])
                if len(product) > 1:
                    done = False
                    continue
                if product:
                    saleorder_line_data['product_id'] = product.id
                    if product.default_code:
                        saleorder_line_data['name'] = '[%s] %s' % (product.default_code, line['name'])
                    else:
                        saleorder_line_data['name'] = line['name']
                else:
                    saleorder_line_data['product_id'] = 15414 #sync-error product
                    saleorder_line_data['name'] = line['name']
                
                # saleorder_line_data['name'] = line['name']
                
                o_saleorder_line = self.env['sale.order.line'].create(saleorder_line_data)

            if not done:
                print('Problem with order.')
                continue

            #check cod_fee & shipment fee and add it as products
            if order['cod_fee']:
                saleorder_line_data = {}
                saleorder_line_data['order_id'] = o_saleorder.id
                saleorder_line_data['name'] = 'Contrarembolso'
                #saleorder_line_data['product_uom'] = PRODUCT_UOM
                saleorder_line_data['product_id'] = 64456 #15413 #product 'gastos de envio'
                saleorder_line_data['product_qty'] = 1
                saleorder_line_data['price_unit'] = float(order['cod_fee'])
                saleorder_line_data['tax_id'] = [(6, 0, [GLOBAL_TAX_ID])]
                o_saleorder_line = self.env['sale.order.line'].create(saleorder_line_data)

            if order['shipping_amount']:
                saleorder_line_data = {}
                saleorder_line_data['order_id'] = o_saleorder.id
                #saleorder_line_data['product_uom'] = PRODUCT_UOM
                saleorder_line_data['name'] = 'Gastos de envio'
                saleorder_line_data['product_id'] = 64456 #15413 #product 'gastos de envio'
                saleorder_line_data['product_qty'] = 1
                saleorder_line_data['price_unit'] = float(order['shipping_amount'])
                saleorder_line_data['tax_id'] = [(6, 0, [GLOBAL_TAX_ID])]
                o_saleorder_line = self.env['sale.order.line'].create(saleorder_line_data)

            #adding payment_mode_id
            if order['payment']:
                if order['payment']['method'] == 'realvault':
                    payment_method = self.env['account.payment.mode'].search([('name','=', 'realexredirect')])
                else:
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

            if order['discount_description']:
                saleorder_line_data = {}
                saleorder_line_data['order_id'] = o_saleorder.id
                #saleorder_line_data['product_uom'] = PRODUCT_UOM
                saleorder_line_data['name'] = 'Vale web - ' + order['discount_description'] 
                saleorder_line_data['product_id'] = 64659 #16716 #product 'VALE WEB'
                saleorder_line_data['product_qty'] = 1
                saleorder_line_data['price_unit'] = float(order['discount_amount'])
                saleorder_line_data['tax_id'] = [(6, 0, [GLOBAL_TAX_ID])]
                o_saleorder_line = self.env['sale.order.line'].create(saleorder_line_data)                

            if order['money_for_points']:
                saleorder_line_data = {}
                saleorder_line_data['order_id'] = o_saleorder.id
                #saleorder_line_data['product_uom'] = PRODUCT_UOM
                saleorder_line_data['name'] = 'Puntos web ' + str(float(order['money_for_points'])) + ' puntos' 
                saleorder_line_data['product_id'] = 64595 #21653 #product 'PUNTOS WEB'
                saleorder_line_data['product_qty'] = 1
                saleorder_line_data['price_unit'] = float(order['money_for_points'])
                saleorder_line_data['tax_id'] = [(6, 0, [GLOBAL_TAX_ID])]
                o_saleorder_line = self.env['sale.order.line'].create(saleorder_line_data)
            
    #PRODUCT BRAND
    #PRODUCT BRAND
    def sync_brands_from_magento(self):
        importlib.reload(sys)

        # check config and do nothing if it's missing some parameter
        if not config.domain or \
           not config.port or \
           not config.user or \
           not config.key or \
           not config.protocol:
           return

        #testing
        _logger.info('*** Fetching magento brands...')
        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
        
        magento_brands = m.catalog_product_attribute.info('manufacturer')['options']
        for b in magento_brands:
            reference = self.env['syncid.reference'].search([('model', '=', 329), ('source', '=', 1), ('source_id', '=' ,b['value'])])

            if not reference:
                #create brand and syncid
                _logger.info('*** creating new brand! %s' % b['label'])
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
    def sync_categorys_from_magento(self):
        importlib.reload(sys)

        # check config and do nothing if it's missing some parameter
        if not config.domain or \
           not config.port or \
           not config.user or \
           not config.key or \
           not config.protocol:
           return

        def read_children(item):
            if 'children' in item:
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
        _logger.info('*** Fetching magento categorys...')
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
                    # 'active': True,
                }
                if categories[i]['parent']:
                    data['parent_id'] = self.env['syncid.reference'].search([('model', '=', 184), ('source', '=', 1), ('source_id', '=', categories[i]['parent'])])[0].odoo_id
                _logger.info('*** ** %s %s %s %s' % (categories[i]['id'], categories[i]['name'], categories[i]['parent'], data))
                category_id = self.env['product.category'].create(data)

                data_sync = {
                    'model': 184,
                    'source': 1,
                    'odoo_id': category_id.id,
                    'source_id': i
                }
                sync_id = self.env['syncid.reference'].create(data_sync)
                _logger.info('*** new category... %s %s' % (categories[i]['name'], sync_id))
            
    #PRODUCT SYNC
    #PRODUCT SYNC
    def sync_products_from_magento(self):
        importlib.reload(sys)

        # check config and do nothing if it's missing some parameter
        if not config.domain or \
           not config.port or \
           not config.user or \
           not config.key or \
           not config.protocol:
           return

        #testing
        _logger.info('*** Fetching magento products...')

        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
        
        reference = self.env['syncid.reference'].search([('model', '=', 190), ('source', '=', 1)], order='id desc')
        magento_filter = {'product_id':{'from':reference[0].source_id}}
        
        magento_products = m.catalog_product.list(magento_filter)
        
        _logger.info('*** working...')
        con = 1
        for p in magento_products:
            _logger.info('*** %s' % p['product_id'])
            if con % 500 == 0:
                _logger.info('*** Syncing magento products (%i - %i)' % (con, len(magento_products)))
            con +=1
            reference = self.env['syncid.reference'].search([('model', '=', 190), ('source', '=', 1), ('source_id', '=' ,p['product_id'])])
            if not reference and p['type'] == 'simple':
                #create product and syncid
                _logger.info('*** creating new product! %s' % p['name'])
                pp = m.catalog_product.info(p['product_id'])
                categ_ids = []
                categ_id = None
                for i in pp['category_ids']:
                    if i not in ['169']: # error in magento database
                        category = self.env['syncid.reference'].search([('model', '=', 184), ('source', '=', 1), ('source_id', '=', str(i))])
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
                    'inventory_availability': 'always',
                    'weight': pp['weight'],
                }

                if pp['manufacturer']:
                    product_brand_id = self.env['syncid.reference'].search([('model', '=', 329), ('source', '=', 1), ('source_id', '=', pp['manufacturer'])])
                    if product_brand_id:
                        data['product_brand_id'] = product_brand_id.odoo_id

                o_product = self.env['product.template'].create(data)
                data_sync = {
                    'model': 190,
                    'source': 1,
                    'odoo_id': o_product.id,
                    'source_id': pp['product_id'],
                }
                sync_id = self.env['syncid.reference'].create(data_sync)
                _logger.info('*** FINISH')

#STOCK SYNC
#STOCK SYNC
class StockPicking(models.Model):

    _inherit = 'stock.picking'

    def write(self, vals):
        res = super(StockPicking, self).write(vals)
        if vals.get('carrier_tracking_ref'):
            _logger.info('***  %s' % vals)
            if vals.get('carrier_tracking_ref') != 'GENERATING...' and vals.get('carrier_tracking_ref'):
                for i in self:
                    if i.origin and 'MAG' in i.origin and not i.carrier_file_generated:
                        _logger.info('*** Adding tracking to Magento Order... %s' % i.origin)
                        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
                        magento_id = i.origin[4:]
                        
                        try:
                            shipment = m.sales_order_shipment.create(magento_id)
                            track = m.sales_order_shipment.addTrack(int(shipment), 'custom', i.carrier_id.name, vals['carrier_tracking_ref'] )
                        except:
                            _logger.info('*** ++ Shipment ya existente en magento!! %s' %  magento_id)
                            
                        try:
                            invoice = m.sales_order_invoice.create(magento_id)
                        except:
                            _logger.info('*** ++ Factura ya existente en magento!! %s' %  magento_id)
                            
        return res

#this controls de stock.moves when working with IN/OUT picking operations
class stock_move(models.Model):
    
    _inherit = 'stock.move'

    msync = fields.Boolean('msync', default=False, copy=False)




    #inherited method to add MAGENTO STOCK SYNC when a IN/OUT picking operation is validated
    def _action_done(self):
        _logger.info('*** entering stock_move action_dome - magento update')

        result = super(stock_move, self)._action_done()
        destination = 0
        products_to_sync = []
        products_to_sync_moves = {}
        products_stock_dict = {}
        print(result)
        for move in result:
            print('for move in self.browse')
            if move.picking_id and not move.msync:
                destination = move.picking_id.location_dest_id.id
                products_to_sync.append(move.product_id.product_tmpl_id.id)
                products_to_sync_moves[move.product_id.product_tmpl_id.id] = move
                products_stock_dict[move.product_id.product_tmpl_id.id] = move.product_id.qty_available

        syncid_obj = self.env['syncid.reference']
        _logger.info(products_to_sync) 
        if destination in [19, 12, 25, 8, 9, 5]:
            print('entro destination')
            #update magento stock!
            m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
            con = 1
            for i in products_to_sync:
                _logger.info('*** sync stock %s/%s - %s' % (con, len(products_to_sync), i))
                con +=1
                domain = [('model', '=', 190), ('source', '=', 1), ('odoo_id', '=' ,i)]
                product_syncid_references = syncid_obj.search(domain)
                if product_syncid_references:
                    product_syncid_reference = product_syncid_references[0]
                    print(product_syncid_references, product_syncid_reference, product_syncid_reference.source_id)
                    is_in_stock = '0'
                    if products_stock_dict[i] > 0:
                        is_in_stock = '1'

                    m.cataloginventory_stock_item.update({'product_id':product_syncid_reference.source_id}, {'qty':str(products_stock_dict[i]),'is_in_stock':is_in_stock})
                    products_to_sync_moves[i].msync = True
                    self.env.cr.commit()

        return result

#This controls the inventory adjustment
class StockInventory(models.Model):

    _inherit = "stock.inventory"

    def check_products(self):
        m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)
        error_msg = 'Products not found in sync table:\n'
        error_sync = ''
        error_mag = 'Products not found in magento:\n'
        for inventory_line in self.line_ids:
            domain = [('model', '=', 190), ('source', '=', 1), ('odoo_id', '=' ,inventory_line.product_id.product_tmpl_id.id)]
            product_syncid_references = self.env['syncid.reference'].search(domain)
            if not product_syncid_references:
                error_sync += inventory_line.product_id.name + '\n'
            else:
                try:
                    magento_product = m.catalog_product.info(product_syncid_references[0].source_id)
                except:
                    error_mag += inventory_line.product_id.name + ' - ' +  inventory_line.product_id.id + ' - ' +  product_syncid_references[0].source_id + '\n'
        raise exceptions.Warning(error_msg + error_sync + error_mag)

    #inherited method to add MAGENTO STOCK SYNC when a Inventory Adjustments is validated
    def _action_done(self):
        """ Finish the inventory
        @return: True
        """
        result = super(StockInventory, self)._action_done()
        syncid_obj = self.env['syncid.reference']

        for inv in self:
            if 1770 in inv.location_ids.ids:
                continue
            _logger.info('*** Initiating sync stock inventory adjustment - %s to process...' % len(inv.line_ids))
            con = 1
            m = MagentoAPI(config.domain, config.port, config.user, config.key, proto=config.protocol)

            m_check = False
            m_plist = []

            for inventory_line in inv.line_ids:
                _logger.info('*** Syncing inventory_line %s/%s - %s' % (con, len(inv.line_ids), inventory_line.product_id.id))
                con +=1
                domain = [('model', '=', 190), ('source', '=', 1), ('odoo_id', '=' ,inventory_line.product_id.product_tmpl_id.id)]
                product_syncid_references = syncid_obj.search(domain)
                if product_syncid_references:
                    product_syncid_reference = product_syncid_references[0]
                    is_in_stock = '0'
                    if inventory_line.product_id.qty_available > 0:
                        is_in_stock = '1'
                    #add error tolerance
                    # if not m_check:
                    if product_syncid_reference:
                        #found! update it!
                        m.cataloginventory_stock_item.update({'product_id':product_syncid_reference.source_id}, {'qty':str(inventory_line.product_id.qty_available),'is_in_stock':is_in_stock})
        return True
        
