# -*- coding: utf-8 -*-
import base64
import os
import random
from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri, image_process
import requests
import werkzeug
import werkzeug.exceptions
from urllib.parse import urlparse, parse_qs
import re


def _get_default_player_photo(self):
    img_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'static', 'img', 'default_icon.png'
    )
    with open(img_path, 'rb') as f:
        return base64.b64encode(f.read())
class AuctionTeamPlayer(models.Model):
    _name = 'auction.team.player'

    @api.model
    def default_get(self, fields):
        defaults = super(AuctionTeamPlayer, self).default_get(fields)
        last_record = self.search([],limit=1, order='sl_no desc')
        if last_record:
            defaults.update({'sl_no': last_record.sl_no+1})
        else:
            defaults.update({'sl_no': 1})
        # Auto-populate tournament_id from the logged-in user's profile
        if not defaults.get('tournament_id'):
            user_tournament = self.env.user.tournament_id
            if user_tournament:
                defaults['tournament_id'] = user_tournament.id
        return defaults

    @api.model
    def create(self, vals):
        player = super().create(vals)
        # Auto-close registration when the max limit is reached
        tournament = player.tournament_id
        if tournament and tournament.registration_open and tournament.max_registrations > 0:
            draft_count = self.search_count([
                ('tournament_id', '=', tournament.id),
                ('state', '=', 'draft'),
            ])
            if draft_count >= tournament.max_registrations:
                tournament.sudo().write({'registration_open': False})
        return player

    sl_no = fields.Integer("Sl No")
    name = fields.Char(string="Name of the player", required=True)
    contact = fields.Char("Mobile Number")
    masked_contact = fields.Char(
        "Masked Mobile Number",
        compute='_compute_masked_contact',
        help='Contact number with all digits except the first and last replaced by X.',
    )
    address = fields.Text("Address")
    batting_style = fields.Char(string="Batting Style", required=True, default='Right Handed Batter')
    bowling_style = fields.Char(string="Bowling Style", required=True, default='Right Arm')
    role = fields.Char()
    photo = fields.Binary("Photo", default=_get_default_player_photo)
    photo_card = fields.Binary(
        string='Photo (Card Print)',
        compute='_compute_photo_card',
        help='Resized & compressed JPEG for PDF card printing. Reduces PDF size and generation time.',
    )
    photo_url = fields.Char("Photo URL")
    payment_url = fields.Char("Payment URL")
    state = fields.Selection([('draft', 'Draft'), ('auction', 'In Auction'), ('sold', 'Sold'), ('unsold', 'Unsold')], default='draft')
    amount_paid = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')
    tournament_type = fields.Selection(related='tournament_id.tournament_type')
    assigned_team_id = fields.Many2one('auction.team', 'Team')
    icon_player = fields.Boolean("Key Player")
    is_on_stage = fields.Boolean("Currently on Stage", default=False,
                                  help="True when this player is actively displayed in the auction stage. Only one player should have this True at a time.")
    tier_id = fields.Many2one('auction.player.tier', string='Tier')
    previous_tier_id = fields.Many2one('auction.player.tier', string='Previous Tier', help='Stores the tier before the player was promoted to Icon Player, used to restore on revoke.')
    tier_color = fields.Selection(related='tier_id.color', string='Tier Color')
    base_price = fields.Integer(string='Base Price')
    effective_base_price = fields.Integer(
        string='Effective Base Price',
        compute='_compute_effective_base_price',
    )
    notes = fields.Char()
    #other details
    current_team = fields.Char("Current Team")
    jersy_size = fields.Char('Jersy Size')
    jersy_number = fields.Char("Number in Jersy")
    jersy_name = fields.Char("Name in Jersy")
    blood_group = fields.Char("Blood Group")
    p_type =   fields.Char("Type")
    p_category = fields.Char("Category")
    payment_proof = fields.Binary("Payment Proof", help="Uploaded payment screenshot/receipt from registration form.")

    @api.depends('contact')
    def _compute_masked_contact(self):
        for player in self:
            c = player.contact or ''
            if len(c) > 2:
                player.masked_contact = c[0] + 'X' * (len(c) - 2) + c[-1]
            else:
                player.masked_contact = c

    @api.depends('photo')
    def _compute_photo_card(self):
        """Return a resized, JPEG-compressed copy of the player photo for card PDF printing.
        Reduces per-page image size from ~200KB to ~15-30KB, significantly cutting PDF size and wkhtmltopdf time."""
        for player in self:
            if player.photo:
                try:
                    player.photo_card = image_process(
                        player.photo,
                        size=(400, 500),
                        quality=70,
                        output_format='JPEG',
                    )
                except Exception:
                    player.photo_card = player.photo
            else:
                player.photo_card = False

    def _compute_effective_base_price(self):
        """Return the base price for this player from the auction setup.
        Uses the tier-specific base_point if configured, otherwise the global base_point."""
        for player in self:
            auction = self.env['auction.auction'].search(
                [('tournament_id', '=', player.tournament_id.id)], limit=1
            ) if player.tournament_id else self.env['auction.auction'].search([], limit=1)

            if not auction:
                player.effective_base_price = 0
                continue

            base = auction.base_point
            if player.tier_id and auction.tier_limit_ids:
                tier_limit = auction.tier_limit_ids.filtered(
                    lambda l: l.tier_id.id == player.tier_id.id
                )
                if tier_limit and tier_limit[0].base_point > 0:
                    base = tier_limit[0].base_point

            player.effective_base_price = base

    @api.model
    def get_sell_teams_data(self, player_id):
        """Return available teams + auction data for the web sell modal."""
        player = self.browse(int(player_id))

        # ── Tournament-level bid config ───────────────────────────────────
        # Use the player's own tournament (not just any active tournament)
        tournament = player.tournament_id
        tournament_preset_points = []
        tournament_slabs = []
        if tournament:
            if tournament.preset_points:
                try:
                    tournament_preset_points = [
                        int(x.strip())
                        for x in tournament.preset_points.split(',')
                        if x.strip().lstrip('-').isdigit()
                    ]
                except Exception:
                    pass

            splits = tournament.points_split_ids.sorted('points')
            split_list = list(splits)
            for i, split in enumerate(split_list):
                to_amt = (split_list[i + 1].points - 1) if i + 1 < len(split_list) else 99999999
                tournament_slabs.append({
                    'from_amount': split.points,
                    'to_amount': to_amt,
                    'increment': split.no_of_calls,
                })

        # Only show teams that belong to the same tournament as the player
        auction_domain = [('tournament_id', '=', tournament.id)] if tournament else []
        auctions = self.env['auction.auction'].search(auction_domain)
        teams = []
        for auction in auctions:
            if auction.remaining_players_count <= 0 or auction.remaining_points <= 0:
                continue

            # Compute effective base point for this player's tier
            effective_base = auction.base_point
            if player.tier_id and auction.tier_limit_ids:
                tier_limit = auction.tier_limit_ids.filtered(
                    lambda l: l.tier_id.id == player.tier_id.id
                )
                if tier_limit and tier_limit[0].base_point > 0:
                    effective_base = tier_limit[0].base_point

            # Tier limit remaining slots
            # Exclude the current player from the count to avoid stale-record false positives
            # (e.g. if a player was previously sold to this team without proper record cleanup).
            tier_slots_ok = True
            if player.tier_id and auction.tier_limit_ids:
                tier_limit = auction.tier_limit_ids.filtered(
                    lambda l: l.tier_id.id == player.tier_id.id
                )
                if tier_limit:
                    already_sold = self.env['auction.auction.player'].search_count([
                        ('auction_id', '=', auction.id),
                        ('player_id.tier_id', '=', player.tier_id.id),
                        ('player_id', '!=', player.id),
                    ])
                    if already_sold >= tier_limit[0].max_players:
                        tier_slots_ok = False

            # Check the team can actually afford the tier's minimum bid.
            tier_aware_max_call = auction.get_max_bid_for_team(auction, player)
            budget_ok = (effective_base <= tier_aware_max_call)

            # Prefer auction-level bid slabs (set in the wizard Slab Setup).
            # Fall back to tournament point-split slabs if none are configured.
            auction_slabs = [
                {'from_amount': s.from_amount, 'to_amount': s.to_amount, 'increment': s.increment}
                for s in auction.auction_bid_slab_ids.sorted('from_amount')
            ]
            effective_slabs = auction_slabs if auction_slabs else tournament_slabs

            teams.append({
                'team_id': auction.team_id.id,
                'team_name': auction.team_id.name,
                'auction_id': auction.id,
                'remaining_points': auction.remaining_points,
                'remaining_players': auction.remaining_players_count,
                'base_point': auction.base_point,
                'effective_base_point': effective_base,
                'max_call': tier_aware_max_call,
                'tier_slots_ok': tier_slots_ok,
                'budget_ok': budget_ok,
                'preset_points': tournament_preset_points,
                'slabs': effective_slabs,
            })
        return teams

    @api.model
    def action_sell_from_web(self, player_id, team_id, final_point):
        """Execute sell from the web auction template. Returns dict with success/error."""
        player = self.browse(int(player_id))
        if not player.exists():
            return {'success': False, 'error': 'Player not found'}

        # Guard: player must still be in auction state
        if player.state == 'sold':
            return {
                'success': False,
                'error': '%s has already been sold. Use "Recall" to correct the sale.' % player.name,
            }
        if player.state != 'auction':
            return {
                'success': False,
                'error': '%s is not available for auction (current state: %s).' % (player.name, player.state),
            }

        # Icon player guard
        icon_players = self.env['auction.team'].search([]).mapped('key_player_ids')
        if player.id in icon_players.ids:
            return {'success': False, 'error': '%s is an icon player and cannot be sold via auction' % player.name}

        auction = self.env['auction.auction'].search([('team_id', '=', int(team_id))], limit=1)
        if not auction:
            return {'success': False, 'error': 'Selected team is not part of the current auction'}

        # Tier limit check
        if player.tier_id and auction.tier_limit_ids:
            tier_limit = auction.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            if tier_limit:
                already_sold = self.env['auction.auction.player'].search_count([
                    ('auction_id', '=', auction.id),
                    ('player_id.tier_id', '=', player.tier_id.id),
                ])
                if already_sold >= tier_limit[0].max_players:
                    return {
                        'success': False,
                        'error': '%s has already reached the maximum of %d player(s) from the "%s" tier' % (
                            auction.team_id.name, tier_limit[0].max_players, player.tier_id.name
                        )
                    }

        # Effective base point (tier-specific)
        effective_base = auction.base_point
        if player.tier_id and auction.tier_limit_ids:
            tier_limit = auction.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            if tier_limit and tier_limit[0].base_point > 0:
                effective_base = tier_limit[0].base_point

        if final_point < effective_base:
            return {'success': False, 'error': 'Points cannot be below the base point of %d' % effective_base}

        # Purse must cover the tier's minimum bid
        if player.tier_id and auction.tier_limit_ids:
            _tl_min = auction.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            _tier_min = (_tl_min[0].base_point if _tl_min and _tl_min[0].base_point > 0
                         else (auction.base_point or 0))
            if _tier_min > 0 and auction.remaining_points < _tier_min:
                return {
                    'success': False,
                    'error': 'Insufficient purse for "%s" tier (requires %d pts, team has %d pts)' % (
                        player.tier_id.name, _tier_min, auction.remaining_points
                    ),
                }

        # Tier-aware max call check (covers per-tier budget reserves + tier max_call cap + slab snapping)
        tier_aware_max_call = auction.get_max_bid_for_team(auction, player)
        if final_point > tier_aware_max_call:
            return {
                'success': False,
                'error': 'Points exceed the max call of %d pts for this team' % tier_aware_max_call,
            }

        # Max points cap (global auction ceiling)
        if auction.max_limited == 'yes' and final_point > auction.max_points:
            return {'success': False, 'error': 'Points exceed the auction cap of %d' % auction.max_points}

        # Execute the sell
        auction_line_data = {'player_id': player.id, 'points': final_point}
        message = '%s sold to %s for %d points!' % (player.name, auction.team_id.name, final_point)

        auction.player_ids = [(0, 0, auction_line_data)]
        player.assigned_team_id = auction.team_id.id
        player.state = 'sold'
        # is_on_stage stays True so the live board can show the SOLD stamp
        # until the next player is called via get_random_player()
        player.create_auction_history(auction.team_id.id, message, tournament_id=player.tournament_id.id, player=player)

        # ── Stamp: record on tournament for the live board ──
        if player.tournament_id:
            display_secs = player.tournament_id.sold_display_seconds or 5
            from datetime import timedelta
            player.tournament_id.sudo().write({
                'stamp_player_id': player.id,
                'stamp_state': 'sold',
                'stamp_expires_at': fields.Datetime.now() + timedelta(seconds=display_secs + 8),
            })

        self.env.user.notify_success(message=message, title='CONGRATULATIONS!')
        return {
            'success': True,
            'message': message,
            'player_id': player.id,
            'player_name': player.name,
            'team_id': auction.team_id.id,
            'team_name': auction.team_id.name,
            'final_point': final_point,
            'display_seconds': player.tournament_id.sold_display_seconds if player.tournament_id else 5,
        }

    def print_player_cards(self):
        # Use the player's own tournament theme, not the globally "active" tournament
        tournament = self[0].tournament_id if self else None
        template = tournament.player_display_template if tournament else 'vanilla'
        report_map = {
            'vanilla':       'auction_module.action_report_player_card',
            'butterscotch':  'auction_module.action_report_player_card_butterscotch',
            'strawberry':    'auction_module.action_report_player_card_strawberry',
            'cherry':        'auction_module.action_report_player_card_cherry',
            'pistah':        'auction_module.action_report_player_card_pistah',
        }
        report_ref = report_map.get(template, 'auction_module.action_report_player_card')
        return self.env.ref(report_ref).report_action(self)

    def print_player_cards_portrait(self):
        return self.env.ref('auction_module.action_report_player_card_portrait').report_action(self)

    # def print_player_card(self):
    #     players = self.search([])
    #     return self.env.ref('auction_module.action_player_card_auction').report_action(players.ids)

    @api.model
    def action_player_card_report(self):
        # Kept for backward compatibility – delegates to print_player_cards
        return self.print_player_cards()

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.browse(docids)
        print(f"Report docs: {docs}")  # Debugging statement
        return {
            'doc_ids': docids,
            'doc_model': 'your.model',
            'docs': docs,
            'tournament': self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        }
    def get_base64_from_url(self,image_url):
        try:
            # Download the image
            response = requests.get(image_url)
            response.raise_for_status()  # Ensure we notice bad responses

            # Encode the image content in base64
            image_base64 = base64.b64encode(response.content).decode('utf-8')

            return image_base64

        except requests.exceptions.RequestException as e:
            # Handle any errors that occur during the download
            return None


    def get_image_base64_from_google_url(self, url):
        """
        Converts a Google Drive 'open?id=' URL into a direct download URL
        and returns Base64 encoded binary.
        """

        try:
            if not url:
                return False

            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            file_id = query.get("id", [None])[0]

            if not file_id:
                return False

            # Convert to direct download URL
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

            # Download the file
            response = requests.get(download_url, allow_redirects=True, timeout=20)
            response.raise_for_status()

            # Must be an image
            if "image" not in response.headers.get("Content-Type", ""):
                print("Not an image, Google returned:", response.headers.get("Content-Type"))
                return False

            return base64.b64encode(response.content)

        except Exception as e:
            print("Google Drive image fetch error:", e)
            return False


    @api.model
    def create(self, vals):
        tournament_id = self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        if tournament_id:
            vals.update({'tournament_id': tournament_id.id})

        if vals.get('photo_url', False):
            image_base64 = self.get_base64_from_url(vals.get('photo_url', False))
            if image_base64:
               vals.update({'photo': image_base64})

        if not vals.get('payment_url', False):
            vals.update({'amount_paid': False})
        player = super(AuctionTeamPlayer, self).create(vals)
        print(vals, "After printing vals")
        return player

    def write(self, vals):
        if 'photo_url' in vals:
            image_base64 = self.get_base64_from_url(vals.get('photo_url', False))
            if image_base64:
                vals.update({'photo': image_base64})
        res = super(AuctionTeamPlayer, self).write(vals)
        return res

    def get_icon_players(self, team_id):
        players_domain = [('icon_player', '=', True), ('assigned_team_id', '=', team_id)]
        players = self.search(players_domain, order='sl_no asc')
        return players

    def get_auction_players(self, tournament_id=False):
        players_domain = [('icon_player', '=', False), ('state', '=', 'auction')]
        if tournament_id:
            players_domain.append(('tournament_id', '=', tournament_id.id if hasattr(tournament_id, 'id') else tournament_id))
        players = self.search(players_domain, order='sl_no asc')
        return players

    def get_random_player(self, exclude_id=0, tournament_id=False):
        tournament = tournament_id or self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        random_player = False

        players = self.get_auction_players(tournament_id=tournament)
        if players:
            player_ids = players.ids

            # Prefer the client-supplied exclude_id (avoids is_on_stage sync issues);
            # fall back to the is_on_stage flag when no explicit hint is given.
            current_id = int(exclude_id) if exclude_id else False
            if not current_id:
                on_stage_domain = [('is_on_stage', '=', True)]
                if tournament:
                    on_stage_domain.append(('tournament_id', '=', tournament.id))
                current_on_stage = self.search(on_stage_domain, limit=1)
                current_id = current_on_stage.id if current_on_stage else False
            candidates = (
                [pid for pid in player_ids if pid != current_id]
                if current_id and len(player_ids) > 1
                else player_ids
            )

            if tournament and tournament.player_appearance_algorithm == 'random':
                random_player = self.browse(random.choice(candidates))
            else:
                random_player = self.browse(candidates[0])

        # ── Stage tracking: clear previous on-stage for this tournament only ──
        on_stage_domain = [('is_on_stage', '=', True)]
        if tournament:
            on_stage_domain.append(('tournament_id', '=', tournament.id))
        on_stage = self.search(on_stage_domain)
        if on_stage:
            on_stage.sudo().write({'is_on_stage': False})
        if random_player:
            random_player.sudo().write({'is_on_stage': True})

        # ── Clear stamp so live board switches to new player immediately ──
        if tournament and tournament.stamp_player_id:
            tournament.sudo().write({
                'stamp_player_id': False,
                'stamp_state': False,
                'stamp_expires_at': False,
            })

        return random_player

    def action_set_on_stage(self):
        """Mark this player as the current on-stage player for the live board."""
        all_on_stage = self.search([('is_on_stage', '=', True)])
        if all_on_stage:
            all_on_stage.sudo().write({'is_on_stage': False})
        for player in self:
            player.sudo().write({'is_on_stage': True})
            # Clear any active stamp so the live board switches to this player immediately
            tournament = player.tournament_id
            if tournament and tournament.stamp_player_id:
                tournament.sudo().write({
                    'stamp_player_id': False,
                    'stamp_state': False,
                    'stamp_expires_at': False,
                })
        return {'success': True}

    def action_clear_stage(self):
        """Called when the auctioneer closes the player drawer.
        Clears is_on_stage and the tournament stamp so the projector and
        live board immediately return to the waiting state."""
        for player in self:
            player.sudo().write({'is_on_stage': False})
            tournament = player.tournament_id
            if tournament:
                tournament.sudo().write({
                    'stamp_player_id': False,
                    'stamp_state': False,
                    'stamp_expires_at': False,
                })
        return True

    def action_unsold(self):
        for player in self:
            if player.state == 'auction':
                player.state = 'unsold'
                # is_on_stage stays True so the live board shows the UNSOLD stamp
                # until the next player is called via get_random_player()
                message = player.name + ' is Unsold!'
                player.create_unsold_auction_history( message, tournament_id=player.tournament_id.id,
                                              player=player)
                self.env.user.notify_success(message)
                # ── Stamp: record on tournament for the live board ──
                if player.tournament_id:
                    display_secs = player.tournament_id.sold_display_seconds or 5
                    from datetime import timedelta
                    player.tournament_id.sudo().write({
                        'stamp_player_id': player.id,
                        'stamp_state': 'unsold',
                        'stamp_expires_at': fields.Datetime.now() + timedelta(seconds=display_secs + 8),
                    })
        display_seconds = self[0].tournament_id.sold_display_seconds if self and self[0].tournament_id else 5
        return {
            'success': True,
            'display_seconds': display_seconds if display_seconds and display_seconds > 0 else 5,
        }

    def action_recall_auction_sold(self):
        context = self.env.context.copy()
        for player in self:
            if player.state == 'sold':
                auction_player = self.env['auction.auction.player'].search([('player_id', '=', player.id)])
                if auction_player:
                    auction_player.action_recall_to_auction()
        if context.get('mass_update', False):
            message =  'Selected players brought back to auction successfully!. The player will be available in the auction'
            self.env.user.notify_success(message)

    def action_auction(self):
        context = self.env.context.copy()
        for player in self:
            if player.state == 'unsold':
                player.state = 'auction'
                if not context.get('mass_update', False):
                    message = player.name + ' brought to auction successfully!'
                    self.env.user.notify_success(message)
        if context.get('mass_update', False):
            message = 'Selected players brought to auction successfully!'
            self.env.user.notify_success(message)

    def action_revoke_key_player(self):
        for player in self:
            if player.icon_player:
                team_id = player.assigned_team_id
                player.write({
                    'assigned_team_id': False,
                    'state': 'auction',
                    'icon_player': False,
                    'tier_id': player.previous_tier_id.id if player.previous_tier_id else False,
                    'previous_tier_id': False,
                })
                team_id.key_player_ids = [(3, player.id)]
                message = player.name + ' has been revoked from icon player list and brought back to auction successfully!'
                self.env.user.notify_success(message)

    def get_all_teams_for_correction(self):
        """Return all teams for this player's tournament, for the sale-correction panel."""
        player = self[0] if self else False
        if not player:
            return []
        tournament = player.tournament_id
        tournament_slabs = []
        if tournament:
            splits = tournament.points_split_ids.sorted('points')
            split_list = list(splits)
            for i, split in enumerate(split_list):
                to_amt = (split_list[i + 1].points - 1) if i + 1 < len(split_list) else 99999999
                tournament_slabs.append({
                    'from_amount': split.points,
                    'to_amount': to_amt,
                    'increment': split.no_of_calls,
                })
        auction_domain = [('tournament_id', '=', tournament.id)] if tournament else []
        auctions = self.env['auction.auction'].search(auction_domain)
        result = []
        for a in auctions:
            if not a.team_id:
                continue
            auction_slabs = [
                {'from_amount': s.from_amount, 'to_amount': s.to_amount, 'increment': s.increment}
                for s in a.auction_bid_slab_ids.sorted('from_amount')
            ]
            result.append({
                'team_id': a.team_id.id,
                'team_name': a.team_id.name,
                'team_logo': a.team_id.logo.decode('utf-8') if a.team_id.logo else '',
                'is_current': a.team_id.id == player.assigned_team_id.id,
                'slabs': auction_slabs if auction_slabs else tournament_slabs,
            })
        return result

    def action_update_sale(self, new_points, new_team_id):
        """Correct a sale: update points and/or change team. Used from the web correction panel."""
        player = self[0] if self else False
        if not player or player.state != 'sold':
            return {'success': False, 'error': 'Player is not in sold state'}
        new_team_id = int(new_team_id)
        new_points  = int(new_points)
        old_line = self.env['auction.auction.player'].search(
            [('player_id', '=', player.id)], limit=1)
        if not old_line:
            return {'success': False, 'error': 'Sale record not found'}
        old_team     = player.assigned_team_id
        team_changed = (old_team.id != new_team_id)
        if team_changed:
            new_auction = self.env['auction.auction'].search(
                [('team_id', '=', new_team_id),
                 ('tournament_id', '=', player.tournament_id.id)], limit=1)
            if not new_auction:
                return {'success': False, 'error': 'Selected team is not part of this tournament'}
            old_line.unlink()
            self.env['auction.auction.player'].create({
                'auction_id': new_auction.id,
                'player_id': player.id,
                'points': new_points,
            })
            player.assigned_team_id = new_team_id
            new_team_name = new_auction.team_id.name
            new_team_logo = new_auction.team_id.logo.decode('utf-8') if new_auction.team_id.logo else ''
        else:
            old_line.points = new_points
            new_team_name = old_team.name
            new_team_logo = old_team.logo.decode('utf-8') if old_team.logo else ''
        message = '%s sale corrected: sold to %s for %d pts' % (player.name, new_team_name, new_points)
        self.env.user.notify_success(message=message, title='Sale Updated')
        return {
            'success': True,
            'message': message,
            'new_points': new_points,
            'new_team_id': new_team_id,
            'new_team_name': new_team_name,
            'new_team_logo': new_team_logo,
        }

    def action_update_sale_points(self, new_points):
        """Update the sold points for a player (corrects typo in final bid). Points-only edit, team unchanged."""
        player = self[0] if self else False
        if not player or player.state != 'sold':
            return {'success': False, 'error': 'Player is not in sold state'}
        player_line = self.env['auction.auction.player'].search(
            [('player_id', '=', player.id)], limit=1)
        if not player_line:
            return {'success': False, 'error': 'Sale record not found'}
        old_points = player_line.points
        player_line.points = int(new_points)
        message = 'Points updated for %s: %d → %d pts' % (player.name, old_points, int(new_points))
        self.env.user.notify_success(message=message, title='Points Updated')
        return {'success': True, 'message': message, 'old_points': old_points, 'new_points': int(new_points)}

    def button_sell_player(self, player_id, other_data):
        team_id = self.env['auction.team'].browse(int(team_id))
        player = self.env['auction.team.player'].browse(int(player_id))
        auction = self.env['auction.auction'].search([('team_id', '=', int(team_id))])
        auction_line_data = {
            'player_id': player.id,
            'points': points,

        }
        message = player.name + ' sold to the '+ auction.team_id.name+' for ' + str(points) + ' points successfully!'

        auction.player_ids = [(0, 0, auction_line_data)]
        player.assigned_team_id = auction.team_id and auction.team_id.id or False
        player.state = 'sold'
        # is_on_stage stays True — cleared on next player call
        self.create_auction_history(team_id.id, message, tournament_id=player.tournament_id.id, player=player)
        self.env.user.notify_success(message)

    def create_auction_history(self, team_id, message, tournament_id, player):
        self.env['auction.history'].create(
            {
                'team_id': team_id,
                'message': message,
                'tournament_id': tournament_id,
                'player_photo': player.photo
            }
        )

    def create_unsold_auction_history(self, message, tournament_id, player):
        self.env['auction.history'].create(
            {
                'message': message,
                'tournament_id': tournament_id,
                'player_photo': player.photo
            }
        )
