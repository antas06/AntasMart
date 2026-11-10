/* Shared product type-ahead for barcode inputs.
   Lightweight, no dependencies, caches results per query. */
(function () {
    'use strict';

    window.initProductSuggestions = function (options) {
        var input = document.querySelector(options.inputSelector || '.barcode-input');
        var box = document.getElementById(options.boxId);
        var form = document.getElementById(options.formId);
        if (!input || !box || !form) return;

        var endpoint = options.endpoint;
        var delay = options.delay || 180;
        var timer;
        var cache = new Map();

        function hide() {
            box.hidden = true;
            box.replaceChildren();
        }

        function render(products) {
            box.replaceChildren();
            if (!products.length) {
                hide();
                return;
            }

            products.forEach(function (product) {
                var item = document.createElement('button');
                item.type = 'button';
                item.className = 'suggestion-item';

                var title = document.createElement('span');
                title.className = 'suggestion-title';
                title.textContent =
                    product.name +
                    (product.weight ? ' (' + product.weight + ')' : '');

                var meta = document.createElement('span');
                meta.className = 'suggestion-meta';
                meta.textContent =
                    'Barcode: ' + product.barcode +
                    ' · ₹' + product.price +
                    ' · Stock: ' + product.quantity;

                item.appendChild(title);
                item.appendChild(meta);
                item.addEventListener('click', function () {
                    input.value = product.barcode;
                    form.submit();
                });
                box.appendChild(item);
            });

            box.hidden = false;
        }

        input.addEventListener('input', function () {
            var query = this.value.trim();
            clearTimeout(timer);
            if (!query) {
                hide();
                return;
            }

            timer = setTimeout(function () {
                var cached = cache.get(query);
                if (cached) {
                    render(cached);
                    return;
                }
                fetch(endpoint + '?q=' + encodeURIComponent(query))
                    .then(function (response) { return response.json(); })
                    .then(function (data) {
                        cache.set(query, data.products);
                        render(data.products);
                    })
                    .catch(hide);
            }, delay);
        });

        input.addEventListener('blur', function () {
            setTimeout(hide, 150);
        });
    };
})();
