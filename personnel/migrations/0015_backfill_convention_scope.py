"""Backfills `scope` on existing SiteAssignment rows created through the
convention path (name non-empty) — see 0014_siteassignment_convention_scope
and ConventionScope's own docstring. Inferred from whether a phase was
already set: PAR_ETAPE if so, CHANTIER_ENTIER otherwise (a convention
created before `scope` existed had no explicit way to say "whole
chantier", so a convention without a phase is the closest honest
inference). Plain affectations (name blank) are left with scope=''
(blank) — scope is a convention-specific concept, not meaningful there.
"""
from django.db import migrations


def backfill_scope(apps, schema_editor):
    SiteAssignment = apps.get_model('personnel', 'SiteAssignment')
    SiteAssignment.objects.filter(name__gt='', phase__isnull=False, scope='').update(scope='PAR_ETAPE')
    SiteAssignment.objects.filter(name__gt='', phase__isnull=True, scope='').update(scope='CHANTIER_ENTIER')


def noop_reverse(apps, schema_editor):
    """Not reversible in a meaningful way (we can't tell a backfilled
    scope from one the user picked afterward) — left as a no-op so
    reversing this migration doesn't destroy data."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("personnel", "0014_siteassignment_convention_scope"),
    ]

    operations = [
        migrations.RunPython(backfill_scope, noop_reverse),
    ]
