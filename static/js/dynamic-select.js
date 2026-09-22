/**
 * Dynamic "select or add new" pickers.
 *
 * Any <select data-control="select2"> becomes a searchable picker. If it
 * also carries data-create-url, the person can type a value that doesn't
 * exist yet and an "Add «text»" option appears; picking it POSTs to that
 * URL, creates the record on the spot, and selects it — no page reload,
 * no separate "create X" screen to go fill in first.
 *
 * Used for "master data" that grows as people use the app (a worker, a
 * supplier, a material, ...) — never for fixed-choice fields (status,
 * role, ...), those stay plain selects with no data-create-url.
 *
 * Supported data-* attributes (set by core.widgets.DynamicSelectWidget):
 *   data-control="select2"      required to activate this widget at all
 *   data-create-url="/..."      POST endpoint that creates a new record
 *   data-placeholder="..."      placeholder / search hint text
 *   data-create-label="..."     "Add" label prefix (defaults to a French label)
 *   data-depends-on="id_site"   id of another field this one is scoped to;
 *                                 its current value is sent as an extra
 *                                 create-time param (see data-depends-param)
 *   data-depends-param="site"   POST param name for the above (default "site")
 *
 * Call window.initDynamicSelects(root) again after inserting new markup
 * into the page (e.g. a cloned formset row) so newly added selects inside
 * `root` get the same treatment. Safe to call repeatedly / on the whole
 * document — already-initialized selects are skipped.
 */
(function (window, document, $) {
    'use strict';

    if (!$ || !$.fn || !$.fn.select2) {
        // select2 not loaded on this page — nothing to enhance.
        window.initDynamicSelects = window.initDynamicSelects || function () {};
        return;
    }

    var NEW_PREFIX = '__new__:';

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        // Fallback: an embedded {% csrf_token %} hidden input, if any is on the page.
        var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return input ? input.value : '';
    }

    function showFieldError($el, message) {
        clearFieldError($el);
        var $container = $el.data('select2') ? $el.next('.select2-container') : $el;
        var $msg = $('<div class="text-danger fs--2 dynamic-select-error mt-1"></div>').text(message);
        $container.after($msg);
    }

    function clearFieldError($el) {
        var $container = $el.data('select2') ? $el.next('.select2-container') : $el;
        $container.next('.dynamic-select-error').remove();
    }

    function optionExists($el, term) {
        var lower = term.trim().toLowerCase();
        var found = false;
        $el.find('option').each(function () {
            if ($(this).text().trim().toLowerCase() === lower) {
                found = true;
                return false;
            }
        });
        return found;
    }

    function createInstance($el, term) {
        var createUrl = $el.data('createUrl');
        var payload = { name: term };

        var extra = $el.data('createExtra');
        if (extra && typeof extra === 'object') {
            $.extend(payload, extra);
        }

        var dependsOn = $el.data('dependsOn');
        if (dependsOn) {
            var $dep = $('#' + dependsOn);
            if ($dep.length) {
                var paramName = $el.data('dependsParam') || 'site';
                payload[paramName] = $dep.val();
            }
        }

        return fetch(createUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify(payload),
        }).then(function (response) {
            return response.json().then(function (body) {
                return { ok: response.ok, body: body };
            });
        });
    }

    function handleNewTag($el, data) {
        var term = data.text;
        var tempId = data.id;

        $el.prop('disabled', true);

        createInstance($el, term).then(function (result) {
            // Remove the temporary tag option select2 auto-inserted.
            $el.find('option').filter(function () { return this.value === tempId; }).remove();

            if (!result.ok) {
                var message = (result.body && result.body.error) || $el.data('createErrorMessage') ||
                    'Impossible de créer « ' + term + ' ». Réessayez.';
                showFieldError($el, message);
                $el.trigger('change');
                return;
            }

            clearFieldError($el);
            var newOption = new Option(result.body.text, result.body.id, true, true);
            $el.append(newOption);

            if ($el.prop('multiple')) {
                var current = ($el.val() || []).filter(function (v) { return v !== tempId; });
                current.push(String(result.body.id));
                $el.val(current);
            } else {
                $el.val(String(result.body.id));
            }
            $el.trigger('change');
        }).catch(function (err) {
            console.error('Quick-create failed:', err);
            $el.find('option').filter(function () { return this.value === tempId; }).remove();
            showFieldError($el, 'Impossible de créer « ' + term + ' ». Vérifiez votre connexion et réessayez.');
            $el.trigger('change');
        }).finally(function () {
            $el.prop('disabled', false);
        });
    }

    function initOne(el) {
        var $el = $(el);
        if ($el.data('select2')) return; // already initialized

        var createUrl = $el.data('createUrl');
        var placeholder = $el.data('placeholder') || '';
        var createLabel = $el.data('createLabel') || 'Ajouter';

        var options = {
            theme: 'bootstrap-5',
            width: '100%',
            language: {
                noResults: function () { return 'Aucun résultat'; },
                searching: function () { return 'Recherche…'; },
                inputTooShort: function () { return 'Continuez à taper pour rechercher…'; },
            },
            placeholder: placeholder || undefined,
            allowClear: !el.required,
        };

        if (createUrl) {
            options.tags = true;
            options.createTag = function (params) {
                var term = $.trim(params.term);
                if (!term) return null;
                if (optionExists($el, term)) return null;
                return { id: NEW_PREFIX + term, text: term, newTag: true };
            };
            options.templateResult = function (data) {
                if (data.loading) return data.text;
                if (data.newTag) {
                    var $span = $('<span class="text-primary"></span>');
                    $('<i class="fas fa-plus-circle me-1"></i>').appendTo($span);
                    $span.append(document.createTextNode(createLabel + ' « ' + data.text + ' »'));
                    return $span;
                }
                return data.text;
            };
        }

        $el.select2(options);

        if (createUrl) {
            $el.on('select2:select', function (e) {
                if (e.params && e.params.data && e.params.data.newTag) {
                    handleNewTag($el, e.params.data);
                }
            });
        }
    }

    window.initDynamicSelects = function (root) {
        var scope = root || document;
        var nodes = scope.querySelectorAll ? scope.querySelectorAll('[data-control="select2"]') : [];
        Array.prototype.forEach.call(nodes, initOne);
        // If `scope` itself is such an element (e.g. called with a single freshly-created node).
        if (scope.matches && scope.matches('[data-control="select2"]')) initOne(scope);
    };

    document.addEventListener('DOMContentLoaded', function () {
        window.initDynamicSelects(document);
    });
})(window, document, window.jQuery);
