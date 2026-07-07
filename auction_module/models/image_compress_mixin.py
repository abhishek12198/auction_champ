# -*- coding: utf-8 -*-
import logging

from odoo import api, models
from odoo.tools.image import image_process

_logger = logging.getLogger(__name__)

_DEFAULT_QUALITY = 80
_DEFAULT_FORMAT = 'JPEG'


class ImageCompressMixin(models.AbstractModel):
    """Mixin that auto-compresses Binary image fields on every create/write.

    How to use
    ----------
    1. Add ``'auction.image.compress.mixin'`` to the model's ``_inherit``.
    2. Declare ``_compressible_image_fields`` as a dict mapping each Binary
       field name to a compression spec tuple:

         - ``(max_w, max_h)``                        → quality=80, JPEG
         - ``(max_w, max_h, quality)``                → JPEG
         - ``(max_w, max_h, quality, output_format)`` → full control
           Use ``output_format='PNG'`` for QR codes (lossless, sharp edges).

    The mixin plugs into the existing ``super()`` chain so it works
    transparently alongside any existing ``create``/``write`` overrides.

    Example::

        class AuctionTeam(models.Model):
            _name = 'auction.team'
            _inherit = ['auction.image.compress.mixin']

            _compressible_image_fields = {
                'logo': (400, 400),
            }
    """
    _name = 'auction.image.compress.mixin'
    _description = 'Auto Image Compression Mixin'

    # Subclasses override this. Keys = field names, values = spec tuples.
    _compressible_image_fields = {}

    def _compress_image_vals(self, vals):
        """Return *vals* with all declared image fields compressed in-place."""
        for field, spec in self._compressible_image_fields.items():
            raw = vals.get(field)
            if not raw:
                continue
            max_w = spec[0]
            max_h = spec[1]
            quality = spec[2] if len(spec) > 2 else _DEFAULT_QUALITY
            fmt = spec[3] if len(spec) > 3 else _DEFAULT_FORMAT
            try:
                vals[field] = image_process(
                    raw,
                    size=(max_w, max_h),
                    quality=quality,
                    output_format=fmt,
                )
            except Exception:
                _logger.warning(
                    'ImageCompressMixin: could not compress field "%s" on model "%s" — storing original.',
                    field, self._name,
                )
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._compress_image_vals(v) for v in vals_list])

    def write(self, vals):
        return super().write(self._compress_image_vals(vals))
