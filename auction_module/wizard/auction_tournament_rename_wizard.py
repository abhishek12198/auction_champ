# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import html_escape

from odoo.addons.auction_module.models.auction_tournament import _slugify


class AuctionTournamentRenameWizard(models.TransientModel):
    _name = 'auction.tournament.rename.wizard'
    _description = 'Update Tournament Name'

    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament', required=True, readonly=True,
    )
    old_name = fields.Char(
        related='tournament_id.name', string='Current Name', readonly=True,
    )
    new_name = fields.Char(string='New Name', required=True)
    old_slug = fields.Char(string='Current URL slug', compute='_compute_impact', readonly=True)
    new_slug = fields.Char(string='New URL slug', compute='_compute_impact', readonly=True)
    slug_changes = fields.Boolean(compute='_compute_impact')
    impact_html = fields.Html(
        string='URL impact',
        compute='_compute_impact',
        sanitize=False,
    )
    accept_impact = fields.Boolean(
        string='I understand the public URLs will change',
        default=False,
    )
    done = fields.Boolean(default=False)
    confirmed_name = fields.Char(readonly=True)
    confirmed_slug = fields.Char(readonly=True)
    result_html = fields.Html(string='New URLs', readonly=True, sanitize=False)

    @api.depends('tournament_id', 'tournament_id.name', 'tournament_id.slug', 'new_name')
    def _compute_impact(self):
        for wiz in self:
            tournament = wiz.tournament_id
            old_slug = (tournament.slug or '') if tournament else ''
            new_slug = _slugify(wiz.new_name or '')
            wiz.old_slug = old_slug
            wiz.new_slug = new_slug
            wiz.slug_changes = bool(old_slug and new_slug and old_slug != new_slug)
            if not tournament:
                wiz.impact_html = ''
                continue
            old_rows = tournament.get_slug_url_catalog(old_slug)
            new_rows = tournament.get_slug_url_catalog(new_slug)
            body = [
                '<table class="rn-url-table">',
                '<thead><tr>',
                '<th>Page</th><th>Current URL</th><th>URL after rename</th>',
                '</tr></thead><tbody>',
            ]
            by_name = {row['name']: row for row in new_rows}
            for old in old_rows:
                new = by_name.get(old['name']) or {}
                old_url = old.get('url') or '—'
                new_url = new.get('url') or '—'
                changed = old_url != new_url
                body.append(
                    '<tr class="%s"><td><strong>%s</strong>'
                    '<div class="rn-detail">%s</div></td>'
                    '<td class="rn-url">%s</td>'
                    '<td class="rn-url">%s</td></tr>' % (
                        'is-changed' if changed else 'is-same',
                        html_escape(old.get('name') or ''),
                        html_escape(old.get('detail') or ''),
                        html_escape(old_url),
                        html_escape(new_url),
                    )
                )
            body.append('</tbody></table>')
            wiz.impact_html = Markup(''.join(body))

    def _new_urls_html(self, tournament):
        rows = tournament.get_slug_url_catalog()
        body = [
            '<table class="rn-url-table">',
            '<thead><tr><th>Page</th><th>New URL</th></tr></thead><tbody>',
        ]
        for row in rows:
            body.append(
                '<tr><td><strong>%s</strong>'
                '<div class="rn-detail">%s</div></td>'
                '<td class="rn-url">%s</td></tr>' % (
                    html_escape(row.get('name') or ''),
                    html_escape(row.get('detail') or ''),
                    html_escape(row.get('url') or '—'),
                )
            )
        body.append('</tbody></table>')
        return Markup(''.join(body))

    def action_confirm(self):
        self.ensure_one()
        tournament = self.tournament_id
        if not tournament:
            raise UserError(_('No tournament selected.'))
        new_name = (self.new_name or '').strip()
        if not new_name:
            raise UserError(_('Enter the new tournament name.'))
        if new_name == (tournament.name or '').strip():
            raise UserError(_('The new name is the same as the current name.'))
        new_slug = _slugify(new_name)
        if not new_slug:
            raise UserError(_(
                'The new name must contain letters or numbers so a public URL can be generated.'
            ))
        if not self.accept_impact:
            raise UserError(_(
                'Tick the box to confirm you understand that public URLs will change '
                'and old links will stop working.'
            ))
        tournament.with_context(auction_rename_via_wizard=True).write({'name': new_name})
        tournament.invalidate_cache(['name', 'slug'])
        tournament = tournament.browse(tournament.id)
        self.write({
            'done': True,
            'confirmed_name': tournament.name or new_name,
            'confirmed_slug': tournament.slug or new_slug,
            'result_html': self._new_urls_html(tournament),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tournament Name Updated'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'auction_module.view_auction_tournament_rename_wizard_form'
            ).id,
            'target': 'new',
            'context': dict(self.env.context, form_view_initial_mode='readonly'),
        }
