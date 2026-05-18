from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile, normalize_phone


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. +255712345678',
            'type': 'tel',
        }),
        help_text="Optional. Phone number for receiving OTP via SMS (e.g. +255712345678)"
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken. Please choose another.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email address is already registered.")
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone:
            normalized = normalize_phone(phone)
            if normalized:
                # Check uniqueness using normalized form
                all_phones = UserProfile.objects.values_list('phone_number', flat=True)
                for existing in all_phones:
                    if existing and normalize_phone(existing) == normalized:
                        raise forms.ValidationError("This phone number is already in use by another account.")
                # Store normalized version
                self.cleaned_data['phone_number'] = phone  # Keep original for display
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            profile, created = UserProfile.objects.get_or_create(user=user)
            phone = self.cleaned_data.get('phone_number')
            if phone:
                normalized = normalize_phone(phone)
                profile.phone_number = normalized or phone
                profile.save(update_fields=['phone_number'])
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['signature', 'stamp', 'phone_number']
        widgets = {
            'signature': forms.FileInput(attrs={'accept': 'image/png'}),
            'stamp': forms.FileInput(attrs={'accept': 'image/png'}),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. +255712345678',
                'type': 'tel',
            }),
        }

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone:
            normalized = normalize_phone(phone)
            if normalized:
                # Check uniqueness using normalized form, excluding current user's profile
                all_phones = UserProfile.objects.exclude(pk=self.instance.pk if self.instance and self.instance.pk else None).values_list('phone_number', flat=True)
                for existing in all_phones:
                    if existing and normalize_phone(existing) == normalized:
                        raise forms.ValidationError("This phone number is already in use by another account.")
                # Store normalized version for saving
                self.cleaned_data['phone_number'] = normalized
        return phone
