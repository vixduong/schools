from rest_framework.permissions import BasePermission

from .models import Membership, RoleAssignment


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


class IsSchoolAdmin(BasePermission):
    """The School admin's `school_admin` Role Assignment is in force. Always listed after
    HasMembership, which sets `request.membership`. Temporary: slice 5 replaces it with the one
    permission check fed by Role Assignments in force."""

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        return membership is not None and (
            RoleAssignment.objects.in_force()
            .filter(membership=membership, role=RoleAssignment.Role.SCHOOL_ADMIN)
            .exists()
        )
