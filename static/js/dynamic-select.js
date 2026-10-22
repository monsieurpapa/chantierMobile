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
 *   data-tags="true"            (without data-create-url) lets a typed value
 *                                 be kept as-is — free text, nothing created
 *   data-placeholder="..."      placeholder / search hint text
 *   data-create-label="..."     "Add" label prefix (defaults to a French label)
 *   data-depends-on="id_site"   id of another field this one is scoped to;
 *                                 its current value is sent as an extra
 *                                 create-time param (see data-depends-param)
 *   data-depends-param="site"   POST param name for the above (default "site")
 *
 * After a quick-create the new option is also added to every other picker
 * backed by the same data-create-url, and the select fires a jQuery
 * 'dynamicselect:created' event whose `record` is the endpoint's JSON
 * ({id, text, ...extra fields}).
 *
 * Note: select2 fires jQuery 'change' events. Listen with $(el).on('change')
 * — a native addEventListener('change') does not see them.
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
            var newId = String(result.body.id);
            // The endpoint may hand back an existing record (e.g. a material
            // already in the catalogue): select it rather than duplicating it.
            if (!$el.find('option').filter(function () { return this.value === newId; }).length) {
                $el.append(new Option(result.body.text, newId, false, false));
            }
            // Other pickers backed by the same endpoint (the other rows of a
            // formset, say) get the new entry too, unselected.
            $('select[data-create-url]').not($el).filter(function () {
                return $(this).data('createUrl') === $el.data('createUrl') &&
                    !$(this).find('option').filter(function () { return this.value === newId; }).length;
            }).each(function () {
                $(this).append(new Option(result.body.text, newId, false, false));
            });
            $el.trigger($.Event('dynamicselect:created', { record: result.body }));

            if ($el.prop('multiple')) {
                var current = ($el.val() || []).filter(function (v) { return v !== tempId; });
                current.push(newId);
                $el.val(current);
            } else {
                $el.val(newId);
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

        // data-tags="true" without a create URL: free text kept as typed
        // (a value, not a record — e.g. a role on a chantier).
        var freeTags = !createUrl && ($el.data('tags') === true || $el.data('tags') === 'true');

        if (createUrl || freeTags) {
            options.tags = true;
            options.createTag = function (params) {
                var term = $.trim(params.term);
                if (!term) return null;
                if (optionExists($el, term)) return null;
                return { id: freeTags ? term : NEW_PREFIX + term, text: term, newTag: true };
            };
            // List "Ajouter « … »" after the matches, so typing "Ciment" then
            // Enter picks the existing "Ciment (sac)" instead of creating a
            // near-duplicate.
            options.insertTag = function (data, tag) { data.push(tag); };
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

    // ------------------------------------------------------------------
    // Étape pickers (2026-10-22): every "Étape" <select> in the app gets a
    // search box — chantiers have dozens of étapes and sous-étapes, plus
    // the Catalogue des étapes. Found by name (phase, parent_phase,
    // catalog_template, formset "-phase" fields) or data-etape, so no form
    // needs changing. Many pages rebuild these options in script (when the
    // chantier changes) or set their value in code, and some listen with
    // a plain addEventListener('change'): all of that keeps working.
    // ------------------------------------------------------------------
    var ETAPE_SELECTOR = [
        'select[name="phase"]', 'select[name$="-phase"]',
        'select[name="parent_phase"]', 'select[name$="-parent_phase"]',
        'select[name="catalog_template"]', 'select[data-etape]',
    ].join(',');

    function initEtape(el) {
        var $el = $(el);
        if (el.multiple || $el.data('select2') || el.getAttribute('data-control') === 'select2'
            || el.getAttribute('data-etape') === 'off') return;
        var first = el.options[0];
        $el.select2({
            theme: 'bootstrap-5',
            width: '100%',
            placeholder: el.getAttribute('data-placeholder') || 'Choisir une étape…',
            // A narrow column (état de besoin lines) must not squeeze the list.
            dropdownAutoWidth: true,
            allowClear: !el.required && !!first && first.value === '',
            language: {
                noResults: function () { return 'Aucune étape trouvée'; },
                searching: function () { return 'Recherche…'; },
            },
        });

        function refresh() { $el.trigger('change.select2'); }

        // Options rebuilt in script (innerHTML, appendChild…): show the new state.
        new MutationObserver(refresh).observe(el, { childList: true, subtree: true });

        // Value set in code (el.value = …, el.selectedIndex = …): same.
        var proto = window.HTMLSelectElement.prototype;
        ['value', 'selectedIndex'].forEach(function (prop) {
            var d = Object.getOwnPropertyDescriptor(proto, prop);
            Object.defineProperty(el, prop, {
                configurable: true,
                get: function () { return d.get.call(el); },
                set: function (v) { d.set.call(el, v); refresh(); },
            });
        });

        // select2 announces a pick as a jQuery event only; pass it on as a
        // real one for listeners added with addEventListener('change').
        $el.on('change.etapebridge', function (e) {
            if (!e.originalEvent && !e.etapeBridge) {
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }

    function initEtapes(scope) {
        if (!scope || !scope.querySelectorAll) return;
        if (scope.matches && scope.matches(ETAPE_SELECTOR)) initEtape(scope);
        Array.prototype.forEach.call(scope.querySelectorAll(ETAPE_SELECTOR), initEtape);
    }

    window.initDynamicSelects = function (root) {
        var scope = root || document;
        var nodes = scope.querySelectorAll ? scope.querySelectorAll('[data-control="select2"]') : [];
        Array.prototype.forEach.call(nodes, initOne);
        // If `scope` itself is such an element (e.g. called with a single freshly-created node).
        if (scope.matches && scope.matches('[data-control="select2"]')) initOne(scope);
        initEtapes(scope);
    };

    document.addEventListener('DOMContentLoaded', function () {
        window.initDynamicSelects(document);
        // Rows added later (formsets, "Ajouter une ligne"): their étape
        // pickers get the search box too.
        new MutationObserver(function (mutations) {
            mutations.forEach(function (m) {
                Array.prototype.forEach.call(m.addedNodes, function (node) {
                    if (node.nodeType === 1 && !(node.classList && node.classList.contains('select2-container'))) {
                        initEtapes(node);
                    }
                });
            });
        }).observe(document.body, { childList: true, subtree: true });
    });
})(window, document, window.jQuery);
