# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager
#
##############################################################################
from odoo import api, models


class MailMail(models.Model):
    _inherit = 'mail.mail'

    @api.model_create_multi
    def create(self, vals_list):
        """Website/public mail should not be authored by the Public User."""
        if self.env.user._is_public():
            author = self.env.company.sudo().partner_id
            email_from = self.env['ac.saas.account']._saas_email_from()
            for vals in vals_list:
                vals.setdefault('author_id', author.id if author else False)
                if not (vals.get('email_from') or '').strip():
                    vals['email_from'] = email_from
        return super().create(vals_list)

    def read(self, fields=None, load='_classic_read'):
        """mail.mail form reads inherited mail.message fields (attachments)."""
        self.check_access_rights('read')
        self.check_access_rule('read')
        return super(MailMail, self.sudo()).read(fields=fields, load=load)

    def _send(self, auto_commit=False, raise_exception=False, smtp_session=None):
        """Fill a missing From address before delivery.

        Website signup / credentials mail was failing with:
        ``You must either provide a sender address explicitly or configure
        mail.catchall.domain and mail.default.from``.
        """
        Account = self.env['ac.saas.account']
        email_from = Account._saas_email_from()
        server = Account._saas_mail_server()
        for mail in self:
            vals = {}
            if Account._saas_from_is_unroutable(mail.email_from):
                vals['email_from'] = email_from
            if Account._saas_message_id_is_unroutable(mail.message_id):
                vals['message_id'] = Account._saas_message_id()
            if server and not mail.mail_server_id:
                vals['mail_server_id'] = server.id
            if vals:
                mail.sudo().write(vals)
        return super()._send(
            auto_commit=auto_commit,
            raise_exception=raise_exception,
            smtp_session=smtp_session,
        )
