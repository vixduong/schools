from collections.abc import Callable

from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.permissions import HasMembership

from .actor import Actor
from .engine import can
from .matrix import ACTIONS


class CanPermission(BasePermission):
    """Base of the classes `Can(...)` builds, so the open-views test can recognise them."""

    action: str
    target_getter: Callable
    read: bool = False
    read_on_writes: bool = False

    def has_permission(self, request, view):
        if getattr(request, "membership", None) is None and not HasMembership().has_permission(
            request, view
        ):
            return False
        read = self.read and (self.read_on_writes or request.method in SAFE_METHODS)
        return can(Actor.of(request), self.action, self.target_getter(request, view), read=read)


def school_of_request(request, view):
    return request.school


def Can(
    action: str,
    target_getter: Callable = school_of_request,
    *,
    read: bool = False,
    read_on_writes: bool = False,
) -> type[CanPermission]:
    """DRF permission: the request's member may do `action` on the target `target_getter(request,
    view)` returns (default: the request's School).

    `read=True` also accepts the read-only (👁) cells, for safe methods (GET, HEAD, OPTIONS) only:
    a write is never gated by a read-only cell. The one exception is the explicit
    `read_on_writes=True`, used by `RoleAssignmentViewSet.confirm`, where the principal board may
    confirm although it only reads the role assignments otherwise."""
    assert action in ACTIONS, f"unknown action {action}"
    attrs = {
        "action": action,
        "target_getter": staticmethod(target_getter),
        "read": read,
        "read_on_writes": read_on_writes,
    }
    return type(f"Can[{action}]", (CanPermission,), attrs)
