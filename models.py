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

        print 'Fetching magento orders...'
        m = MagentoAPI(config.domain, config.port, config.user, config.key, config.protocol)
        orders = m.sales_order.list({'created_at': {'from': date.today().strftime('%Y-%m-%d')}})

        for order in orders:
            print order
