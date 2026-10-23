from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core import validators
from django.conf import settings
import re

class Usuario(AbstractUser):
    
    username_validator = validators.RegexValidator(
        r'^[\w.@+ -]+$',
        'Informe um nome de usuário válido. Este valor pode conter apenas letras, números, espaços e os caracteres @/./+/-/_.'
    )
    
    username = models.CharField(
        max_length=150,
        unique=True,
        help_text='Obrigatório. 150 caracteres ou menos. Letras, números e espaços apenas.',
        validators=[username_validator],
        error_messages={
            'unique': "Um usuário com este nome já existe.",
        },
    )
    
    FUNCOES = (
        ('SECRETARIO', 'Secretário'),
        ('DIRETOR', 'Diretor Escolar'),
        ('NUTRICIONISTA', 'Nutricionista'),
        ('ESTOQUISTA', 'Estoquista'), # Novo perfil adicionado
    )
    
    cargo = models.CharField(max_length=20, choices=FUNCOES)
    
    def is_secretario(self):
        return self.cargo == 'SECRETARIO'
    
    def is_diretor(self):
        return self.cargo == 'DIRETOR'
    
    def is_nutricionista(self):
        return self.cargo == 'NUTRICIONISTA'
        
    def is_estoquista(self):
        return self.cargo == 'ESTOQUISTA'
    

class PerfilEscola(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='escola')
    nome_escola = models.CharField(max_length=200, verbose_name='Nome da Escola')
    
    def __str__(self):
        return self.nome_escola