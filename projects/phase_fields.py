"""Étape (ProjectPhase) select that also offers the Catalogue des étapes.

Every "Étape" select in the app is a ForeignKey to ProjectPhase, which is
always tied to one chantier (Site). The Catalogue des étapes
(PhaseTemplate) is not tied to any chantier, so until now a catalog étape
could only be picked after someone had imported it onto the chantier from
the catalogue page.

CatalogPhaseChoiceField fixes that without touching any model: it lists the
chantier's own étapes first, then a "Catalogue des étapes" group with every
catalog étape/sous-étape the chantier does not have yet. A catalog option's
value is ``catalogue:<site pk>:<template pk>``.

Picking a catalog option creates the real ProjectPhase on that chantier,
but only once the whole form is valid (see PhaseCatalogFormMixin): an
invalid submission never leaves a stray étape behind. Until then the field
holds an unsaved ProjectPhase so form/model clean() methods can still read
its site, name and parent.
"""
from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import ModelChoiceIterator
from django.utils.translation import gettext_lazy as _

CATALOG_PREFIX = 'catalogue'


def catalog_value(site_pk, template_pk):
    return f'{CATALOG_PREFIX}:{site_pk}:{template_pk}'


def is_catalog_value(value):
    return isinstance(value, str) and value.startswith(CATALOG_PREFIX + ':')


def _key(parent_name, name):
    parent = (parent_name or '').strip().lower() or None
    return parent, (name or '').strip().lower()


def _category_rank(category):
    from chantiermobile.constants import PhaseCategory
    values = list(PhaseCategory.values)
    return values.index(category) if category in values else len(values)


def catalog_entries_for_site(site, top_level_only=False):
    """Catalog étapes the chantier does not have yet, in catalogue order
    (category, then order, each étape followed by its sous-étapes).

    Returns a list of ``(template, label)``. An étape counts as already on
    the chantier when a ProjectPhase with the same name (case-insensitive)
    exists under the same parent name. When a cabinet's own template and a
    global one share a name, the cabinet's own wins."""
    from .models import PhaseTemplate, ProjectPhase
    if site is None:
        return []
    templates = list(PhaseTemplate.catalog_for_cabinet(site.cabinet))
    existing = {
        _key(parent_name, name)
        for parent_name, name in ProjectPhase.objects.filter(site=site).values_list('parent_phase__name', 'name')
    }

    tops = {}
    subs = {}
    for t in templates:
        if t.parent_template_id:
            bucket = subs.setdefault(_key(None, t.parent_template.name), {})
            k = _key(t.parent_template.name, t.name)
        else:
            bucket = tops
            k = _key(None, t.name)
        if k not in bucket or t.cabinet_id:
            bucket[k] = t

    entries = []
    for top in sorted(tops.values(), key=lambda t: (_category_rank(t.category), t.order, t.name.lower())):
        top_key = _key(None, top.name)
        if top_key not in existing:
            entries.append((top, top.name))
        if top_level_only:
            continue
        for sub in sorted(subs.get(top_key, {}).values(), key=lambda t: (t.order, t.name.lower())):
            if _key(top.name, sub.name) not in existing:
                entries.append((sub, f'{top.name} › {sub.name}'))
    return entries


def pending_phase_from_template(site, template):
    """The ProjectPhase `template` stands for on `site`: the existing row
    if the chantier already has it, otherwise an unsaved instance (its
    parent may be unsaved too) marked for creation by
    persist_catalog_phase()."""
    from .models import ProjectPhase
    parent = None
    if template.parent_template_id:
        parent_tpl = template.parent_template
        parent = ProjectPhase.objects.filter(
            site=site, parent_phase__isnull=True, name__iexact=parent_tpl.name,
        ).first()
        if parent is None:
            parent = ProjectPhase(site=site, name=parent_tpl.name, category=parent_tpl.category)
            parent._catalog_pending = True
    if parent is None or parent.pk:
        existing = ProjectPhase.objects.filter(
            site=site, parent_phase=parent, name__iexact=template.name,
        ).first()
        if existing is not None:
            return existing
    phase = ProjectPhase(site=site, name=template.name, category=template.category, parent_phase=parent)
    phase._catalog_pending = True
    return phase


def persist_catalog_phase(phase):
    """Saves a pending catalog phase (and its pending parent). Idempotent:
    reuses a same-named étape created in the meantime instead of
    duplicating it. Any other value is returned unchanged."""
    from .models import ProjectPhase
    if phase is None or not getattr(phase, '_catalog_pending', False) or phase.pk:
        return phase
    parent = phase.parent_phase
    if parent is not None and not parent.pk:
        parent = persist_catalog_phase(parent)
    saved, _created = ProjectPhase.objects.get_or_create(
        site=phase.site, parent_phase=parent, name__iexact=phase.name,
        defaults={'name': phase.name, 'category': phase.category},
    )
    return saved


class _PhaseChoiceIterator(ModelChoiceIterator):
    """The chantier's own étapes, then one catalog group per chantier.
    With no catalog entries to show, renders exactly like a plain
    ModelChoiceField (flat list, same labels)."""

    def __iter__(self):
        field = self.field
        if field.empty_label is not None:
            yield ('', field.empty_label)
        own = [self.choice(obj) for obj in self.queryset]
        groups = field.catalog_groups()
        if not groups:
            yield from own
            return
        if own:
            yield (_("Étapes du chantier"), own)
        yield from groups

    def __len__(self):
        return sum(1 for _ in self)

    def __bool__(self):
        return True


class CatalogPhaseChoiceField(forms.ModelChoiceField):
    """A ProjectPhase select that also offers catalog étapes for the
    chantiers in `catalog_sites`. `top_level_only` limits the catalog part
    to main étapes (used for "Étape parente")."""
    iterator = _PhaseChoiceIterator

    def __init__(self, *args, catalog_sites=(), top_level_only=False, **kwargs):
        self.top_level_only = top_level_only
        self._catalog_sites = [s for s in catalog_sites if s is not None]
        self._catalog_cache = None
        super().__init__(*args, **kwargs)

    def __deepcopy__(self, memo):
        result = super().__deepcopy__(memo)
        result._catalog_sites = list(self._catalog_sites)
        result._catalog_cache = None
        return result

    @property
    def catalog_sites(self):
        return self._catalog_sites

    @catalog_sites.setter
    def catalog_sites(self, sites):
        self._catalog_sites = [s for s in sites if s is not None]
        self._catalog_cache = None
        self.widget.choices = self.choices

    def catalog_groups(self):
        if self._catalog_cache is None:
            groups = []
            many = len(self._catalog_sites) > 1
            for site in self._catalog_sites:
                entries = catalog_entries_for_site(site, top_level_only=self.top_level_only)
                if not entries:
                    continue
                if many:
                    label = _("Catalogue des étapes — %(site)s") % {'site': site.name}
                else:
                    label = _("Catalogue des étapes")
                groups.append((label, [(catalog_value(site.pk, t.pk), text) for t, text in entries]))
            self._catalog_cache = groups
        return self._catalog_cache

    def to_python(self, value):
        if is_catalog_value(value):
            return self._from_catalog(value)
        return super().to_python(value)

    def _from_catalog(self, value):
        from .models import PhaseTemplate
        invalid = ValidationError(
            self.error_messages['invalid_choice'], code='invalid_choice', params={'value': value},
        )
        try:
            _prefix, site_pk, template_pk = value.split(':')
            site_pk, template_pk = int(site_pk), int(template_pk)
        except ValueError:
            raise invalid
        site = next((s for s in self._catalog_sites if s.pk == site_pk), None)
        if site is None:
            raise invalid
        template = PhaseTemplate.catalog_for_cabinet(site.cabinet).filter(pk=template_pk).first()
        if template is None or (self.top_level_only and template.parent_template_id):
            raise invalid
        return pending_phase_from_template(site, template)


class PhaseCatalogFormMixin:
    """Creates the étapes picked from the catalog once the form is
    otherwise valid — before the model instance is built and validated, so
    its own clean() (e.g. "the étape must belong to the same chantier")
    runs against the real saved étape."""

    def _post_clean(self):
        if not self._errors:
            for name, value in list(self.cleaned_data.items()):
                if getattr(value, '_catalog_pending', False):
                    self.cleaned_data[name] = persist_catalog_phase(value)
        super()._post_clean()

    def _get_validation_exclusions(self):
        # When another field is invalid, a catalog étape stays unsaved, so
        # the model would wrongly report it as empty; skip it — the user
        # only needs to see the real error.
        exclude = set(super()._get_validation_exclusions())
        exclude.update(
            name for name, value in getattr(self, 'cleaned_data', {}).items()
            if getattr(value, '_catalog_pending', False) and not getattr(value, 'pk', None)
        )
        return exclude


def enable_phase_catalog(form, field_name='phase', sites=(), top_level_only=False):
    """Swaps `form.fields[field_name]` (a ProjectPhase ModelChoiceField)
    for a CatalogPhaseChoiceField with the same queryset, label, widget
    and required flag, offering the catalog for `sites`. Call it after the
    form has set the field's queryset. The form class must also include
    PhaseCatalogFormMixin. Returns the new field (or None if the form has
    no such field)."""
    old = form.fields.get(field_name)
    if old is None:
        return None
    if isinstance(old, CatalogPhaseChoiceField):
        old.catalog_sites = sites
        return old
    new = CatalogPhaseChoiceField(
        queryset=old.queryset,
        required=old.required,
        label=old.label,
        help_text=old.help_text,
        widget=old.widget,
        initial=old.initial,
        empty_label=old.empty_label,
        disabled=old.disabled,
        catalog_sites=sites,
        top_level_only=top_level_only,
    )
    form.fields[field_name] = new
    return new


def site_phase_options(site):
    """JSON-ready options for one chantier's étape select: its own étapes
    (``{'id', 'text'}``) followed by the catalog étapes it does not have
    yet (``{'id': 'catalogue:…', 'text', 'group'}``). Shared by the
    finance:site_phases_data endpoint and the personnel form."""
    from .models import ProjectPhase
    results = [
        {'id': p.pk, 'text': p.name}
        for p in ProjectPhase.objects.filter(site=site).order_by('start_date')
    ]
    group = str(_("Catalogue des étapes"))
    results += [
        {'id': catalog_value(site.pk, t.pk), 'text': text, 'group': group}
        for t, text in catalog_entries_for_site(site)
    ]
    return results
