from django import forms
from .models import Document


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['pdf_file', 'title']
        widgets = {
            'pdf_file': forms.FileInput(attrs={
                'accept': 'application/pdf',
                'class': 'form-control',
            }),
            'title': forms.TextInput(attrs={
                'placeholder': 'Optional document title',
                'class': 'form-control',
            }),
        }


class OTPForm(forms.Form):
    otp_code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter 6-digit OTP',
            'pattern': '[0-9]{6}',
            'maxlength': '6',
            'autocomplete': 'off',
        }),
        label='OTP Code'
    )
