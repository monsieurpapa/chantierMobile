from django.db import models
from core.models import BaseModel
from accounts.models import Cabinet, User
from projects.models import Site

class Skill(BaseModel):
    name = models.CharField(max_length=100) # e.g. Maçon, Ferrailleur
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name

class Personnel(BaseModel):
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='personnel')
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='personnel_profile', help_text="Link to system user if they have login access")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    skills = models.ManyToManyField(Skill, blank=True)
    default_daily_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="Default daily cost")
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class SiteAssignment(BaseModel):
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='assignments')
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='assignments')
    role = models.CharField(max_length=100, help_text="Specific role on this site, e.g. Chef d'équipe")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="Agreed rate for this specific assignment")

    def clean(self):
        # Validation logic for overlapping assignments could go here
        # For MVP, we'll enforce it in the form/view or simple clean method
        pass

    def __str__(self):
        return f"{self.personnel} -> {self.site} ({self.role})"
