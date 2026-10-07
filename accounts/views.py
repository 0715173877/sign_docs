import random
import string
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from .forms import RegisterForm, ProfileForm, CompanyForm, CompanySignatureForm
from .models import UserProfile, Company
from .company import get_active_company, set_active_company, ensure_default_company
from documents.models import OTP
from documents.views import send_otp_email, send_otp_sms


User = get_user_model()

# --- Account Lockout Configuration ---
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15

# --- OTP Rate Limiting ---
MAX_OTP_RESENDS = 3
OTP_RESEND_WINDOW_MINUTES = 10


def generate_otp():
    """Generate a random 6-digit OTP."""
    return "".join(random.choices(string.digits, k=6))


def _get_login_attempts(request):
    """Get the number of failed login attempts from session."""
    return request.session.get('login_attempts', 0)


def _increment_login_attempts(request):
    """Increment failed login attempts and set lockout time if threshold reached."""
    attempts = _get_login_attempts(request) + 1
    request.session['login_attempts'] = attempts
    if attempts >= MAX_LOGIN_ATTEMPTS:
        request.session['login_locked_until'] = (timezone.now() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)).isoformat()
    return attempts


def _reset_login_attempts(request):
    """Reset failed login attempts."""
    request.session.pop('login_attempts', None)
    request.session.pop('login_locked_until', None)


def _is_account_locked(request):
    """Check if the account is currently locked due to too many failed attempts."""
    locked_until_str = request.session.get('login_locked_until')
    if locked_until_str:
        locked_until = timezone.datetime.fromisoformat(locked_until_str)
        if timezone.now() < locked_until:
            return True
        # Lockout period has expired, reset
        _reset_login_attempts(request)
    return False


def _get_otp_resend_count(request):
    """Get the number of OTP resends in the current window."""
    return request.session.get('otp_resend_count', 0)


def _increment_otp_resend(request):
    """Increment OTP resend count and set window start if first resend."""
    count = _get_otp_resend_count(request) + 1
    request.session['otp_resend_count'] = count
    if count == 1:
        request.session['otp_resend_window_start'] = timezone.now().isoformat()
    return count


def _can_resend_otp(request):
    """Check if user is allowed to resend OTP (rate limited)."""
    count = _get_otp_resend_count(request)
    window_start_str = request.session.get('otp_resend_window_start')

    if count == 0:
        return True

    if window_start_str:
        window_start = timezone.datetime.fromisoformat(window_start_str)
        if timezone.now() - window_start > timedelta(minutes=OTP_RESEND_WINDOW_MINUTES):
            # Window expired, reset
            request.session.pop('otp_resend_count', None)
            request.session.pop('otp_resend_window_start', None)
            return True

    return count < MAX_OTP_RESENDS


def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Every user needs at least one company to sign documents.
            ensure_default_company(user)
            login(request, user)
            messages.success(request, 'Account created successfully!')
            return redirect('profile')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    # If user is already fully authenticated, redirect to dashboard
    if request.user.is_authenticated and not request.session.get('pending_otp'):
        return redirect('dashboard')

    # If user has pending OTP, redirect to OTP page
    if request.session.get('pending_otp'):
        return redirect('login_otp')

    # Check if account is locked
    if _is_account_locked(request):
        remaining = LOCKOUT_DURATION_MINUTES
        messages.error(
            request,
            f'Account temporarily locked due to too many failed attempts. '
            f'Please try again in {remaining} minutes.'
        )
        return render(request, 'accounts/login.html', {'form': AuthenticationForm()})

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            _reset_login_attempts(request)

            # Store user ID in session for OTP verification
            request.session['pending_otp_user_id'] = user.id
            request.session['pending_otp'] = True

            # Generate and send OTP
            otp_code = generate_otp()
            # Store OTP in session (we'll verify against this)
            request.session['login_otp_code'] = otp_code
            request.session['login_otp_created_at'] = timezone.now().isoformat()

            # Send OTP via SMS (if phone is set) or email
            profile = UserProfile.objects.filter(user=user).first()
            if profile and profile.phone_number:
                sms_sent = send_otp_sms(user, None, otp_code)
                if sms_sent:
                    request.session['login_otp_method'] = 'sms'
                else:
                    send_otp_email(user, None, otp_code)
                    request.session['login_otp_method'] = 'email'
            else:
                send_otp_email(user, None, otp_code)
                request.session['login_otp_method'] = 'email'

            messages.info(request, 'A verification code has been sent to your registered contact.')
            return redirect('login_otp')
        else:
            _increment_login_attempts(request)
            remaining_attempts = MAX_LOGIN_ATTEMPTS - _get_login_attempts(request)
            if remaining_attempts > 0:
                messages.error(
                    request,
                    f'Invalid username or password. {remaining_attempts} attempt(s) remaining.'
                )
            else:
                messages.error(
                    request,
                    f'Account locked due to too many failed attempts. '
                    f'Please try again in {LOCKOUT_DURATION_MINUTES} minutes.'
                )
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})


@never_cache
def login_otp_view(request):
    """Verify OTP after login to complete authentication."""
    # Check if there's a pending OTP verification
    if not request.session.get('pending_otp'):
        return redirect('login')

    user_id = request.session.get('pending_otp_user_id')
    if not user_id:
        return redirect('login')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('login')

    otp_method = request.session.get('login_otp_method', 'email')
    profile = UserProfile.objects.filter(user=user).first()

    # Handle resend with rate limiting
    if request.GET.get('resend') == 'sms' or request.GET.get('resend') == 'email':
        if not _can_resend_otp(request):
            messages.error(
                request,
                f'Too many OTP resend requests. Please wait {OTP_RESEND_WINDOW_MINUTES} minutes before trying again.'
            )
            return redirect('login_otp')

        method = request.GET.get('resend')
        otp_code = generate_otp()
        request.session['login_otp_code'] = otp_code
        request.session['login_otp_created_at'] = timezone.now().isoformat()
        _increment_otp_resend(request)

        if method == 'sms' and profile and profile.phone_number:
            sms_sent = send_otp_sms(user, None, otp_code)
            if sms_sent:
                request.session['login_otp_method'] = 'sms'
                messages.success(request, 'OTP resent via SMS.')
            else:
                send_otp_email(user, None, otp_code)
                request.session['login_otp_method'] = 'email'
                messages.success(request, 'OTP resent via email.')
        else:
            send_otp_email(user, None, otp_code)
            request.session['login_otp_method'] = 'email'
            messages.success(request, 'OTP resent via email.')

        return redirect('login_otp')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp_code', '').strip()
        stored_otp = request.session.get('login_otp_code')
        created_at_str = request.session.get('login_otp_created_at')

        if stored_otp and entered_otp == stored_otp:
            # Check expiry (10 minutes)
            if created_at_str:
                created_at = timezone.datetime.fromisoformat(created_at_str)
                if timezone.now() - created_at > timezone.timedelta(minutes=10):
                    messages.error(request, 'OTP has expired. Please login again.')
                    # Clean up session
                    for key in ['pending_otp', 'pending_otp_user_id', 'login_otp_code', 'login_otp_created_at', 'login_otp_method']:
                        request.session.pop(key, None)
                    return redirect('login')

            # OTP is valid - fully log the user in
            login(request, user)

            # Select the user's default company for this session
            default_company = ensure_default_company(user)
            set_active_company(request, default_company)

            # Clean up OTP session data
            for key in ['pending_otp', 'pending_otp_user_id', 'login_otp_code', 'login_otp_created_at', 'login_otp_method']:
                request.session.pop(key, None)

            messages.success(request, f'Welcome back, {user.username}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid verification code. Please try again.')

    # Determine display info
    if otp_method == 'sms' and profile and profile.phone_number:
        otp_destination = profile.phone_number
        if len(otp_destination) > 6:
            otp_destination = otp_destination[:3] + "****" + otp_destination[-3:]
    else:
        otp_destination = user.email

    context = {
        'otp_method': otp_method,
        'otp_destination': otp_destination,
        'has_phone': profile and profile.phone_number,
    }

    # DEV ONLY: When DEBUG is on, expose the OTP on the page so the flow can be
    # tested without a working SMS/email gateway. Never enabled in production.
    if settings.DEBUG:
        context['debug_otp'] = request.session.get('login_otp_code')

    return render(request, 'accounts/login_otp.html', context)


@never_cache
@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def profile_view(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    # Make sure the user always has at least one company.
    ensure_default_company(request.user)

    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = ProfileForm(instance=profile)

    companies = Company.objects.filter(user=request.user)
    active_company = get_active_company(request)

    return render(request, 'accounts/profile.html', {
        'form': form,
        'profile': profile,
        'companies': companies,
        'active_company': active_company,
        'company_form': CompanyForm(),
        'company_signature_form': CompanySignatureForm(),
    })


@login_required
@require_POST
def company_create_view(request):
    """Create a new company for the logged-in user."""
    form = CompanyForm(request.POST)
    if form.is_valid():
        company = form.save(commit=False)
        company.user = request.user
        # The very first company becomes the default.
        if not Company.objects.filter(user=request.user).exists():
            company.is_default = True
        company.save()
        messages.success(
            request,
            f'Company "{company.name}" created. Upload its signature and stamp below.'
        )
    else:
        error = form.errors.get('name')
        messages.error(
            request,
            error[0] if error else 'Please enter a valid company name.'
        )
    return redirect('profile')


@login_required
@require_POST
def company_switch_view(request, company_id):
    """Switch the active company for the current session."""
    company = get_object_or_404(Company, id=company_id, user=request.user)
    set_active_company(request, company)
    messages.success(request, f'Switched to "{company.name}".')
    return redirect('dashboard')


@login_required
@require_POST
def company_update_view(request, company_id):
    """Update a company's signature and/or stamp."""
    company = get_object_or_404(Company, id=company_id, user=request.user)
    form = CompanySignatureForm(request.POST, request.FILES, instance=company)
    if form.is_valid():
        form.save()
        messages.success(request, f'Signature & stamp updated for "{company.name}".')
    else:
        messages.error(
            request,
            'Could not save the image. Please upload a valid PNG file.'
        )
    return redirect('profile')


@login_required
@require_POST
def company_set_default_view(request, company_id):
    """Mark a company as the default one selected after login."""
    company = get_object_or_404(Company, id=company_id, user=request.user)
    Company.objects.filter(user=request.user).update(is_default=False)
    company.is_default = True
    company.save(update_fields=['is_default'])
    messages.success(request, f'"{company.name}" is now your default company.')
    return redirect('profile')


@login_required
@require_POST
def company_delete_view(request, company_id):
    """Delete a company (a user must always keep at least one)."""
    company = get_object_or_404(Company, id=company_id, user=request.user)

    if Company.objects.filter(user=request.user).count() <= 1:
        messages.error(request, 'You must keep at least one company.')
        return redirect('profile')

    was_active = request.session.get('active_company_id') == company.id
    was_default = company.is_default
    name = company.name
    company.delete()

    if was_active:
        request.session.pop('active_company_id', None)

    if was_default:
        new_default = Company.objects.filter(user=request.user).first()
        if new_default:
            new_default.is_default = True
            new_default.save(update_fields=['is_default'])

    messages.success(request, f'Company "{name}" deleted.')
    return redirect('profile')
