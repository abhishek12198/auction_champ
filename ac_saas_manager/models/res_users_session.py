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
        """Navbar Active Tournament for this request (session or profile)."""
        self.ensure_one()
        user = self.sudo().with_context(active_test=False)
        Tournament = self.env['auction.tournament'].sudo().with_context(active_test=False)

        preferred = []
        if user._saas_parallel_sessions_enabled():
            session = user._saas_http_session()
            if session is not None:
                raw = session.get(AC_WORKING_TOURNAMENT_SESSION_KEY)
                if raw:
                    try:
                        preferred.append(int(raw))
                    except (TypeError, ValueError):
                        pass
        if user.tournament_id:
            preferred.append(user.tournament_id.id)

        seen = set()
        for tid in preferred:
            if not tid or tid in seen:
                continue
            seen.add(tid)
            rec = Tournament.browse(tid).exists()
            if rec:
                if user._saas_parallel_sessions_enabled():
                    user._saas_seed_session_tournament(rec.id)
                return rec

        allowed = user._saas_switchable_tournaments()
        if allowed:
            return Tournament.browse(allowed.ids[:1])
        ids = list(user.tournament_ids.ids)
        return Tournament.browse(ids[:1]) if ids else Tournament.browse()

    def get_working_tournament_id(self):
        t = self.get_working_tournament()
        return t.id if t else False
