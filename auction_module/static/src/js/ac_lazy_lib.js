/**
 * Lazy-load heavy optional libraries (Chart.js, html2canvas) on first use.
 * Keeps them out of the post-login web.assets_backend critical path.
 */
(function (root) {
    'use strict';
    var pending = {};

    function loadScript(src) {
        if (pending[src]) {
            return pending[src];
        }
        pending[src] = new Promise(function (resolve, reject) {
            var existing = document.querySelector('script[data-ac-lazy="' + src + '"]');
            if (existing) {
                existing.addEventListener('load', function () { resolve(); });
                existing.addEventListener('error', function () {
                    delete pending[src];
                    reject(new Error('Failed to load ' + src));
                });
                return;
            }
            var s = document.createElement('script');
            s.src = src;
            s.async = true;
            s.setAttribute('data-ac-lazy', src);
            s.onload = function () { resolve(); };
            s.onerror = function () {
                delete pending[src];
                reject(new Error('Failed to load ' + src));
            };
            document.head.appendChild(s);
        });
        return pending[src];
    }

    root.AcLazyLib = {
        chart: function () {
            if (root.Chart) {
                return Promise.resolve(root.Chart);
            }
            return loadScript('/auction_module/static/src/lib/chart.umd.min.js').then(function () {
                return root.Chart;
            });
        },
        html2canvas: function () {
            if (root.html2canvas) {
                return Promise.resolve(root.html2canvas);
            }
            return loadScript('/auction_module/static/src/lib/html2canvas.min.js').then(function () {
                return root.html2canvas;
            });
        },
    };
})(window);
