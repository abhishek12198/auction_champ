# -*- coding: utf-8 -*-
"""Stub model — allows Odoo to load after the player-card wizard was removed.

Database rows may still reference ``auction.player.card.wizard`` until
``migrations/1.5.661/post-migrate.py`` runs.  This empty transient model
keeps the registry valid during that cleanup.
"""

from odoo import models


class AuctionPlayerCardWizard(models.TransientModel):
    _name = 'auction.player.card.wizard'
    _description = 'Player Card Wizard (removed)'
