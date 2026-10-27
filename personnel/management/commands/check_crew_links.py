"""Lists the chantier crew entries whose profile link used to 404
(2026-10-27) and, with --fix, repairs the unambiguous ones.

    python manage.py check_crew_links            # report only
    python manage.py check_crew_links --fix      # repair

Two kinds of entries:

- "autre cabinet": the person's record belongs to another cabinet than the
  chantier. With --fix, the record moves to the chantier's cabinet when
  ALL of the person's active assignments are in that one cabinet; when
  they work for several cabinets, it is only reported (decide by hand).
- "personne supprimée": the person's record was deleted but the assignment
  is still active. With --fix, the assignment is soft-deleted too (it
  stays in the database; restorable).
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from personnel.models import Personnel, SiteAssignment


class Command(BaseCommand):
    help = "Signale (et répare avec --fix) les affectations dont la fiche personnel donnait une erreur 404."

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true', help='Réparer les cas sans ambiguïté.')

    def handle(self, *args, fix=False, **options):
        live = SiteAssignment.objects.select_related('site__cabinet', 'personnel__cabinet')
        mismatched = list(live.exclude(personnel__cabinet_id=F('site__cabinet_id')).filter(personnel__is_deleted=False))
        orphaned = list(live.filter(personnel__is_deleted=True))

        self.stdout.write(f"Affectations « autre cabinet » : {len(mismatched)}")
        by_person = defaultdict(list)
        for a in mismatched:
            by_person[a.personnel_id].append(a)
            self.stdout.write(f"  - {a.site.name} [{a.site.cabinet}] ← {a.personnel.get_full_name()} [fiche dans : {a.personnel.cabinet}]")
        self.stdout.write(f"Affectations de personnes supprimées : {len(orphaned)}")
        for a in orphaned:
            self.stdout.write(f"  - {a.site.name} [{a.site.cabinet}] ← {a.personnel.get_full_name()} (supprimé(e))")

        if not fix:
            if mismatched or orphaned:
                self.stdout.write("Relancez avec --fix pour réparer les cas sans ambiguïté.")
            return

        moved, manual = 0, []
        with transaction.atomic():
            for person_id in by_person:
                person = Personnel.objects.select_related('cabinet').get(pk=person_id)
                cabinets = set(SiteAssignment.objects.filter(personnel=person).values_list('site__cabinet_id', flat=True))
                if len(cabinets) == 1:
                    target = by_person[person_id][0].site.cabinet
                    person.cabinet = target
                    person.save(update_fields=['cabinet', 'updated_at'])
                    moved += 1
                    self.stdout.write(self.style.SUCCESS(f"  ✓ {person.get_full_name()} → cabinet {target}"))
                else:
                    manual.append(person)
            for a in orphaned:
                a.delete()
        self.stdout.write(self.style.SUCCESS(
            f"Fiches déplacées : {moved} · affectations de personnes supprimées retirées : {len(orphaned)}"))
        for person in manual:
            self.stdout.write(self.style.WARNING(
                f"  ! {person.get_full_name()} travaille pour plusieurs cabinets : à régler à la main."))
