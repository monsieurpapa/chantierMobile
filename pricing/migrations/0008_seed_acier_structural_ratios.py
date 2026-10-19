"""Seed global-default MaterialConsumptionRatio rows for the four
differentiated ACIER structural sub-categories (see
0007_acier_structural_subcategories and WorkCategory's own docstring for
why a single ACIER ratio isn't good enough: semelles, poteaux, poutres
and dalles each reinforce at a very different kg-of-acier-per-m³-of-béton
density, and summing them under one category would double-count/blend
numbers that a lead engineer needs to read apart).

Ratios reflect standard BTP rules of thumb for ordinary residential/
light-commercial reinforced concrete (an avant-métré shortcut, same
spirit as 0004_seed_material_consumption_ratios's own BETON ratios — a
quantity surveyor is expected to refine per DQE line as needed):

- Semelles (strip/isolated footings): ~50 kg/m³ (usual range 40-60).
- Poteaux (columns): ~150 kg/m³ (usual range 125-200 — columns carry
  more reinforcement relative to their concrete volume than footings).
- Poutres (beams): ~200 kg/m³ (beams are typically the most
  reinforcement-dense structural element).
- Dalles (slabs): ~60 kg/m³ (derived from a common slab reinforcement
  rule of thumb — roughly 8 kg/m² treillis soudé + 4 kg/m² HA bars —
  divided by a 0.20 m slab thickness: (8 + 4) / 0.20 = 60 kg/m³).

Reuses the same 'Acier / armatures' Material row 0004 already created —
these are still acier, just priced per differentiated work category.
"""
from django.db import migrations


# (work_category, ratio) — material is always the existing 'acier' row.
RATIOS = [
    ('ACIER_SEMELLES', '50.0000'),
    ('ACIER_POTEAUX', '150.0000'),
    ('ACIER_POUTRES', '200.0000'),
    ('ACIER_DALLES', '60.0000'),
]


def seed_ratios(apps, schema_editor):
    Material = apps.get_model('materials', 'Material')
    MaterialConsumptionRatio = apps.get_model('pricing', 'MaterialConsumptionRatio')

    # Same name/unit 0004_seed_material_consumption_ratios already used
    # for the generic ACIER ratio — get_or_create reuses that exact row
    # rather than creating a duplicate acier Material.
    acier, _created = Material.objects.get_or_create(
        name='Acier / armatures', defaults={'unit': 'kg'},
    )

    for work_category, ratio in RATIOS:
        MaterialConsumptionRatio.objects.get_or_create(
            cabinet=None,
            work_category=work_category,
            material_id=acier.id,
            defaults={'ratio': ratio, 'ratio_unit': 'kg/m3'},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0007_acier_structural_subcategories"),
    ]

    operations = [
        migrations.RunPython(seed_ratios, migrations.RunPython.noop),
    ]
