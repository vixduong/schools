from rest_framework.permissions import BasePermission

from .models import Membership


class HasMembership(BasePermission):
    """The default permission: an active Membership in `request.school`, never just
    'is authenticated'. Leaves the Membership on `request.membership`."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        request.membership = Membership.objects.filter(
            school=request.school, account=request.user, status=Membership.Status.ACTIVE
        ).first()
        return request.membership is not None
