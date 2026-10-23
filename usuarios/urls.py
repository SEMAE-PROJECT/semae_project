from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import CustomLoginView
from .forms import UsuarioLoginForm

urlpatterns = [
    path('', views.lista_usuarios, name='lista_usuarios'),
    path('menu/', views.menu_principal, name='menu_principal'),
    path('listar/', views.lista_usuarios, name='lista'),
    path('criar/', views.criar_usuario, name='criar_usuario'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout_usuario'),
    path('editar/<int:pk>/', views.editar_usuario, name='editar_usuario'),
    path('excluir/<int:pk>/', views.excluir_usuario, name='excluir_usuario'),
    path('menu/secretario/', views.menu_secretario, name='menu_secretario'),
    path('menu/diretor/', views.menu_diretor, name='menu_diretor'),
    path('menu/nutricionista/', views.menu_nutricionista, name='menu_nutricionista'),
    path('menu/estoquista/', views.menu_estoquista, name='menu_estoquista'),
]