# Generated manually on 2026-10-08

"""Data migration companion to 0011_alter_materialrequest_status.

The single-stage workflow change (2026-10-08) removed the intermediate
magasinier-validation step: a MaterialRequest now goes PENDING ->
APPROVED/REJECTED directly, with no UI action available for the retired
VALIDATED status (authorize() also now rejects it). Any request that was
sitting at VALIDATED before this change — i.e. already past the dropped
magasinier stage and awaiting a director's decision — is functionally
equivalent to a fresh PENDING request under the new workflow, so this
migration moves those rows forward rather than leaving them stuck with no
authorize/reject path and invisible to the pending-approvals inbox.
"""
from django.db import migrations


def migrate_validated_to_pending(apps, schema_editor):
    # Historical models only expose the plain (unfiltered) default manager
    # as `objects` unless a custom manager was declared with
    # `use_in_migrations = True` — which SoftDeleteModel's managers aren't —
    # so `.objects` here deliberately reaches every row, soft-deleted ones
    # included, rather than the app-level SoftDeleteManager-filtered one.
    MaterialRequest = apps.get_model('materials', 'MaterialRequest')
    MaterialRequest.objects.filter(status='VALIDATED').update(status='PENDING')


def noop_reverse(apps, schema_editor):
    # Not reversible: we can't tell which PENDING rows used to be VALIDATED.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0011_alter_materialrequest_status'),
    ]

    operations = [
        migrations.RunPython(migrate_validated_to_pending, noop_reverse),
    ]
