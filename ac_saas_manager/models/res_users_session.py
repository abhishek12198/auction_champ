# -*- coding: utf-8 -*-
"""Session-scoped working tournament (parallel mode) helpers on res.users."""
from odoo import api, models

# Stored in the Odoo HTTP session (per browser), not on res.users.
AC_WORKING_TOURNAMENT_SESSION_KEY = 'ac_working_tournament_id'


class ResUsersSession(models.Model):
    _inherit = 'res.users'

    @api.model
    def _saas_http_session(self):
        try:
            from odoo.http import request
            if request and getattr(request, 'session', None) is not None:
                return request.session
        except RuntimeError:
            pass
        return None

    def _saas_parallel_sessions_enabled(self):
        """True when this login may use per-browser working tournaments."""
        self.ensure_one()
        account = self.get_saas_account()
        if not account:
            return False
        return account.parallel_sessions_effective()

    def _saas_seed_session_tournament(self, tournament_id):
        session = self._saas_http_session()
        if not session or not tournament_id:
            return
        session[AC_WORKING_TOURNAMENT_SESSION_KEY] = int(tournament_id)

    def get_working_tournament(self):
        """Tournament used for menus, creates, and navbar scope for this request."""
        self.ensure_one()
        user = self.sudo()
        allowed = user._saas_switchable_tournaments()
        allowed_ids = set(allowed.ids)
        if not allowed_ids:
            return self.env['auction.tournament']
        Tournament = self.env['auction.tournament'].sudo()

        if user._saas_parallel_sessions_enabled():
            session = user._saas_http_session()
            if session is not None:
                raw = session.get(AC_WORKING_TOURNAMENT_SESSION_KEY)
                if raw:
                    try:
                        tid = int(raw)
                    except (TypeError, ValueError):
                        tid = False
                    if tid and tid in allowed_ids:
                        return Tournament.browse(tid)
                current_id = user.tournament_id.id
                if current_id and current_id in allowed_ids:
                    user._saas_seed_session_tournament(current_id)
                    return Tournament.browse(current_id)

        current_id = user.tournament_id.id
        if current_id and current_id in allowed_ids:
            return Tournament.browse(current_id)
        return Tournament.browse(allowed.ids[:1])

    def get_working_tournament_id(self):
        t = self.get_working_tournament()
        return t.id if t else False
