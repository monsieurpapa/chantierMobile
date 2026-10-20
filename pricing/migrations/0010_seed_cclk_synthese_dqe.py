"""Seeds the "Synthèse par étape" DQE of the Appartements CCLK chantier.

Source: the client's devis "DEVIS APPARTEMENTS CCLK 2.xlsx", sheet
"SYTNHESE PAR ETAPE" (Gros-Œuvre summary, 6 étapes A–F, 91 lines,
sheet total $51,899.83). Requested 2026-10-20 to be loaded in production.

What it does, on a database that has the production cabinet:
  1. Uses the "Appartements CCLK" chantier (or creates it in
     "Cabinet Principal", the cabinet bootstrap_admin_and_roles creates).
  2. Makes sure the chantier has one main étape per sheet étape
     (reusing an existing one with the same name, case-insensitive).
  3. Adds one Bibliothèque de Prix article per distinct designation
     (code CCLK-SYN-###): MATERIAL linked to the materials catalog when the
     material exists there, SERVICE for lump sums ("Fft").
  4. Creates DQE "DQE-CCLK-SYN-001" in Brouillon with every sheet line,
     each on its étape, with the sheet's own unit price.

Quantities are stored with 2 decimals (DQELine.quantity), so the DQE
total is $51,900.10 instead of the sheet's $51,899.83.

Safe everywhere:
  - Does nothing when neither the chantier nor "Cabinet Principal" exists
    (fresh CI/test databases).
  - Does nothing when the DQE already exists, so re-running never
    duplicates it.
  - Reversing removes the DQE and the CCLK-SYN articles no other DQE uses;
    the chantier and its étapes are kept (other data may point to them).
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations

CABINET_NAME = 'Cabinet Principal'
SITE_NAME = 'Appartements CCLK'
DQE_REFERENCE = 'DQE-CCLK-SYN-001'
DQE_TITLE = 'Synthèse par étape — Appartements CCLK'
CODE_PREFIX = 'CCLK-SYN-'
GROS_OEUVRE = 'GROS_OEUVRE'

# (sheet letter, chantier étape name, sheet heading, [(designation, unit, quantity, unit price)])
# Values copied from the sheet unchanged.
SYNTHESE = [
    ('A', 'Installation de chantier', 'INSTALLATION CHANTIER', [
        ('Brouettes de 50l', 'pce', '2', '45'),
        ('Démi-fût ( KINGUMBI)', 'pce', '4', '15'),
        ('Ficelle', 'pce', '6', '2.5'),
        ('Niveau à bulle', 'pce', '2', '5'),
        ('Niveau à eau', 'pce', '1', '25'),
        ('Marteau ménuserie', 'pce', '2', '5'),
        ('Marteau maçonnerie 2kg', 'pce', '2', '4'),
        ('Bêche', 'pce', '4', '4'),
        ('Pioche', 'pce', '2', '6'),
        ('Barre de mine', 'pce', '1', '10'),
        ('Burin', 'pce', '2', '3'),
        ('Scie à bois', 'pce', '1', '5'),
        ('Equeurre', 'pce', '2', '4'),
        ('Decametre 50m', 'pce', '1', '10'),
        ('Monture pour scie à métaux', 'pce', '2', '3'),
        ('Lame de scie à métaux', 'boîte', '2', '15'),
        ('Chevrons pour implantation', 'pce', '20', '2'),
        ('Sticks de bois pour implantation', 'pce', '10', '5'),
        ('Chaux pour implantation', 'pce', '3', '4'),
        ('Clous ordinaires', 'kg', '10', '2'),
        ('Clous de tôles', 'kg', '3', '2.5'),
        ('Tube 40x40', 'pce', '2', '11'),
        ('Transport', 'forfait', '1', '20'),
    ]),
    ('B', 'Travaux de fondation', 'FONDATION', [
        ('Remblais', 'm3', '152', '5'),
        ('Ciment', 'pce', '180.09550000000002', '12'),
        ('Moellon', 'm3', '50.31249999999999', '17'),
        ('Gravier', 'm3', '15.3552', '30'),
        ('Sable', 'm3', '23.683899999999998', '25'),
        ('Barres de 8', 'pce', '52.5', '4.5'),
        ('Barres de 12', 'pce', '73', '8'),
        ('Planches de coffrage', 'pce', '77.25', '5'),
        ('Clous ordinaire', 'kg', '31.375999999999998', '2'),
        ('Fil de recuit', 'kg', '24.016', '2.5'),
        ('Plomberie', 'forfait', '1', '225'),
    ]),
    ('C', 'Rez-de-chaussée', 'REZ DE CHAUSSEE', [
        ('Ciment', 'pce', '303.49199999999996', '12'),
        ('Bloc creux de 15cm', 'pce', '3149.9999999999995', '0.6'),
        ('Gravier', 'm3', '28.6368', '30'),
        ('Sable', 'm3', '28.579649999999997', '25'),
        ('Barres de 8', 'pce', '161.22909090909093', '4.5'),
        ('Barres de 10', 'pce', '238.5', '6'),
        ('Barres de 12', 'pce', '106.4', '8'),
        ('Barres de 14', 'pce', '23', '10'),
        ('Barres de 16', 'pce', '36', '12'),
        ('Multiplex de coffrage', 'pce', '151.70833333333334', '17'),
        ('Madrier', 'pce', '10', '7'),
        ('Sticks de bois', 'pce', '223.22916666666669', '5'),
        ('Chevrons', 'pce', '110.41666666666667', '2'),
        ('Clous ordinaire', 'kg', '158.184', '2'),
        ('Fil de recuit', 'kg', '89.49000000000001', '2'),
        ('Ajustage Rez-de-Chaussée', 'forfait', '1', '1166.5'),
        ('Plomberie DALLE 1', 'forfait', '1', '265'),
        ('Electricien DALLE 1', 'forfait', '1', '754'),
    ]),
    ('D', 'Etage 1', 'ETAGE 1', [
        ('Ciment', 'pce', '307.587', '12'),
        ('Bloc creux de 15cm', 'pce', '3299.9999999999995', '0.6'),
        ('Gravier', 'm3', '28.8168', '30'),
        ('Sable', 'm3', '29.220899999999997', '25'),
        ('Barres de 8', 'pce', '165.52', '4.5'),
        ('Barres de 10', 'pce', '238.5', '6'),
        ('Barres de 12', 'pce', '202.4', '8'),
        ('Multiplex de coffrage', 'pce', '20', '17'),
        ('Sticks de bois', 'pce', '45', '5'),
        ('Chevrons', 'pce', '20', '2'),
        ('Clous ordinaire', 'kg', '159.084', '2'),
        ('Fil de recuit', 'kg', '90.0525', '2'),
        ('Ajustage Etage 1', 'forfait', '1', '1166.5'),
        ('Plomberie DALLE 2', 'forfait', '1', '265'),
        ('Electricien DALLE 2', 'forfait', '1', '754'),
    ]),
    ('E', 'Etage 2', 'ETAGE 2', [
        ('Ciment', 'pce', '157.976', '12'),
        ('Bloc creux de 15cm', 'pce', '3000', '0.6'),
        ('Gravier', 'm3', '12.2944', '30'),
        ('Sable', 'm3', '17.834200000000003', '25'),
        ('Barres de 8', 'pce', '132.21818181818182', '4.5'),
        ('Barres de 10', 'pce', '79.5', '6'),
        ('Barres de 12', 'pce', '124.2', '8'),
        ('Multiplex de coffrage', 'pce', '15', '17'),
        ('Sticks de bois', 'pce', '20', '5'),
        ('Chevrons', 'pce', '10', '2'),
        ('Clous ordinaire', 'kg', '76.472', '2'),
        ('Fil de recuit', 'kg', '38.42', '2'),
        ('Ajustage Etage 2', 'forfait', '1', '1174'),
        ('Plomberie', 'forfait', '1', '200'),
        ('Electricien', 'forfait', '1', '100'),
    ]),
    ('F', 'Couverture', 'COUVERTURE', [
        ('Ajustage Etage 1', 'forfait', '1', '2935'),
        ('Ciment', 'pce', '37.226', '12'),
        ('Bloc creux de 15cm', 'pce', '1050', '0.6'),
        ('Gravier', 'm3', '2.5264', '30'),
        ('Sable', 'm3', '4.5706999999999995', '25'),
        ('Barres de 6', 'pce', '32.5', '3.5'),
        ('Barres de 10', 'pce', '32.5', '6'),
        ('Clous ordinaire', 'kg', '25.386', '2'),
        ('Fil de recuit', 'kg', '7.895', '2'),
    ]),
]

# Sheet designation (lower-case) -> materials catalog name (materials 0013).
MATERIAL_NAMES = {
    'brouettes de 50l': 'Brouette 50L',
    'démi-fût ( kingumbi)': 'Demi-fût (Kingumbi)',
    'ficelle': 'Ficelle',
    'niveau à bulle': 'Niveau à bulle',
    'niveau à eau': 'Niveau à eau',
    'marteau ménuserie': 'Marteau menuiserie',
    'marteau maçonnerie 2kg': 'Marteau maçonnerie 2kg',
    'bêche': 'Bêche',
    'pioche': 'Pioche',
    'barre de mine': 'Barre de mine',
    'burin': 'Burin',
    'scie à bois': 'Scie à bois',
    'equeurre': 'Equerre',
    'decametre 50m': 'Décamètre 50m',
    'monture pour scie à métaux': 'Monture pour scie à métaux',
    'lame de scie à métaux': 'Lame de scie à métaux',
    'chevrons pour implantation': 'Chevron',
    'sticks de bois pour implantation': 'Stick de bois',
    'chaux pour implantation': 'Chaux (implantation)',
    'clous ordinaires': 'Clous ordinaire',
    'clous ordinaire': 'Clous ordinaire',
    'tube 40x40': 'Tube 40x40',
    'remblais': 'Remblais',
    'ciment': 'Ciment',
    'moellon': 'Moellons',
    'gravier': 'Gravier',
    'sable': 'Sable',
    'barres de 6': 'Ferrons ϕ6',
    'barres de 8': 'Ferrons ϕ8',
    'barres de 10': 'Ferrons ϕ10',
    'barres de 12': 'Ferrons ϕ12',
    'barres de 14': 'Ferrons ϕ14',
    'planches de coffrage': 'Planches de coffrage',
    'fil de recuit': 'Fil de recuit',
    'bloc creux de 15cm': 'Bloc creux (15cm)',
    'multiplex de coffrage': 'Multiplex de coffrage',
    'madrier': 'Madrier',
    'sticks de bois': 'Stick de bois',
    'chevrons': 'Chevron',
}


def _q2(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _find_site(apps):
    Cabinet = apps.get_model('accounts', 'Cabinet')
    Site = apps.get_model('projects', 'Site')
    sites = Site.objects.filter(name__iexact=SITE_NAME, is_deleted=False)
    cabinet = Cabinet.objects.filter(name=CABINET_NAME, is_deleted=False).order_by('pk').first()
    if cabinet is not None and sites.filter(cabinet=cabinet).exists():
        return sites.filter(cabinet=cabinet).order_by('pk').first()
    if sites.count() == 1:
        return sites.first()
    if cabinet is None:
        return None
    return Site.objects.create(
        cabinet=cabinet, name=SITE_NAME,
        location='CCLK, Q. Kyeshero, Commune de Goma, Goma-NK',
        contract_mode='CLE_EN_MAIN', structure_type='POTEAUX_POUTRES',
        floor_count=2, basement_count=0, footprint_area_m2=Decimal('152.00'),
    )


def seed_dqe(apps, schema_editor):
    ProjectPhase = apps.get_model('projects', 'ProjectPhase')
    Material = apps.get_model('materials', 'Material')
    PriceLibraryItem = apps.get_model('pricing', 'PriceLibraryItem')
    DQE = apps.get_model('pricing', 'DQE')
    DQELine = apps.get_model('pricing', 'DQELine')

    site = _find_site(apps)
    if site is None:
        print('\n  [pricing 0010] No "%s" chantier or "%s" cabinet here — skipped.' % (SITE_NAME, CABINET_NAME))
        return
    cabinet = site.cabinet
    if DQE.objects.filter(cabinet=cabinet, reference=DQE_REFERENCE).exists():
        print('\n  [pricing 0010] %s already exists — skipped.' % DQE_REFERENCE)
        return

    dqe = DQE.objects.create(
        cabinet=cabinet, site=site, reference=DQE_REFERENCE, title=DQE_TITLE, status='DRAFT',
        notes=("Importé du devis du client « DEVIS APPARTEMENTS CCLK 2.xlsx », feuille "
               "« SYTNHESE PAR ETAPE » (Gros-Œuvre). Quantités arrondies à 2 décimales."),
    )

    items = {}
    code_n = 0
    order = 0
    for _letter, etape_name, _heading, lines in SYNTHESE:
        phase = ProjectPhase.objects.filter(
            site=site, parent_phase__isnull=True, name__iexact=etape_name, is_deleted=False,
        ).order_by('pk').first()
        if phase is None:
            phase = ProjectPhase.objects.create(site=site, name=etape_name, category=GROS_OEUVRE)
        for designation, unit, quantity, unit_price in lines:
            key = designation.lower()
            item = items.get(key)
            if item is None:
                item = PriceLibraryItem.objects.filter(
                    cabinet=cabinet, code__startswith=CODE_PREFIX, designation__iexact=designation, is_deleted=False,
                ).order_by('pk').first()
            if item is None:
                code_n += 1
                # Next code not already taken (soft-deleted rows included —
                # (cabinet, code) is unique across them too).
                while PriceLibraryItem.objects.filter(cabinet=cabinet, code='%s%03d' % (CODE_PREFIX, code_n)).exists():
                    code_n += 1
                material = None
                if key in MATERIAL_NAMES:
                    material = Material.objects.filter(name=MATERIAL_NAMES[key], is_deleted=False).order_by('pk').first()
                item = PriceLibraryItem.objects.create(
                    cabinet=cabinet, code='%s%03d' % (CODE_PREFIX, code_n), designation=designation,
                    item_type='SERVICE' if unit == 'forfait' else 'MATERIAL',
                    material=material, unit=unit, unit_price=_q2(unit_price),
                    notes='Devis APPARTEMENTS CCLK — synthèse par étape.',
                )
            items[key] = item
            DQELine.objects.create(
                dqe=dqe, price_item=item, phase=phase,
                quantity=_q2(quantity), unit_price=_q2(unit_price), order=order,
            )
            order += 1
    print('\n  [pricing 0010] Created %s on "%s" (%d lines).' % (DQE_REFERENCE, site.name, order))


def unseed_dqe(apps, schema_editor):
    PriceLibraryItem = apps.get_model('pricing', 'PriceLibraryItem')
    DQE = apps.get_model('pricing', 'DQE')
    DQELine = apps.get_model('pricing', 'DQELine')
    for dqe in DQE.objects.filter(reference=DQE_REFERENCE):
        DQELine.objects.filter(dqe=dqe).delete()
        dqe.delete()
    PriceLibraryItem.objects.filter(code__startswith=CODE_PREFIX, dqe_lines__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_cabinet_rebar_density_kg_per_m3'),
        ('materials', '0013_seed_cclk_materials'),
        ('projects', '0012_seed_phase_templates'),
        ('pricing', '0009_dqe_approval_workflow'),
    ]

    operations = [
        migrations.RunPython(seed_dqe, unseed_dqe),
    ]
