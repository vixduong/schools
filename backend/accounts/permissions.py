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


class HasRoleInForce(BasePermission):
    """One of `roles` is in force for `request.membership`. Always listed after HasMembership."""

    roles: tuple[str, ...] = ()

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        return membership is not None and (
            RoleAssignment.objects.in_force()
            .filter(membership=membership, role__in=self.roles)
            .exists()
        )


class IsSchoolAdmin(HasRoleInForce):
    """The School admin's `school_admin` Role Assignment is in force. Temporary: slice 5
    replaces it with the one permission check fed by Role Assignments in force."""

    roles = (RoleAssignment.Role.SCHOOL_ADMIN,)


class CanConfirmRoleAssignment(HasRoleInForce):
    """Second-person confirmation of a self-granted principal_board: a School admin or
    principal_board in force who is neither the requester nor the assignee."""

    roles = (RoleAssignment.Role.SCHOOL_ADMIN, RoleAssignment.Role.PRINCIPAL_BOARD)

    def has_object_permission(self, request, view, obj):
        return request.membership.pk not in (obj.requested_by_id, obj.membership_id)
