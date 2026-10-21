"""Brave Bakulu joins as Chef des Ingénieurs (2026-10-21).

Creates the account (no usable password: a superadmin gives him a
temporary one with "Réinitialiser le mot de passe" on his user page, and
he must choose his own at first login) and an approved CHIEF_ENGINEER role
in the client's cabinet — "ATGC Congo", else the only cabinet when there
is exactly one. A no-op elsewhere (empty or multi-cabinet databases), and
safe to re-run: an existing account with this e-mail is reused.
"""
from django.contrib.auth.hashers import make_password
from django.db import migrations

EMAIL = 'bravebakuluirbtp@gmail.com'


def forwards(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    Cabinet = apps.get_model('accounts', 'Cabinet')
    UserCabinetRole = apps.get_model('accounts', 'UserCabinetRole')

    cabinet = Cabinet.objects.filter(name='ATGC Congo', is_deleted=False).first()
    if cabinet is None:
        cabinets = list(Cabinet.objects.filter(is_deleted=False)[:2])
        cabinet = cabinets[0] if len(cabinets) == 1 else None
    if cabinet is None:
        print('\n  [accounts 0016] No "ATGC Congo" cabinet and not exactly one cabinet here — Brave Bakulu not added.')
        return

    user = User.objects.filter(email__iexact=EMAIL).first()
    if user is None:
        username = 'brave.bakulu'
        if User.objects.filter(username=username).exists():
            username = 'bravebakulu'
        user = User.objects.create(
            username=username, email=EMAIL, first_name='Brave', last_name='Bakulu',
            password=make_password(None), must_change_password=True, is_active=True,
        )
    UserCabinetRole.objects.update_or_create(
        user=user, cabinet=cabinet,
        defaults={'role': 'CHIEF_ENGINEER', 'status': 'APPROVED', 'site': None, 'is_deleted': False},
    )
    print(f'\n  [accounts 0016] {user.username} <{EMAIL}> — Chef des Ingénieurs @ {cabinet.name}.')


class Migration(migrations.Migration):
    dependencies = [('accounts', '0015_whatsapp_phone')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
