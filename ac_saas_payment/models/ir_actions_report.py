# -*- coding: utf-8 -*-
from urllib.parse import urlparse

from odoo import models

_INVOICE_REPORT = 'ac_saas_payment.report_saas_signup_invoice'


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _get_report_url(self, layout=None):
        """wkhtmltopdf must reach this server directly.

        web.base.url on a LAN address is not reachable from the PDF renderer,
        which otherwise waits on a network timeout before the invoice is ready.
        """
        report_name = self[:1].report_name
        if report_name != _INVOICE_REPORT:
            return super()._get_report_url(layout=layout)
        configured = (
            self.env['ir.config_parameter'].sudo().get_param('report.url') or ''
        ).strip().rstrip('/')
        if configured.startswith('http://127.0.0.1') or configured.startswith('http://localhost'):
            return configured
        base = (
            self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        ).strip()
        parsed = urlparse(base)
        port = parsed.port or 8069
        return 'http://127.0.0.1:%s' % port
