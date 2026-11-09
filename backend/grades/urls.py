from django.urls import path

from . import views

urlpatterns = [
    path("gradebooks/", views.GradebooksView.as_view(), name="gradebooks"),
    path("gradebooks/mine/", views.MyGradebooksView.as_view(), name="my-gradebooks"),
    path("gradebooks/<int:pk>/", views.GradebookView.as_view(), name="gradebook"),
    path("gradebooks/<int:pk>/cells/", views.GradebookCellsView.as_view(), name="gradebook-cells"),
    *(
        path(f"gradebooks/<int:pk>/{name}/", view.as_view(), name=f"gradebook-{name}")
        for name, view in (
            ("submit", views.SubmitView),
            ("withdraw", views.WithdrawView),
            ("return", views.ReturnView),
            ("approve", views.ApproveView),
            ("reopen", views.ReopenView),
        )
    ),
    path(
        "gradebooks/<int:pk>/columns/<int:column>/release/",
        views.ColumnReleaseView.as_view(),
        name="gradebook-column-release",
    ),
    path(
        "gradebooks/<int:pk>/history/",
        views.GradebookHistoryView.as_view(),
        name="gradebook-history",
    ),
]
