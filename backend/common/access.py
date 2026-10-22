from django.http import Http404
from rest_framework.exceptions import PermissionDenied

from companies.models import CompanyMember


def require_specialist(user):
    if not user.is_authenticated or not user.is_credit_specialist:
        raise PermissionDenied("Действие доступно кредитному специалисту.")


def require_member(user, company_id, capability=None):
    membership = CompanyMember.objects.filter(user=user, company_id=company_id, active=True).first()
    if membership is None:
        raise Http404
    if capability and not getattr(membership, capability):
        raise PermissionDenied("У представителя нет необходимых полномочий.")
    return membership


def company_scope(queryset, user, company_path):
    if not user.is_authenticated:
        return queryset.none()
    if user.is_credit_specialist:
        return queryset
    return queryset.filter(
        **{
            f"{company_path}__memberships__user": user,
            f"{company_path}__memberships__active": True,
        }
    )
