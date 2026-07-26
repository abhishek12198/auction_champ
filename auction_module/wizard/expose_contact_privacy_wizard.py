# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
##############################################################################

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ExposeContactPrivacyWizard(models.TransientModel):
    _name = 'auction.expose.contact.privacy.wizard'
    _description = 'Privacy Agreement — Unmask Player Contact'

    tournament_id = fields.Many2one(
        'auction.tournament',
        string='Tournament',
        required=True,
        readonly=True,
    )
    policy_version = fields.Char(
        string='Policy Version',
        readonly=True,
        default=lambda self: self.env['auction.tournament'].CONTACT_UNMASK_PRIVACY_POLICY_VERSION,
    )
    agree = fields.Boolean(
        string='I have read and agree to the Privacy Policy',
        default=False,
    )

    def action_confirm_unmask(self):
        self.ensure_one()
        if not self.agree:
            raise UserError(_(
                "Please tick the box to confirm you have read and agree to the Privacy Policy "
                "before unmasking player contact numbers."
            ))
        tournament = self.tournament_id
        Tournament = self.env['auction.tournament']
        tournament.with_context(expose_contact_privacy_ack=True).write({
            'expose_player_contact': True,
            'expose_player_contact_privacy_agreed': True,
            'expose_player_contact_agreed_user_id': self.env.uid,
            'expose_player_contact_agreed_date': fields.Datetime.now(),
            'expose_player_contact_policy_version': self.policy_version or Tournament.CONTACT_UNMASK_PRIVACY_POLICY_VERSION,
        })
        return {'type': 'ir.actions.act_window_close'}
