# -*- coding: utf-8 -*-
{
    'name': "Magento Tasks",

    'summary': """
        Sync data from magento platform to odoo withoud oca connector proof of concept
    """,

    'description': """
        WARNING: this code is highly customized for a client and should only be used as a proof of concept
        
        magento -> odoo:
        
        saleorders - news and recurring comment
        product brands aka manufactureres in magento
        product categorys
        products

        odoo -> magento:
        
        stock - picking & inventory adjustments
        sale states
        picking tracking ref
    """,

    'author': "Impulzia",
    'website': "http://www.impulzia.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/openerp/addons/base/module/module_data.xml
    # for the full list
    'category': 'Association',
    'version': '9.0.2.3',

    # any module necessary for this one to work correctly
    'depends': ['sale', 'account', 'base', 'stock'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'templates.xml',
        'cron.xml'
    ],
    # only loaded in demonstration mode
    #'demo': [
    #    'demo.xml',
    #],
}
