# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — scope tournament resolution to the login account
#
##############################################################################
from odoo import http
from odoo.http import request

from odoo.addons.auction_module.controllers.main import (
    Auction as AuctionController,
    auction_backend_home_url,
)


def _saas_account():
    """Return the SaaS account for the current user, or empty."""
    try:
        return request.env['ac.saas.account']._get_account_for_user()
    except Exception:
        return request.env['ac.saas.account']


def _saas_account_from_session():
    """Resolve SaaS account even on auth=none routes (session uid)."""
    uid = getattr(request.session, 'uid', None)
    if not uid:
        return request.env['ac.saas.account']
    try:
        return request.env['ac.saas.account'].sudo().search(
            [('user_id', '=', uid)], limit=1
        )
    except Exception:
        return request.env['ac.saas.account']


def _no_tournament_page(message=None):
    msg = message or (
        'You do not have a tournament yet. '
        'Open <strong>Tournament(s)</strong> from the home menu and create one first.'
    )
    return request.make_response(
        '<!DOCTYPE html><html><head><meta charset="utf-8"/>'
        '<title>No Tournament</title></head>'
        '<body style="font-family:system-ui,sans-serif;padding:48px;max-width:560px">'
        '<h2>No tournament yet</h2>'
        '<p>%s</p>'
        '<p><a href="%s">&#8592; Back to AuctionChamp</a></p>'
        '</body></html>' % (msg, auction_backend_home_url()),
        [('Content-Type', 'text/html; charset=utf-8')],
    )


def _frozen_account_page():
    return request.make_response(
        '<!DOCTYPE html><html><head><meta charset="utf-8"/>'
        '<title>Account Frozen</title></head>'
        '<body style="font-family:system-ui,sans-serif;padding:48px;max-width:560px">'
        '<h2>Account frozen</h2>'
        '<p>Your AuctionChamp account has expired and is frozen. '
        'Player Showcase and other auction actions are unavailable until the account '
        'is renewed.</p>'
        '<p>Go back to AuctionChamp and use <strong>Request reactivation</strong> '
        'to ask support to restore access.</p>'
        '<p><a href="%s">&#8592; Back to AuctionChamp</a></p>'
        '</body></html>' % auction_backend_home_url(),
        [('Content-Type', 'text/html; charset=utf-8')],
    )


def _block_if_account_frozen(account=None):
    """Return a frozen HTML page when the login account is expired, else None."""
    account = account or _saas_account() or _saas_account_from_session()
    if not account:
        return None
    try:
        account._sync_expiry_from_date()
        if account._is_frozen():
            return _frozen_account_page()
    except Exception:
        return None
    return None


_orig_resolve_tournament = AuctionController._resolve_tournament


def _saas_resolve_tournament(self):
    """Never fall back to another customer's active tournament for SaaS users."""
    account = _saas_account() or _saas_account_from_session()
    if account:
        user = request.env['res.users'].sudo().browse(
            getattr(request.session, 'uid', None) or request.env.user.id
        )
        linked = False
        if hasattr(user, 'get_working_tournament'):
            linked = user.get_working_tournament()
        if linked and linked.saas_account_id and linked.saas_account_id.id == account.id:
            return linked
        return request.env['auction.tournament'].sudo().search(
            [('saas_account_id', '=', account.id)],
            order='active desc, id desc',
            limit=1,
        )
    return _orig_resolve_tournament(self)


AuctionController._resolve_tournament = _saas_resolve_tournament


class AuctionSaasController(AuctionController):
    """Re-register menu shortcuts so SaaS users never see other tenants' data."""

    @http.route('/auction/showcase', type='http', auth='user', website=True)
    def auction_showcase(self, **kw):
        blocked = _block_if_account_frozen()
        if blocked:
            return blocked
        account = _saas_account()
        if account:
            tournament = self._resolve_tournament()
            if not tournament or not tournament.slug:
                return _no_tournament_page()
            if not self._tournament_auction_rules_ready(tournament):
                return self._auction_rules_required_page(tournament)
            # Dismiss pool/fixture board as soon as Player Showcase opens
            tournament.action_dismiss_projector_board()
            target = self._showcase_target_url(tournament)
            return self._showcase_loading_page(target, tournament)
        return super().auction_showcase(**kw)

    @http.route([
        '/<string:db_name>/auction/player_selector/',
        '/<string:db_name>/auction/player_selector/<string:tournament_slug>/',
    ], type='http', auth='none', website=False, sitemap=False)
    def player_selector(self, db_name, tournament_slug=None, **kw):
        """Roll Call console — scope to the login SaaS account's tournament."""
        blocked = _block_if_account_frozen()
        if blocked:
            return blocked
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            account = _saas_account_from_session()
            tournament = request.env['auction.tournament']
            if account:
                Tournament = request.env['auction.tournament'].sudo().with_context(
                    auction_skip_tournament_security=True,
                )
                if tournament_slug:
                    tournament = Tournament.search([
                        ('slug', '=', tournament_slug),
                        ('saas_account_id', '=', account.id),
                    ], limit=1)
                if not tournament:
                    tournament = self._resolve_tournament()
                if not tournament or not tournament.slug:
                    return _no_tournament_page()
                if not self._tournament_auction_rules_ready(tournament):
                    return self._auction_rules_required_page(tournament, db_name=db_name)
                # Opening player selector must clear projector pool/fixture board
                tournament.action_dismiss_projector_board()
                theme = tournament.player_display_template or 'vanilla'
                Tier = request.env['auction.player.tier'].sudo().with_context(
                    auction_skip_tournament_security=True,
                )
                tiers = Tier.search(
                    [('tournament_id', '=', tournament.id)], order='name asc',
                )
                company = request.env['res.company'].sudo().search([], limit=1)
                html = request.render('auction_module.player_sequence_selector', {
                    'tournament': tournament,
                    'theme': theme,
                    'db_name': db_name,
                    'tournament_slug': tournament.slug,
                    'tiers': tiers,
                    'res_company': company,
                }, lazy=False)
                return request.make_response(
                    html, [('Content-Type', 'text/html; charset=utf-8')]
                )
        return super().player_selector(db_name, tournament_slug=tournament_slug, **kw)

    @http.route([
        '/<string:db_name>/auction/display_auction/',
        '/<string:db_name>/auction/display_auction/<string:tournament_slug>/',
    ], type='http', auth='none', website=False, sitemap=False)
    def display_auction(self, db_name, tournament_slug=None, **kwargs):
        blocked = _block_if_account_frozen()
        if blocked:
            return blocked
        return super().display_auction(
            db_name, tournament_slug=tournament_slug, **kwargs
        )

    @http.route(
        '/<string:db_name>/<string:tournament_slug>/auction/show/team/balance',
        type='http', auth='none', website=False,
    )
    def auction_team_balance(self, db_name, tournament_slug, **kwargs):
        """Prefer the logged-in SaaS account's tournament when slug collides."""
        blocked = _block_if_account_frozen()
        if blocked:
            return blocked
        # Let the base controller open the DB; after that, if a session SaaS
        # account exists, re-resolve the tournament within that account so Bid
        # Summary never loads another tenant's empty tournament with the same slug.
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            account = _saas_account_from_session()
            if account:
                Tournament = request.env['auction.tournament'].sudo().with_context(
                    auction_skip_tournament_security=True,
                )
                tournament = Tournament.search([
                    ('slug', '=', tournament_slug),
                    ('saas_account_id', '=', account.id),
                ], limit=1)
                if not tournament:
                    # Fall back to working tournament when slug is stale
                    tournament = self._resolve_tournament()
                if tournament:
                    try:
                        html = self._render_team_balance(
                            db_name, tournament, tournament.slug or tournament_slug, **kwargs
                        )
                    except Exception:
                        return super().auction_team_balance(
                            db_name, tournament_slug, **kwargs
                        )
                    return request.make_response(html, [
                        ('Content-Type', 'text/html; charset=utf-8'),
                        ('Cache-Control', 'private, max-age=0, must-revalidate'),
                        ('X-Frame-Options', 'SAMEORIGIN'),
                    ])
        return super().auction_team_balance(db_name, tournament_slug, **kwargs)

    @http.route('/auction/my/team-balance', type='http', auth='user', website=False)
    def my_team_balance_redirect(self, **kw):
        account = _saas_account()
        if account:
            tournament = self._resolve_tournament()
            if tournament and tournament.slug:
                return request.redirect(
                    '/{}/{}/auction/show/team/balance'.format(
                        request.env.cr.dbname, tournament.slug
                    )
                )
            return _no_tournament_page()
        return super().my_team_balance_redirect(**kw)

    @http.route('/auction/my/live-board', type='http', auth='user', website=False)
    def my_live_board_redirect(self, **kw):
        account = _saas_account()
        if account:
            tournament = self._resolve_tournament()
            if tournament and tournament.slug:
                db_name = request.env.cr.dbname
                return request.redirect(
                    '/{}/{}/auction/live-board'.format(db_name, tournament.slug)
                )
            return _no_tournament_page()
        return super().my_live_board_redirect(**kw)

    @http.route('/auction/my/payment-marker', type='http', auth='user', website=False)
    def payment_marker_redirect(self, **kw):
        """SaaS: keep legacy URL working; prefer working tournament for the account."""
        account = _saas_account()
        if account:
            has_access, _ = self._get_pm_access()
            if not has_access:
                return request.make_response(
                    'Forbidden', [('Content-Type', 'text/plain')], status=403
                )
            # Prefer explicit tournament_id when opened from a tournament form
            if kw.get('tournament_id'):
                return super().payment_marker_redirect(**kw)
            tournament = self._resolve_tournament()
            if not tournament or not tournament.slug:
                return _no_tournament_page(
                    'Create a tournament first, then open Payment Tracker again.'
                )
            db_name = request.env.cr.dbname
            url = '/{}/{}/auction/payment-marker'.format(db_name, tournament.slug)
            if str(kw.get('embed') or '').lower() in ('1', 'true', 'yes'):
                url += '?embed=1'
            return request.redirect(url)
        return super().payment_marker_redirect(**kw)

    @http.route('/auction/payment-marker/resolve', type='json', auth='user', website=False)
    def payment_marker_resolve(self, tournament_id=None, **kw):
        """SaaS: resolve Payment Tracker embed URL without leaking other tenants."""
        account = _saas_account()
        if account:
            has_access, _ = self._get_pm_access()
            if not has_access:
                return {'ok': False, 'error': 'Access denied'}
            if tournament_id:
                try:
                    tid = int(tournament_id)
                except (TypeError, ValueError):
                    return {'ok': False, 'error': 'Invalid tournament'}
                tournament = request.env['auction.tournament'].sudo().browse(tid)
                if (
                    not tournament.exists()
                    or tournament.saas_account_id.id != account.id
                ):
                    return {'ok': False, 'error': 'Tournament not found'}
            else:
                tournament = self._resolve_tournament()
            if not tournament or not tournament.slug:
                return {
                    'ok': False,
                    'error': (
                        'Create a tournament first, then open Payment Tracker again.'
                    ),
                }
            return {
                'ok': True,
                'url': '/auction/payment-marker/embed?tournament_id=%s' % tournament.id,
                'tournament_id': tournament.id,
                'slug': tournament.slug or '',
            }
        return super().payment_marker_resolve(tournament_id=tournament_id, **kw)

    @http.route('/auction/payment-marker/data', type='json', auth='user', website=False)
    def payment_marker_data(self, tournament_id=None, **kw):
        """SaaS: JSON payload for native Payment Tracker client action."""
        account = _saas_account()
        if account:
            has_access, _ = self._get_pm_access()
            if not has_access:
                return {'ok': False, 'error': 'Access denied'}
            if tournament_id:
                try:
                    tid = int(tournament_id)
                except (TypeError, ValueError):
                    return {'ok': False, 'error': 'Invalid tournament'}
                tournament = request.env['auction.tournament'].sudo().browse(tid)
                if (
                    not tournament.exists()
                    or tournament.saas_account_id.id != account.id
                ):
                    return {'ok': False, 'error': 'Tournament not found'}
            else:
                tournament = self._resolve_tournament()
            if not tournament:
                return {
                    'ok': False,
                    'error': (
                        'Create a tournament first, then open Payment Tracker again.'
                    ),
                }
            return self._payment_marker_payload(tournament)
        return super().payment_marker_data(tournament_id=tournament_id, **kw)

    @http.route('/auction/payment-marker/embed', type='http', auth='user', website=False)
    def payment_marker_embed(self, tournament_id=None, **kw):
        """SaaS: only render tournaments owned by the logged-in account."""
        account = _saas_account()
        if account:
            has_access, _ = self._get_pm_access()
            if not has_access:
                return request.make_response(
                    'Forbidden', [('Content-Type', 'text/plain')], status=403
                )
            tid = tournament_id or kw.get('tournament_id')
            if tid:
                try:
                    tid = int(tid)
                except (TypeError, ValueError):
                    return _no_tournament_page('Invalid tournament.')
                tournament = request.env['auction.tournament'].sudo().browse(tid)
                if (
                    not tournament.exists()
                    or tournament.saas_account_id.id != account.id
                ):
                    return request.make_response(
                        'Forbidden', [('Content-Type', 'text/plain')], status=403
                    )
            else:
                tournament = self._resolve_tournament()
            if not tournament:
                return _no_tournament_page(
                    'Create a tournament first, then open Payment Tracker again.'
                )
            return self._render_payment_marker_page(tournament, embed=True)
        return super().payment_marker_embed(tournament_id=tournament_id, **kw)
