# -*- coding: utf-8 -*-
{
    'name': "Magento Tasks",

    'summary': """
        Sync data from magento platform
    """,

    'description': """
        Sync data from cobot platforms:
        
    """,

    'author': "Impulzia",
    'website': "http://www.impulzia.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/openerp/addons/base/module/module_data.xml
    # for the full list
    'category': 'Association',
    'version': '9.0.0.2',

    # any module necessary for this one to work correctly
    'depends': ['sale', 'account', 'base'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        #'templates.xml',
        'cron.xml'
    ],
    # only loaded in demonstration mode
    #'demo': [
    #    'demo.xml',
    #],
}
