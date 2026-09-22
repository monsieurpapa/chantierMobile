from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from accounts.models import Cabinet, User
from projects.models import Site
from chantiermobile.constants import (
    PersonnelType, AgentCategory, PersonnelStatus, Trade, LeaveType, ApprovalStatus,
)

class Skill(BaseModel):
    name = models.CharField(max_length=100, verbose_name=_('Skill Name')) # e.g. Maçon, Ferrailleur
    description = models.TextField(blank=True, verbose_name=_('Description'))
    
    def __str__(self):
        return self.name

class Personnel(BaseModel):
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='personnel')
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='personnel_profile', help_text=_("Link to system user if they have login access"))
    first_name = models.CharField(max_length=100, verbose_name=_('First Name'))
    last_name = models.CharField(max_length=100, verbose_name=_('Last Name'))
    personnel_type = models.CharField(
        max_length=20, choices=PersonnelType.choices, default=PersonnelType.EMPLOYE,
        verbose_name=_('Type'),
        help_text=_("Employé permanent, tâcheron (journalier) ou prestataire (sous-traitant)"),
    )
    skills = models.ManyToManyField(Skill, blank=True)
    default_daily_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text=_("Default daily cost"), verbose_name=_('Default Daily Rate'))
    monthly_salary = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_("Salaire mensuel fixe (agents administratifs / ingénieurs). Laisser vide pour un ouvrier payé au journalier."),
        verbose_name=_('Salaire mensuel'),
    )
    category = models.CharField(
        max_length=20, choices=AgentCategory.choices, default=AgentCategory.TERRAIN,
        verbose_name=_('Catégorie'),
        help_text=_("Agent de terrain ou d'administration"),
    )
    trade = models.CharField(
        max_length=20, choices=Trade.choices, blank=True,
        verbose_name=_('Fonction / Métier'),
        help_text=_("Fonction de l'ouvrier (Maçon, Menuisier, Plombier, ...)"),
    )
    status = models.CharField(
        max_length=20, choices=PersonnelStatus.choices, default=PersonnelStatus.ACTIF,
        verbose_name=_('Statut'),
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_subcontractor(self):
        """True for Tâcherons and Prestataires — non-payroll workers."""
        return self.personnel_type in (PersonnelType.TACHERON, PersonnelType.PRESTATAIRE)

    @property
    def is_eligible(self):
        return self.status == PersonnelStatus.ACTIF

class SiteAssignment(BaseModel):
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='assignments')
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='assignments')
    role = models.CharField(max_length=100, help_text=_("Specific role on this site, e.g. Chef d'équipe"), verbose_name=_('Role'))
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text=_("Agreed rate for this specific assignment"), verbose_name=_('Daily Rate'))
    agreement_document = models.FileField(
        upload_to='personnel/agreements/', null=True, blank=True,
        verbose_name=_("Convention (document)"),
        help_text=_("Convention de main-d'œuvre signée pour cette affectation."),
    )
    agreement_notes = models.TextField(
        blank=True, verbose_name=_('Termes de la convention'),
        help_text=_("Conditions particulières de la convention de main-d'œuvre."),
    )

    def clean(self):
        from django.core.exceptions import ValidationError
        # Validation logic for overlapping assignments could go here
        # For MVP, we'll enforce it in the form/view or simple clean method
        if self.personnel_id and not self.personnel.is_eligible:
            raise ValidationError({
                'personnel': _(
                    "%(name)s n'est pas éligible (statut : %(status)s) et ne peut pas être affecté(e) à un chantier."
                ) % {'name': self.personnel, 'status': self.personnel.get_status_display()},
            })

    def __str__(self):
        return f"{self.personnel} -> {self.site} ({self.role})"


class PersonnelDocument(BaseModel):
    """A file in an agent/worker's 'dossier' — ID copy, diploma, contract,
    medical certificate, etc."""
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='documents')
    label = models.CharField(max_length=150, verbose_name=_('Libellé'), help_text=_("Ex: Copie CNI, Diplôme, Contrat de travail"))
    file = models.FileField(upload_to='personnel/documents/', verbose_name=_('Fichier'))
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.label} — {self.personnel}"


class Holiday(BaseModel):
    """A company-wide public holiday (jour férié)."""
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='holidays')
    name = models.CharField(max_length=150, verbose_name=_('Nom'))
    date = models.DateField(verbose_name=_('Date'))

    class Meta:
        ordering = ['date']
        unique_together = ('cabinet', 'date')

    def __str__(self):
        return f"{self.name} ({self.date})"


class Leave(BaseModel):
    """A personnel absence: congé (leave) or other declared time off.
    Public holidays that apply to everyone belong on the Holiday model
    instead; this is per-worker."""
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='leaves')
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices, default=LeaveType.CONGE, verbose_name=_('Type'))
    start_date = models.DateField(verbose_name=_('Date de début'))
    end_date = models.DateField(verbose_name=_('Date de fin'))
    reason = models.TextField(blank=True, verbose_name=_('Motif'))
    status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING, verbose_name=_('Statut'))
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='leave_decisions')
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.personnel} — {self.get_leave_type_display()} ({self.start_date} → {self.end_date})"

    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1
