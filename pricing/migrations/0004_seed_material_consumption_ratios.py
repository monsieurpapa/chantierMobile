"""Seed global-default MaterialConsumptionRatio rows (cabinet=None) so a
fresh cabinet's WORK_ITEM price-library items (e.g. "Béton dosé 350 —
fondations") can be exploded into elementary material quantities for the
Devis/État de besoin comparison feature out of the box, without first
requiring every cabinet to build its own ratio catalog from scratch.

Ratios reflect standard BTP (French construction practice) rules of thumb:

- Béton dosé à 350 kg/m³ (commonly used for most structural concrete,
  foundations/poteaux/poutres/dalles): ~7 sacs de ciment (50 kg) per m³,
  ~0.4 m³ de sable per m³, ~0.8 m³ de gravier per m³.
- Ferraillage (armatures): quantities are typically already estimated and
  priced directly in kg of acier, so the "explosion" ratio is simply 1:1 —
  this lets a WORK_ITEM-typed "Ferraillage" line (if a cabinet prices it
  that way instead of as a direct MATERIAL line) still feed the same
  comparison engine as a direct acier line.
- Coffrage: ~0.02 m³ de bois de coffrage per m² coffré (reusable plank
  formwork, rough order-of-magnitude default).
- Maçonnerie (parpaings 20x20x40, pose with mortar joints): ~12.5 unités
  per m² of wall, ~0.5 sac de ciment per m² (mortar), ~0.03 m³ de sable
  per m².

These are deliberately conservative, commonly-cited defaults meant as a
starting point — a cabinet can override any of them with its own
cabinet-specific row (same work_category + material, with its own
`cabinet` set) per MaterialConsumptionRatio.exploded_requirements()'s
override-preference rule.
"""
from django.db import migrations


# (material name, unit) -> created once, reused across ratios
MATERIALS = {
    'ciment': ('Ciment (sac 50kg)', 'sac'),
    'sable': ('Sable', 'm3'),
    'gravier': ('Gravier', 'm3'),
    'acier': ('Acier / armatures', 'kg'),
    'bois_coffrage': ('Bois de coffrage', 'm3'),
    'parpaings': ('Parpaings (20x20x40)', 'unité'),
}

# (work_category, material_key, ratio, ratio_unit)
RATIOS = [
    ('BETON', 'ciment', '7.0000', 'sacs/m3'),
    ('BETON', 'sable', '0.4000', 'm3/m3'),
    ('BETON', 'gravier', '0.8000', 'm3/m3'),
    ('ACIER', 'acier', '1.0000', 'kg/kg'),
    ('COFFRAGE', 'bois_coffrage', '0.0200', 'm3/m2'),
    ('MACONNERIE', 'parpaings', '12.5000', 'unités/m2'),
    ('MACONNERIE', 'ciment', '0.5000', 'sacs/m2'),
    ('MACONNERIE', 'sable', '0.0300', 'm3/m2'),
]


def seed_ratios(apps, schema_editor):
    Material = apps.get_model('materials', 'Material')
    MaterialConsumptionRatio = apps.get_model('pricing', 'MaterialConsumptionRatio')

    material_ids = {}
    for key, (name, unit) in MATERIALS.items():
        obj, _created = Material.objects.get_or_create(name=name, defaults={'unit': unit})
        material_ids[key] = obj.id

    for work_category, material_key, ratio, ratio_unit in RATIOS:
        MaterialConsumptionRatio.objects.get_or_create(
            cabinet=None,
            work_category=work_category,
            material_id=material_ids[material_key],
            defaults={'ratio': ratio, 'ratio_unit': ratio_unit},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0003_dqeline_phase_pricelibraryitem_material_and_more"),
        ("materials", "0009_materialrequestitem_phase"),
    ]

    operations = [
        migrations.RunPython(seed_ratios, migrations.RunPython.noop),
    ]
