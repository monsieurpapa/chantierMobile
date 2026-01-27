from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from .models import UserCabinetRole, Cabinet
from chantiermobile.constants import UserRoles, ApprovalStatus, FormPlaceholders

User = get_user_model()


class UserProfileForm(forms.ModelForm):
    """Form for updating user profile information"""
    
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First Name'
        })
    )
    
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last Name'
        })
    )
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email Address'
        })
    )
    
    phone_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Phone Number',
            'type': 'tel'
        })
    )
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number']


class UserAdminForm(forms.ModelForm):
    """Admin form for managing users - superadmin only"""
    
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First Name'
        })
    )
    
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last Name'
        })
    )
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email Address'
        })
    )
    
    phone_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Phone Number',
            'type': 'tel'
        })
    )
    
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text='Uncheck to deactivate user account'
    )
    
    is_staff = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text='Check to grant staff access'
    )
    
    is_superuser = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text='Check to grant superadmin access'
    )
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number', 'is_active', 'is_staff', 'is_superuser']


class UserCabinetRoleForm(forms.ModelForm):
    """Form for viewing user cabinet roles"""
    
    cabinet_name = forms.CharField(
        max_length=255,
        disabled=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control-plaintext',
        })
    )
    
    role = forms.CharField(
        max_length=50,
        disabled=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control-plaintext',
        })
    )
    
    status = forms.CharField(
        max_length=20,
        disabled=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control-plaintext',
        })
    )
    
    class Meta:
        model = UserCabinetRole
        fields = ['cabinet_name', 'role', 'status']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['cabinet_name'].initial = self.instance.cabinet.name
            self.fields['role'].initial = self.instance.get_role_display()
            self.fields['status'].initial = self.instance.get_status_display()


class AssignUserToCabinetForm(forms.ModelForm):
    """Form for superadmin to assign users to cabinets"""
    
    cabinet = forms.ModelChoiceField(
        queryset=Cabinet.objects.all().order_by('name'),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-placeholder': 'Select Cabinet'
        }),
        label='Cabinet',
        help_text='Select the cabinet to assign this user to'
    )
    
    role = forms.ChoiceField(
        choices=UserRoles.choices,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-placeholder': 'Select Role'
        }),
        label='Role',
        help_text='Select the user role in this cabinet'
    )
    
    status = forms.ChoiceField(
        choices=ApprovalStatus.choices,
        initial=ApprovalStatus.PENDING,
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        label='Status',
        help_text='Set initial approval status'
    )
    
    class Meta:
        model = UserCabinetRole
        fields = ['cabinet', 'role', 'status']
    
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Exclude cabinets user already has roles in
        assigned_cabinets = user.cabinet_roles.values_list('cabinet_id', flat=True)
        self.fields['cabinet'].queryset = Cabinet.objects.exclude(
            id__in=assigned_cabinets
        ).order_by('name')
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.user = self.user
        if commit:
            instance.save()
        return instance


class CabinetForm(forms.ModelForm):
    """Form for creating and editing Cabinet information"""
    
    class Meta:
        model = Cabinet
        fields = ['name', 'address', 'tax_id', 'logo']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Cabinet Name')
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Full Address')
            }),
            'tax_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Tax ID / Registration Number')
            }),
            'logo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }


class AssignRoleToCabinetUserForm(forms.ModelForm):
    """Form for editing role assignment to user in cabinet"""
    
    class Meta:
        model = UserCabinetRole
        fields = ['role', 'status']
        widgets = {
            'role': forms.Select(attrs={
                'class': 'form-select'
            }),
            'status': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].widget.attrs.update({
            'class': 'form-select',
            'title': _('Select the user\'s role in this cabinet')
        })
        self.fields['status'].widget.attrs.update({
            'class': 'form-select',
            'title': _('Select assignment status')
        })

