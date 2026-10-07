"""Helpers for managing a user's active company.

The active company is stored in the session under ``SESSION_KEY``. Every
authenticated request exposes it as ``request.company`` (set by
``sign_docs_project.middleware.ActiveCompanyMiddleware``).
"""
from .models import Company

SESSION_KEY = 'active_company_id'


def ensure_default_company(user):
    """Return the user's default company, creating one if the user has none.

    - If the user already has a default company, it is returned.
    - Otherwise the first company owned by the user is promoted to default.
    - If the user has no companies at all, a default one is created.
    """
    company = Company.objects.filter(user=user, is_default=True).first()
    if company:
        return company

    company = Company.objects.filter(user=user).first()
    if company:
        company.is_default = True
        company.save(update_fields=['is_default'])
        return company

    return Company.objects.create(
        user=user,
        name=f"{user.username}'s Company",
        is_default=True,
    )


def get_active_company(request):
    """Return the currently selected company for the request's user.

    Falls back to (and stores) the user's default company when no valid
    company is selected. Returns ``None`` for anonymous users.
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return None

    # If the middleware already resolved it, reuse that value.
    cached = getattr(request, 'company', None)
    if cached is not None:
        return cached

    company_id = request.session.get(SESSION_KEY)
    company = None
    if company_id:
        company = Company.objects.filter(id=company_id, user=user).first()

    if company is None:
        company = ensure_default_company(user)

    request.session[SESSION_KEY] = company.id
    return company


def set_active_company(request, company):
    """Store ``company`` as the request's active company in the session."""
    request.session[SESSION_KEY] = company.id
