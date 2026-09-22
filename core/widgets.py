import json

from django import forms
from django.urls import reverse_lazy


class DynamicSelectWidget(forms.Select):
    """
    A <select> enhanced client-side (static/js/dynamic-select.js) into a
    searchable "select or add new" picker: if the value someone wants isn't
    in the list yet, they can type it and an "Add «text»" option lets them
    create it on the spot and have it selected immediately.

    Use this for master-data choices that grow progressively as people use
    the app (a worker, a supplier, a material, ...) — a record with no
    fixed initial dataset. Do NOT use it for a fixed set of choices (a
    status, a role, a movement type) or a structural workflow FK (Site,
    ProjectPhase, Cabinet) — free-text creation makes no sense there.
    """

    def __init__(self, create_url_name=None, placeholder='', create_label=None,
                 depends_on=None, depends_param=None, create_extra=None, attrs=None, **kwargs):
        """
        create_url_name: url name (with namespace) of the quick-create POST
            endpoint, e.g. 'personnel:personnel_quick_create'.
        placeholder: hint shown before anything is picked / in the search box.
        create_label: "Add" label prefix shown before the typed text
            (defaults to French "Ajouter" client-side).
        depends_on / depends_param: for a field whose valid choices depend
            on another field ON THE SAME PAGE (e.g. personnel scoped to the
            chosen site) — the *id* of that other field's rendered input
            (e.g. 'id_site'), and the POST param name its value should be
            sent under when creating a new record (e.g. 'site'). Both must
            be given together for the dependency to take effect. Its value
            is read live at creation time, so it always reflects whatever
            is currently selected.
        create_extra: a dict of extra POST params to send every time,
            fixed at render time — for context that isn't a field on the
            page at all (e.g. a site passed into the form via __init__,
            not picked from a dropdown). Use depends_on/depends_param
            instead when the context IS a field on the page.
        """
        merged_attrs = {'class': 'form-select', 'data-control': 'select2'}
        if attrs:
            merged_attrs.update(attrs)
        if placeholder:
            merged_attrs.setdefault('data-placeholder', placeholder)
        if create_label:
            merged_attrs['data-create-label'] = create_label
        if create_url_name:
            merged_attrs['data-create-url'] = reverse_lazy(create_url_name)
        if depends_on and depends_param:
            merged_attrs['data-depends-on'] = depends_on
            merged_attrs['data-depends-param'] = depends_param
        if create_extra:
            merged_attrs['data-create-extra'] = json.dumps(create_extra)
        super().__init__(attrs=merged_attrs, **kwargs)


class DynamicSelectMultipleWidget(forms.SelectMultiple, DynamicSelectWidget):
    """Same as DynamicSelectWidget, for a ManyToMany field (e.g. skills)."""
    pass
