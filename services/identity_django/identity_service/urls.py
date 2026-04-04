from __future__ import annotations

from django.urls import path

from platform_identity import views


urlpatterns = [
    path("api/platform/auth/status", views.auth_status),
    path("api/platform/auth/login", views.auth_login),
    path("api/platform/auth/authenticate", views.auth_authenticate),
    path("api/platform/auth/logout", views.auth_logout),
    path("api/platform/auth/change-password", views.auth_change_password),
    path("api/platform/users/create", views.users_create),
    path("api/platform/users/by-username", views.users_by_username),
    path("api/platform/users/list", views.users_list),
    path("api/platform/users/<uuid:user_id>", views.users_get),
    path("api/platform/users/<uuid:user_id>/update", views.users_update),
    path("api/platform/users/<uuid:user_id>/delete", views.users_delete),
    path("api/platform/users/<uuid:user_id>/profile", views.users_profile),
    path("api/platform/users/<uuid:user_id>/quota", views.users_quota),
]
