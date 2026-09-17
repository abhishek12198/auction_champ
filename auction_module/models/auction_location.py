# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AuctionLocation(models.Model):
    _name = 'auction.location'
    _description = 'City / Location'
    _parent_name = 'parent_id'
    _parent_store = True
    _rec_name = 'complete_name'
    _order = 'complete_name, id'

    name = fields.Char(string='Name', required=True, index=True)
    complete_name = fields.Char(
        string='Full Name',
        compute='_compute_complete_name',
        store=True,
        recursive=True,
        index=True,
    )
    country_id = fields.Many2one(
        'res.country',
        string='Country',
        ondelete='restrict',
        index=True,
    )
    state_id = fields.Many2one(
        'res.country.state',
        string='State',
        ondelete='restrict',
        index=True,
        domain="[('country_id', '=?', country_id)]",
    )
    parent_id = fields.Many2one(
        'auction.location',
        string='Parent',
        ondelete='restrict',
        index=True,
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        'auction.location',
        'parent_id',
        string='Child Locations',
    )
    active = fields.Boolean(default=True)

    def name_get(self):
        return [(rec.id, rec.complete_name or rec.name or '') for rec in self]

    @api.model
    def name_create(self, name):
        """Many2one quick-create writes the city name, not the computed full name."""
        rec = self.create({'name': (name or '').strip()})
        return rec.name_get()[0]

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for rec in self:
            if rec.parent_id and rec.parent_id.complete_name:
                rec.complete_name = '%s, %s' % (rec.name or '', rec.parent_id.complete_name)
            else:
                rec.complete_name = rec.name or ''

    @api.onchange('country_id')
    def _onchange_country_id(self):
        if self.state_id and self.state_id.country_id != self.country_id:
            self.state_id = False

    @api.onchange('state_id')
    def _onchange_state_id(self):
        if self.state_id and self.state_id.country_id:
            self.country_id = self.state_id.country_id

    @api.onchange('parent_id')
    def _onchange_parent_id(self):
        if not self.parent_id:
            return
        if not self.country_id:
            self.country_id = self.parent_id.country_id
        if not self.state_id:
            self.state_id = self.parent_id.state_id

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if not self._check_recursion():
            raise ValidationError('A location cannot be its own parent or child.')

    @api.constrains('state_id', 'country_id')
    def _check_state_country(self):
        for rec in self:
            if rec.state_id and rec.country_id and rec.state_id.country_id != rec.country_id:
                raise ValidationError('The selected state does not belong to the selected country.')

    def get_calendar_district(self):
        """District used on the public calendar.

        City → district → state: return the parent (district).
        District → state, or a standalone location: return self.
        """
        self.ensure_one()
        if self.parent_id and self.parent_id.parent_id:
            return self.parent_id
        return self

    def calendar_location_ids(self):
        """This district plus every nested city / location."""
        self.ensure_one()
        return set(self.search([('id', 'child_of', self.id)]).ids)

    @api.model
    def calendar_districts(self):
        """Unique district records for the calendar dropdown."""
        districts = self.browse()
        for loc in self.search([]):
            districts |= loc.get_calendar_district()
        return districts.sorted(key=lambda r: (r.name or '').lower())

    @api.model
    def match_geo_to_district(self, names):
        """Best district for a list of place names (city, district, state…)."""
        seen = []
        for raw in names or []:
            name = (raw or '').strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.append(key)
            recs = self.search([
                '|',
                ('name', 'ilike', name),
                ('complete_name', 'ilike', name),
            ], limit=30)
            exact = recs.filtered(lambda r: (r.name or '').lower() == key)
            pick = exact[:1] or recs[:1]
            if pick:
                return pick.get_calendar_district()
        return self.browse()
