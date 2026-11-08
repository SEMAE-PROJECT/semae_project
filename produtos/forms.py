from django import forms
from .models import TipoProduto, Lote, ItemPedido, ItemEspecial

class TipoProdutoForm(forms.ModelForm):
    class Meta:
        model = TipoProduto
        fields = [
            'nome', 
            'tipo', 
            'unidade_medida',
            'origem_compra', 
            'possui_data_fabricacao', 
            'possui_data_validade'
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Arroz Agulhinha Tipo 1'}),
            'tipo': forms.Select(attrs={'class': 'form-control'}),
            'unidade_medida': forms.Select(attrs={'class': 'form-control', 'id': 'id_unidade_medida'}),
            'origem_compra': forms.Select(attrs={'class': 'form-control'}),
            'possui_data_fabricacao': forms.CheckboxInput(attrs={'id': 'id_possui_data_fabricacao'}),
            'possui_data_validade': forms.CheckboxInput(attrs={'id': 'id_possui_data_validade'}),
        }

class Loteform(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.tipo_produto = kwargs.pop('tipo_produto', None)
        super().__init__(*args, **kwargs)
        
        if self.tipo_produto and not self.tipo_produto.possui_data_fabricacao:
            self.fields['data_fabricacao'].required = False
            
        if self.tipo_produto and not self.tipo_produto.possui_data_validade:
            self.fields['data_validade'].required = False

    class Meta:
        model = Lote
        fields = [
            'quantidade_pacotes',
            'preco_unitario',
            'data_fabricacao',
            'data_validade',
            'observacoes'
        ]
        widgets = {
            'quantidade_pacotes': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'placeholder': 'Ex: 50'}),
            'preco_unitario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': '0,00'}),
            'data_fabricacao': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'data_validade': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Marca, fornecedor ou observações do lote...'}),
        }

class AdicionarEstoqueForm(forms.Form):
    quantidade_pacotes = forms.IntegerField(
        label='Quantidade a adicionar',
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 10'})
    )

class BaixaEstoqueForm(forms.Form):
    quantidade_pacotes = forms.IntegerField(
        label='Quantidade a dar baixa',
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 5'})
    )

class ItemPedidoForm(forms.ModelForm):
    produto = forms.ModelChoiceField(
        queryset=TipoProduto.objects.filter(ativo=True),
        label="Selecione o Produto",
        empty_label="--- Escolha um produto do estoque ---",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    class Meta:
        model = ItemPedido
        fields = ['produto', 'quantidade']
        widgets = {
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': 'Ex: 5'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['produto'].label_from_instance = (
            lambda obj: f"{obj.nome} — Disponível: {getattr(obj, 'total_estoque', 0)} {obj.unidade_medida if obj.unidade_medida != 'NA' else 'UN'}"
        )

class ItemEspecialForm(forms.ModelForm):
    def __init__(self, *args, categoria=None, **kwargs):
        super().__init__(*args, **kwargs)
        if categoria == 'ESCOLAR':
            self.fields['descricao'].widget.attrs['placeholder'] = 'Ex: Cartolina Guache, Globo Terrestre, Grampeador...'
            self.fields['unidade'].widget.attrs['placeholder'] = 'Ex: Unid, Cx, Pct, Kit'
            self.fields['quantidade'].widget.attrs['placeholder'] = 'Ex: 10'
        else:
            self.fields['descricao'].widget.attrs['placeholder'] = 'Ex: Peito de Frango, Hortifruti, Desinfetante...'
            self.fields['unidade'].widget.attrs['placeholder'] = 'Ex: Kg, Pct, Cx, L'
            self.fields['quantidade'].widget.attrs['placeholder'] = 'Ex: 15.5'

    class Meta:
        model = ItemEspecial
        fields = ['descricao', 'unidade', 'quantidade']
        widgets = {
            'descricao': forms.TextInput(attrs={'class': 'form-control'}),
            'unidade': forms.TextInput(attrs={'class': 'form-control'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'})
        }