# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager
#
##############################################################################
from odoo import api, models
from odoo.exceptions import AccessError


class MailMessage(models.Model):
    _inherit = 'mail.message'

    @api.model
    def _get_message_id(self, values):
        """Use a real mail domain, not the laptop hostname (spam filters drop those)."""
        message_id = super()._get_message_id(values)
        Account = self.env['ac.saas.account']
        if Account._saas_message_id_is_unroutable(message_id):
            return Account._saas_message_id()
        return message_id

    def check_access_rule(self, operation):
        """Allow Settings / SaaS managers to open transactional emails.

        Website signup (public) and ``mail.mail.sudo().create()`` produce
        ``mail.message`` rows whose author is Public or Superuser. Opening
        them in Technical → Emails as a normal admin (uid != 1) fails
        ``mail.message`` record rules: the user is not the author, is not
        a notified partner, and the message has no document.
        """
        try:
            return super().check_access_rule(operation)
        except AccessError:
            if operation != 'read':
                raise
            user = self.env.user
            if user.has_group('base.group_system') or user.has_group(
                'ac_saas_manager.group_saas_manager'
            ):
                return
            raise
