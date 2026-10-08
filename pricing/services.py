"""The Devis/État de besoin comparison engine: how much of a given
material was budgeted for a site+étape (via its accepted Devis's source
DQE) versus how much has actually been requested so far
(materials.MaterialRequestItem), and whether that's within, approaching,
or past the initial estimate.

This is deliberately kept separate from pricing/models.py: it reasons
across three apps (projects, pricing, revenue, materials) rather than
living on any one of their models, and it's the natural seam for the
comparison-badge JSON API and the authorize()-time soft-overage check to
both call into without duplicating the aggregation logic.
"""
from decimal import Decimal

from chantiermobile.constants import MaterialVarianceStatus, MaterialRequestStatus


def _phase_and_descendants(phase):
    """A top-level étape rolls up its sous-étapes' figures too (the
    brainstorm's "the étape itself, and its sub-étapes" requirement);
    a sous-étape only ever represents itself, since nesting is capped at
    one level (see ProjectPhase.clean())."""
    if phase is None:
        return []
    ids = [phase.pk]
    if not phase.is_sub_phase:
        ids.extend(phase.sub_phases.values_list('pk', flat=True))
    return ids


def baseline_quantity(site, phase, material):
    """The budgeted quantity of `material` for `phase` (and its
    sous-étapes, if `phase` is top-level), drawn from the site's accepted
    Devis's source_dqe — combining direct MATERIAL-type DQELines for that
    material with WORK_ITEM-type DQELines exploded through
    MaterialConsumptionRatio. Returns 0 (not None) when the site has no
    accepted Devis, no source_dqe, or no matching lines — "nothing
    budgeted" is a fact worth reporting (see MaterialVarianceStatus.
    NOT_BUDGETED), not an error."""
    from chantiermobile.constants import DevisStatus

    devis = site.devis_set.filter(status=DevisStatus.ACCEPTE, source_dqe__isnull=False).first()
    if not devis or not devis.source_dqe_id:
        return Decimal('0')

    phase_ids = _phase_and_descendants(phase)
    if not phase_ids:
        return Decimal('0')

    total = Decimal('0')
    lines = devis.source_dqe.lines.filter(phase_id__in=phase_ids).select_related('price_item')
    for line in lines:
        exploded = line.exploded_requirements()
        total += exploded.get(material.pk, Decimal('0'))
    return total


def cumulative_requested_quantity(site, phase, material):
    """Sum of every non-REJECTED MaterialRequestItem.quantity requested so
    far for this (site, phase, material) — rolled up across sous-étapes
    the same way baseline_quantity() is, so a top-level étape's badge
    reflects everything requested under it. Free-text (hors-catalogue)
    items are never counted here, since they have no `material` FK to
    match against."""
    from django.db.models import Sum
    from materials.models import MaterialRequestItem

    phase_ids = _phase_and_descendants(phase)
    if not phase_ids:
        return Decimal('0')

    result = MaterialRequestItem.objects.filter(
        request__site=site,
        phase_id__in=phase_ids,
        material=material,
    ).exclude(
        request__status=MaterialRequestStatus.REJECTED,
    ).aggregate(total=Sum('quantity'))
    return result['total'] or Decimal('0')


def compare_material_usage(site, phase, material, exclude_request_item=None, additional_quantity=None):
    """The core red/orange/green comparison for one (site, étape, matériau).

    `exclude_request_item` lets a live form re-check "what would the badge
    be if this specific row's current quantity were replaced by
    `additional_quantity`" without double-counting the row being edited —
    used by the live comparison badge API. `additional_quantity` is added
    on top of the (possibly-excluding) cumulative total; pass it to
    preview a not-yet-saved quantity.

    Returns a dict: {baseline, cumulative_requested, variance_pct, status}
    — variance_pct is None when baseline is 0 (division is meaningless;
    NOT_BUDGETED already communicates that case)."""
    baseline = baseline_quantity(site, phase, material)

    requested = cumulative_requested_quantity(site, phase, material)
    if exclude_request_item is not None and exclude_request_item.material_id == material.pk:
        phase_ids = _phase_and_descendants(phase)
        if exclude_request_item.phase_id in phase_ids:
            requested -= (exclude_request_item.quantity or Decimal('0'))
    if additional_quantity is not None:
        requested += Decimal(additional_quantity)

    if requested < 0:
        requested = Decimal('0')

    if baseline <= 0:
        status = MaterialVarianceStatus.NOT_BUDGETED if requested > 0 else MaterialVarianceStatus.GREEN
        variance_pct = None
    else:
        variance_pct = (requested / baseline) * Decimal('100')
        cabinet = site.cabinet
        orange = cabinet.material_variance_orange_threshold_pct
        red = cabinet.material_variance_red_threshold_pct
        if variance_pct >= red:
            status = MaterialVarianceStatus.RED
        elif variance_pct >= orange:
            status = MaterialVarianceStatus.ORANGE
        else:
            status = MaterialVarianceStatus.GREEN

    return {
        'baseline': baseline,
        'cumulative_requested': requested,
        'variance_pct': variance_pct,
        'status': status,
    }


def material_request_variance_report(material_request):
    """One compare_material_usage() result per item on `material_request`
    that has both a `material` and a `phase` set (free-text items, or
    items with no phase assigned, can't be compared and are simply
    skipped) — the per-item breakdown used by the request detail page and
    by the soft-overage note check at authorize() time.

    Deliberately calls `.all()` with no further queryset method chained
    (no `.select_related()` here) — chaining one creates a brand-new
    QuerySet that bypasses Django's prefetch cache, so a caller that
    already did `prefetch_related('items__material', 'items__phase')`
    (e.g. MaterialRequestDetailView) would get back *different* item
    instances than the ones it iterates elsewhere (e.g. `req.items.all()`
    in the template). Annotating those throwaway instances with
    `.variance_comparison` would then silently have no visible effect —
    exactly the bug this comment is here to prevent reintroducing. Callers
    without a prefetch (e.g. authorize()'s has_red_variance() check) just
    take the small N+1 cost of lazily loading `material`/`phase` instead.

    Returns a list of {item, comparison} dicts, in the request's item
    order."""
    results = []
    for item in material_request.items.all():
        if not item.material_id or not item.phase_id:
            continue
        comparison = compare_material_usage(
            material_request.site, item.phase, item.material,
            exclude_request_item=None,
        )
        results.append({'item': item, 'comparison': comparison})
    return results


def structural_quantity_estimate(site):
    """Ouvrage-level quantities (in each work category's own natural unit,
    not yet exploded into elementary materials) implied by `site`'s
    floor/structure data (Site.floor_count/basement_count/
    footprint_area_m2 and each SiteLevel's dimensions — see
    projects.models.Site/SiteLevel, added 2026-10-08).

    This is advisory: a starting point for sizing a BETON/MACONNERIE DQE
    line for this site, surfaced on the DQE form (see pricing/views.py's
    site_structural_estimate_api and dqe_form.html) so a quantity surveyor
    can pre-fill a line's quantity and still pick the right price-library
    article/étape themselves — it never creates a DQELine on its own.

    Returns {'concrete_m3', 'wall_area_m2', 'rebar_kg'} — all Decimal,
    0 when the site has no levels yet (nothing to estimate), not an
    error."""
    return {
        'concrete_m3': site.total_concrete_volume_m3,
        'wall_area_m2': site.total_wall_area_m2,
        'rebar_kg': site.estimated_rebar_kg,
    }


def has_red_variance(material_request):
    """True if authorizing `material_request` as-is would leave at least
    one of its comparable items in RED — the trigger for authorize()'s
    mandatory justification-note requirement (mirrors
    PayrollListItem.clean()'s chef-de-corps soft-overage pattern)."""
    return any(
        r['comparison']['status'] == MaterialVarianceStatus.RED
        for r in material_request_variance_report(material_request)
    )
