# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################
from odoo import models


class MailMail(models.Model):
    _inherit = 'mail.mail'

    def _send(self, auto_commit=False, raise_exception=False, smtp_session=None):
        """Deliver mail as superuser.

        ``mail.mail.attachment_ids`` is related to ``mail.message.attachment_ids``.
        Reading that field runs ``mail.message.check_access_rule('read')``, which
        fails when the message is tied to a document the current user cannot
        access (e.g. registration PDF on ``auction.team.player`` under SaaS /
        tournament record rules) — even for Settings admins who are not uid=1.

        Once a ``mail.mail`` row exists, sending it is a system delivery step and
        must not be blocked by document ACLs on the related chatter message.
        """
        return super(MailMail, self.sudo())._send(
            auto_commit=auto_commit,
            raise_exception=raise_exception,
            smtp_session=smtp_session,
        )
