from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.contrib.auth.models import Group
from django.http import HttpRequest, HttpResponse
from django.urls import reverse_lazy
from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum, IntegerField
from django.db.models.functions import Coalesce
from .models import Usuario, PerfilEscola
from .forms import UsuarioCadastroForm, UsuarioEditForm, UsuarioLoginForm
from produtos.models import Pedido, TipoProduto, Lote

# --- FUNÇÕES DE VERIFICAÇÃO DE ACESSO ---
def is_secretario(user):
    return user.is_authenticated and user.is_secretario() and user.cargo == "SECRETARIO"

def is_diretor(user):
    return user.is_authenticated and user.is_diretor() and user.cargo == "DIRETOR"

def is_nutricionista(user):
    return user.is_authenticated and user.is_nutricionista() and user.cargo == "NUTRICIONISTA"

def is_estoquista(user):
    return user.is_authenticated and user.is_estoquista() and user.cargo == "ESTOQUISTA"

def pode_ver_estoque(user):
    return user.is_authenticated and (user.cargo in ['SECRETARIO', 'NUTRICIONISTA', 'ESTOQUISTA'])

# --- VIEWS DE MENUS COM DASHBOARD ---
@login_required
@user_passes_test(is_secretario)
def menu_secretario(request):
    pedidos_validos = Pedido.objects.filter(Q(itens__isnull=False) | Q(itens_especiais__isnull=False)).distinct()
    context = {
        'kpi_pendentes': pedidos_validos.filter(status='PENDENTE', categoria='ESCOLAR').count(),
        'kpi_em_separacao': pedidos_validos.filter(status='APROVADO', categoria='ESCOLAR').count(),
        'kpi_entregues': pedidos_validos.filter(status='ENTREGUE').count(),
        'kpi_usuarios': Usuario.objects.count(),
    }
    return render(request, 'usuarios/menu_secretario.html', context)

@login_required
@user_passes_test(is_nutricionista)
def menu_nutricionista(request):
    hoje = date.today()
    pedidos_validos = Pedido.objects.filter(Q(itens__isnull=False) | Q(itens_especiais__isnull=False)).distinct()
    lotes_alerta = Lote.objects.filter(
        quantidade_pacotes__gt=0,
        data_validade__isnull=False,
        data_validade__lte=hoje + timedelta(days=30)
    ).count()
    context = {
        'kpi_pendentes': pedidos_validos.filter(status='PENDENTE', categoria='ALIMENTICIO_LIMPEZA').count(),
        'kpi_aprovados': pedidos_validos.filter(status='APROVADO', categoria='ALIMENTICIO_LIMPEZA').count(),
        'kpi_entregues': pedidos_validos.filter(status='ENTREGUE', categoria='ALIMENTICIO_LIMPEZA').count(),
        'kpi_lotes_alerta': lotes_alerta,
    }
    return render(request, 'usuarios/menu_nutricionista.html', context)

@login_required
@user_passes_test(is_estoquista)
def menu_estoquista(request):
    hoje = date.today()
    produtos_ativos = TipoProduto.objects.filter(ativo=True).annotate(
        saldo=Coalesce(Sum('lotes__quantidade_pacotes'), 0, output_field=IntegerField())
    )
    lotes_alerta = Lote.objects.filter(
        quantidade_pacotes__gt=0,
        data_validade__isnull=False,
        data_validade__lte=hoje + timedelta(days=30)
    ).count()
    context = {
        'kpi_aguardando_envio': Pedido.objects.filter(status='APROVADO').count(),
        'kpi_sem_estoque': produtos_ativos.filter(saldo=0).count(),
        'kpi_lotes_alerta': lotes_alerta,
        'kpi_entregues': Pedido.objects.filter(status='ENTREGUE').count(),
    }
    return render(request, 'usuarios/menu_estoquista.html', context)

@login_required
@user_passes_test(is_diretor)
def menu_diretor(request):
    meus = Pedido.objects.filter(
        solicitante=request.user
    ).filter(Q(itens__isnull=False) | Q(itens_especiais__isnull=False)).distinct()
    context = {
        'kpi_pendentes': meus.filter(status='PENDENTE').count(),
        'kpi_aprovados': meus.filter(status='APROVADO').count(),
        'kpi_entregues': meus.filter(status='ENTREGUE').count(),
        'kpi_rejeitados': meus.filter(status='REJEITADO').count(),
    }
    return render(request, 'usuarios/menu_diretor.html', context)

@login_required
def menu_principal(request: HttpRequest) -> HttpResponse:
    if request.user.cargo == 'SECRETARIO':
        return redirect('menu_secretario')
    elif request.user.cargo == 'NUTRICIONISTA':
        return redirect('menu_nutricionista')
    elif request.user.cargo == 'DIRETOR':
        return redirect('menu_diretor')
    elif request.user.cargo == 'ESTOQUISTA':
        return redirect('menu_estoquista')
    return redirect('logout_usuario')


# --- GERENCIAMENTO DE USUÁRIOS (Apenas Secretário) ---
@login_required
@user_passes_test(is_secretario)
def lista_usuarios(request: HttpRequest) -> HttpResponse:
    usuarios = Usuario.objects.all()
    return render(request, 'usuarios/lista.html', {'usuarios': usuarios})

@login_required
@user_passes_test(is_secretario)
def criar_usuario(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = UsuarioCadastroForm(request.POST)
        
        if form.is_valid():
            with transaction.atomic():            
                novo_usuario = form.save()
                cargo_selecionado = novo_usuario.cargo 
                
                if cargo_selecionado == 'SECRETARIO':
                    grupo, _ = Group.objects.get_or_create(name='Secretário')
                    novo_usuario.groups.add(grupo)
                    
                elif cargo_selecionado == 'NUTRICIONISTA':
                    grupo, _ = Group.objects.get_or_create(name='Nutricionista')
                    novo_usuario.groups.add(grupo)
                    
                elif cargo_selecionado == 'ESTOQUISTA':
                    grupo, _ = Group.objects.get_or_create(name='Estoquista')
                    novo_usuario.groups.add(grupo)
                    
                elif cargo_selecionado == 'DIRETOR':
                    grupo, _ = Group.objects.get_or_create(name='Diretor')
                    novo_usuario.groups.add(grupo)
                    
                    nome_da_escola = request.POST.get('nome_escola')
                    if nome_da_escola:
                        PerfilEscola.objects.create(
                            usuario=novo_usuario,
                            nome_escola=nome_da_escola
                        )
                
            return redirect('lista_usuarios')
    else:
        form = UsuarioCadastroForm()
            
    return render(request, 'usuarios/criar.html', {'form': form})

@login_required
@user_passes_test(is_secretario)
def editar_usuario(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    
    if request.method == 'POST':
        form = UsuarioEditForm(request.POST, instance=usuario)
        if form.is_valid():
            user = form.save(commit=False)
            
            nova_senha = form.cleaned_data.get('nova_senha')
            if nova_senha:
                user.set_password(nova_senha)
            
            user.save()

            if user.cargo == 'DIRETOR':
                nome_escola = form.cleaned_data.get('nome_escola')
                PerfilEscola.objects.update_or_create(
                    usuario=user, 
                    defaults={'nome_escola': nome_escola}
                )
            else:
                PerfilEscola.objects.filter(usuario=user).delete()

            return redirect('lista_usuarios')
    else:
        form = UsuarioEditForm(instance=usuario)

    return render(request, 'usuarios/editar.html', {'form': form, 'usuario': usuario})

@login_required
@user_passes_test(is_secretario)
def excluir_usuario(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == 'POST':
        usuario.delete()
        return redirect('lista_usuarios')

    return render(request, 'usuarios/excluir.html', {'usuario': usuario})


# --- VIEWS DE AUTENTICAÇÃO ---
def login_usuario(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = UsuarioLoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect(settings.LOGIN_REDIRECT_URL)
    else: 
        form = UsuarioLoginForm()
    
    return render(request, 'usuarios/login.html', {'form': form})
    
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL) 

class CustomLoginView(LoginView):
    template_name = 'usuarios/login.html'
    authentication_form = UsuarioLoginForm

    def get_success_url(self):
        user = self.request.user

        if user.is_secretario():
            return reverse_lazy('menu_secretario')
        elif user.is_diretor():
            return reverse_lazy('menu_diretor')
        elif user.is_nutricionista():
            return reverse_lazy('menu_nutricionista')
        elif user.is_estoquista():
            return reverse_lazy('menu_estoquista')
        else:
            return reverse_lazy('login')

@login_required
def menu_principal(request: HttpRequest) -> HttpResponse:
    if request.user.cargo == 'SECRETARIO':
        return redirect('menu_secretario')
    elif request.user.cargo == 'NUTRICIONISTA':
        return redirect('menu_nutricionista')
    elif request.user.cargo == 'DIRETOR':
        return redirect('menu_diretor')
    elif request.user.cargo == 'ESTOQUISTA':
        return redirect('menu_estoquista')
    return redirect('logout_usuario')