from django.urls import path

from .views import ActivateView, CsrfView, LoginView, LogoutView, MeView, SchoolView

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("activate/", ActivateView.as_view(), name="auth-activate"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("school/", SchoolView.as_view(), name="auth-school"),
]
