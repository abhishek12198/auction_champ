odoo.define('auction_module.TournamentCalendar', function (require) {
    "use strict";

    var CalendarRenderer = require('web.CalendarRenderer');
    var CalendarView = require('web.CalendarView');
    var viewRegistry = require('web.view_registry');
    var fieldRegistry = require('web.field_registry');
    var basicFields = require('web.basic_fields');
    var qweb = require('web.core').qweb;
    var session = require('web.session');

    // Alias of phone (tel:) so calendar/form can use widget="mobile" for click-to-call.
    if (!fieldRegistry.contains('mobile')) {
        fieldRegistry.add('mobile', basicFields.FieldPhone);
    }

    var TournamentCalendarRenderer = CalendarRenderer.extend({
        config: _.extend({}, CalendarRenderer.prototype.config, {
            eventTemplate: 'auction_module.TournamentCalendarBox',
        }),
        /**
         * Odoo truncates popover titles at 30 chars — tournament names are longer.
         * Keep the full name in the popup header, with logo on the left.
         *
         * @override
         */
        _getPopoverParams: function (eventData) {
            var record = eventData.extendedProps.record;
            var displayLock = record.privacy === 'private'
                && record.partner_ids
                && record.partner_ids.includes(session.partner_id);
            var name = _.escape(record.display_name || '');
            var logoSrc = '/web/image/auction.tournament/' + record.id + '/logo';
            var title = '<span class="o_atk_cal_pop_title">' +
                '<img class="o_atk_cal_pop_logo" src="' + logoSrc + '" alt=""' +
                ' onerror="this.style.display=\'none\';' +
                'if(this.nextElementSibling){this.nextElementSibling.style.display=\'inline-flex\';}"/>' +
                '<span class="o_atk_cal_pop_logo_ph" style="display:none;" aria-hidden="true">' +
                '<i class="fa fa-trophy"></i></span>' +
                '<span class="o_atk_cal_pop_name">' + name + '</span></span>';
            return {
                animation: false,
                delay: {
                    show: 50,
                    hide: 100
                },
                trigger: 'manual',
                html: true,
                title: title,
                template: qweb.render('CalendarView.event.popover.placeholder', {
                    color: this.getColor(eventData.extendedProps.color_index),
                    displayLock: displayLock,
                }),
                container: eventData.allDay ? '.fc-view' : '.fc-scroller',
            };
        },
    });

    var TournamentCalendarView = CalendarView.extend({
        config: _.extend({}, CalendarView.prototype.config, {
            Renderer: TournamentCalendarRenderer,
        }),
    });

    viewRegistry.add('auction_tournament_calendar', TournamentCalendarView);

    return TournamentCalendarView;
});
