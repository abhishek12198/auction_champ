# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — inject expiry warning into web session
#
##############################################################################
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        try:
            user = self.env.user
            account = self.env['ac.saas.account']._get_account_for_user(user)
            if account:
                account._sync_expiry_from_date()
            warning = user._get_saas_expiry_warning()
            frozen = bool(account and account._is_frozen())
        except Exception:
            warning = False
            frozen = False
        result['saas_expiry_warning'] = warning or False
        result['saas_account_frozen'] = frozen
        return result
