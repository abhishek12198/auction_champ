odoo.define('auction_module.TreeStickyHeader', function (require) {
    "use strict";

    const ListView = require('web.ListView');

    ListView.include({
        // Hook to run when the tree view is mounted
        mounted: function () {
            this._super.apply(this, arguments);
            this._applyStickyHeader();
        },

        // Function to apply sticky behavior to the header
        _applyStickyHeader: function () {
            const headers = this.$el.find('.o_list_table thead th');
            headers.each(function () {
                $(this).css({
                    position: 'sticky',
                    top: 0,
                    background: '#f9f9f9',
                    zIndex: 2,
                    borderBottom: '1px solid #ddd',
                });
            });
        },
    });
});
