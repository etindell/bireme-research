from django.urls import path

from . import views

app_name = 'portfolio'

urlpatterns = [
    path('', views.PortfolioListView.as_view(), name='list'),
    path('create/', views.PortfolioCreateView.as_view(), name='create'),
    path('<int:pk>/', views.PortfolioDetailView.as_view(), name='detail'),
    path('<int:pk>/re-extract/', views.PortfolioReExtractView.as_view(), name='re_extract'),
    path('<int:pk>/update-weight/<int:position_pk>/', views.PortfolioUpdateWeightView.as_view(), name='update_weight'),
    path('<int:pk>/recalculate/', views.PortfolioRecalculateView.as_view(), name='recalculate'),
    path('<int:pk>/volatility/', views.PortfolioVolatilityView.as_view(), name='volatility'),
]
