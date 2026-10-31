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


class NotRequesterOrAssignee(BasePermission):
    """Second-person confirmation of a self-granted principal_board: the confirmer is neither the
    requester nor the assignee. Who may confirm at all is the engine's call (`accounts.manage`)."""

    def has_object_permission(self, request, view, obj):
        return request.membership.pk not in (obj.requested_by_id, obj.membership_id)
