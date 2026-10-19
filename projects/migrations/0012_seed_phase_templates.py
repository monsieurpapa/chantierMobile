"""Seed global-default PhaseTemplate rows (cabinet=None) so a fresh
cabinet gets a ready-to-use "liste des étapes possibles" out of the box
instead of starting from an empty catalog — mirroring how
pricing.migrations.0004_seed_material_consumption_ratios seeds global
MaterialConsumptionRatio defaults.

The structure (major étapes + their sous-étapes, Gros-Œuvre and Second-
Œuvre) is taken from a real devis quantitatif et estimatif ("Appartements
CCLK") shared by the client while exploring this feature — it reflects
how a typical multi-storey reinforced-concrete building (fondation →
rez-de-chaussée → étages → couverture, then plomberie/électricité/
finitions) is actually broken down into étapes/sous-étapes in this
cabinet's own practice, rather than an invented or generic taxonomy.

Second-Œuvre majors that the source devis left for a separate trade
quote ("Cfr Devis ...") or simply hadn't itemized yet (Huisserie
métallique, Étanchéité, Faux-plafond, Carrelage, Peinture, Vitrerie) are
still seeded as top-level templates with no sous-étapes — a cabinet can
flesh those out with its own sous-modèles later."""
from django.db import migrations


# (name, [sub-étape names...]) — Gros-Œuvre
GROS_OEUVRE = [
    ('Travaux de fondation', [
        'Fondation',
        'Béton de propreté',
        'Semelle en BA',
        'Socle en BA',
        'Maçonnerie de fondation en moellons',
        'Longrine en BA',
        'Béton de sous-pavement',
    ]),
    ('Rez-de-chaussée', [
        'Elévation',
        'Colonnes en BA',
        'Bande sismique',
        'Ajustage portes et fenêtres métalliques',
        'Poutres en BA',
        'Dalle et escalier',
    ]),
    ('Etage 1', [
        'Elévation',
        'Colonnes en BA',
        'Bande sismique',
        'Ajustage portes et fenêtres métalliques',
        'Poutres en BA',
        'Dalle et escalier',
    ]),
    ('Etage 2', [
        'Elévation',
        'Colonnes en BA',
        'Bande sismique',
        'Ajustage portes et fenêtres métalliques',
        'Poutres en BA',
        'Dalle et pergola',
    ]),
    ('Couverture', [
        'Charpente et tôlage',
        'Elévation',
        'Colonnes en BA',
        'Chaînage supérieur en BA',
    ]),
]

# (name, [sub-étape names...]) — Second-Œuvre (finissage)
SECOND_OEUVRE = [
    ('Plomberie', [
        'Descentes des évacuations',
        'Conduite fosse septique',
        'Alimentation en eau froide et chaude',
        'Raccordement en eau potable',
        'Appareillage',
    ]),
    ('Electricité', [
        'Prise de terre',
        'Tubages',
        'Câblage plafond Gyproc',
        'Appareillage',
        "Logette d'arrivée",
    ]),
    ('Huisserie en bois', [
        'Encadrements',
        'Portes et fenêtres',
        'Serrurerie',
    ]),
    ('Huisserie métallique (serrurerie)', []),
    ('Travaux de crépissage', [
        'Enduit mur extérieur et intérieur Rez-de-chaussée',
        'Enduit mur extérieur et intérieur Etage 1',
        'Enduit mur extérieur et intérieur Etage 2',
        'Enduit mur extérieur et intérieur Couverture et toiture',
        'Echafaudage',
    ]),
    ("Travaux d'étanchéité", []),
    ('Travaux de faux-plafond', []),
    ('Travaux de carrelage', []),
    ('Travaux de peinture', []),
    ('Travaux de vitrerie', []),
]


def seed_templates(apps, schema_editor):
    PhaseTemplate = apps.get_model('projects', 'PhaseTemplate')

    def create_group(items, category):
        for order, (name, subs) in enumerate(items):
            major, _created = PhaseTemplate.objects.get_or_create(
                cabinet=None, parent_template=None, name=name,
                defaults={'category': category, 'order': order},
            )
            for sub_order, sub_name in enumerate(subs):
                PhaseTemplate.objects.get_or_create(
                    cabinet=None, parent_template=major, name=sub_name,
                    defaults={'category': category, 'order': sub_order},
                )

    create_group(GROS_OEUVRE, 'GROS_OEUVRE')
    create_group(SECOND_OEUVRE, 'FINISSAGE')


def unseed_templates(apps, schema_editor):
    PhaseTemplate = apps.get_model('projects', 'PhaseTemplate')
    names = [name for name, _subs in GROS_OEUVRE + SECOND_OEUVRE]
    PhaseTemplate.objects.filter(cabinet__isnull=True, parent_template__isnull=True, name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0011_phasetemplate'),
    ]

    operations = [
        migrations.RunPython(seed_templates, unseed_templates),
    ]
