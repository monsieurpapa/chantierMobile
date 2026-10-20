"""Fills the letterhead of the ATGC Congo cabinet (production's cabinet)
from the client's own "DEVIS GLOBAL.xlsx" header, so its generated PDFs
carry its branding straight away. Only blank fields are filled, and only
on a cabinet named "ATGC Congo" — every other cabinet (and fresh CI/test
databases) is untouched. Each cabinet can edit these later in
Administration → Cabinets.

The logo (accounts/branding/atgc-congo-logo.png, extracted from the same
sheet) is stored through the default storage (Cloudflare R2 in
production); if that fails, the migration still succeeds and the logo can
be uploaded from the cabinet form.
"""
from pathlib import Path

from django.db import migrations

CABINET_NAME = 'ATGC Congo'
LETTERHEAD = {
    'legal_name': 'Assistance Technique en Génie Civil (ATGC congo.sarl)',
    'short_name': 'A.T.G.C.',
    'legal_mentions': "N° d'ag. 565/EC-D/08-19/KN\nRCCM : CD/KNG/RCCM/18-B-01479\nID. NAT. : 01-401-N38203Y",
    'phone': '(+243) 994166625, 852900881',
    'email': 'atgc.congo@gmail.com, placidebatu@gmail.com',
    'city': 'Goma',
}
LOGO = Path(__file__).resolve().parent.parent / 'branding' / 'atgc-congo-logo.png'


def seed(apps, schema_editor):
    Cabinet = apps.get_model('accounts', 'Cabinet')
    for cabinet in Cabinet.objects.filter(name__iexact=CABINET_NAME, is_deleted=False):
        changed = []
        for field, value in LETTERHEAD.items():
            if not getattr(cabinet, field):
                setattr(cabinet, field, value)
                changed.append(field)
        if changed:
            cabinet.save(update_fields=changed)
        if not cabinet.logo and LOGO.exists():
            try:
                from django.core.files import File
                with LOGO.open('rb') as fh:
                    cabinet.logo.save('atgc-congo-logo.png', File(fh), save=True)
            except Exception as exc:  # storage unreachable: keep going, upload later
                print('\n  [accounts 0013] Logo not stored (%s) — upload it from the cabinet form.' % exc)
        print('\n  [accounts 0013] Letterhead filled for "%s".' % cabinet.name)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_cabinet_letterhead'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
