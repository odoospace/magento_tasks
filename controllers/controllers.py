# -*- coding: utf-8 -*-
# from openerp import http

# class MagentoTasks(http.Controller):
#     @http.route('/magento_tasks/magento_tasks/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/magento_tasks/magento_tasks/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('magento_tasks.listing', {
#             'root': '/magento_tasks/magento_tasks',
#             'objects': http.request.env['magento_tasks.magento_tasks'].search([]),
#         })

#     @http.route('/magento_tasks/magento_tasks/objects/<model("magento_tasks.magento_tasks"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('magento_tasks.object', {
#             'object': obj
#         })