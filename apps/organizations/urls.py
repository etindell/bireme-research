"""
URL configuration for organizations app.
"""
from django.urls import path

from . import views

app_name = 'organizations'

urlpatterns = [
    path('create/', views.OrganizationCreateView.as_view(), name='create'),
    path('settings/', views.OrganizationUpdateView.as_view(), name='settings'),
    path('switch/<int:pk>/', views.OrganizationSwitchView.as_view(), name='switch'),
    path('members/', views.OrganizationMembersView.as_view(), name='members'),
    path('members/add/', views.AddMemberView.as_view(), name='add_member'),
    path('members/<int:pk>/remove/', views.RemoveMemberView.as_view(), name='remove_member'),
    path('invites/<int:pk>/cancel/', views.CancelInviteView.as_view(), name='cancel_invite'),
]
