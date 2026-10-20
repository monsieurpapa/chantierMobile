/*
 * Shared helpers for "Étape" <select>s filled from finance:site_phases_data.
 *
 * That endpoint returns the chantier's own étapes ({id, text}) followed by
 * the Catalogue des étapes entries the chantier doesn't have yet
 * ({id: "catalogue:<site>:<template>", text, group}). Catalog entries go in
 * their own <optgroup>; the étape is created on the chantier when the form
 * is saved.
 */
(function () {
    'use strict';

    // Appends `opt` to `select`, inside the <optgroup> labelled `group`
    // (created on first use) when a group is given.
    function place(select, opt, group) {
        if (!group) {
            select.appendChild(opt);
            return opt;
        }
        var target = null;
        var groups = select.querySelectorAll('optgroup');
        for (var i = 0; i < groups.length; i++) {
            if (groups[i].label === group) { target = groups[i]; break; }
        }
        if (!target) {
            target = document.createElement('optgroup');
            target.label = group;
            select.appendChild(target);
        }
        target.appendChild(opt);
        return opt;
    }

    // Replaces the options of `select` with `results`, keeping a blank
    // first option and re-selecting `preselectId` when present.
    function fill(select, results, preselectId, blankLabel) {
        select.innerHTML = '';
        var blank = document.createElement('option');
        blank.value = '';
        blank.textContent = blankLabel || '---------';
        select.appendChild(blank);
        (results || []).forEach(function (item) {
            var opt = document.createElement('option');
            opt.value = item.id;
            opt.textContent = item.text;
            if (preselectId && String(item.id) === String(preselectId)) opt.selected = true;
            place(select, opt, item.group);
        });
    }

    // Reloads `phaseSelect` from `url` whenever `siteSelect` changes
    // (and once on load when `loadNow` is true and a site is picked).
    function bind(siteSelect, phaseSelect, url, blankLabel, loadNow) {
        if (!siteSelect || !phaseSelect) return;
        function load(preselectId) {
            var siteId = siteSelect.value;
            if (!siteId) { fill(phaseSelect, [], null, blankLabel); return; }
            fetch(url + '?site=' + encodeURIComponent(siteId), {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(function (r) { return r.json(); })
            .then(function (data) { fill(phaseSelect, data.results, preselectId, blankLabel); })
            .catch(function (err) { console.error('Error loading étapes:', err); });
        }
        if (loadNow && siteSelect.value) load(phaseSelect.value);
        siteSelect.addEventListener('change', function () { load(null); });
    }

    window.ChantierPhases = { place: place, fill: fill, bind: bind };
})();
