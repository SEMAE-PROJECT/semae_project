from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from .forms import TipoProdutoForm, ItemPedidoForm, Loteform, AdicionarEstoqueForm, BaixaEstoqueForm, ItemEspecialForm
from usuarios.views import is_nutricionista, is_estoquista, pode_ver_estoque
from .models import Pedido, ItemPedido, TipoProduto, Lote, Usuario, ItemEspecial
from django.db import transaction
from django.db.models import Q, F, Sum, IntegerField, OuterRef, Subquery, DecimalField, Case, When
from django.db.models.functions import Coalesce
from django.contrib import messages
from datetime import date, datetime, timedelta
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

import openpyxl
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

from django.contrib import messages
from django.shortcuts import redirect

@login_required
@user_passes_test(pode_ver_estoque)
def listar_tipos_produto(request):
    tipos_produto = TipoProduto.objects.annotate(
        total_estoque=Coalesce(Sum('lotes__quantidade_pacotes'), 0, output_field=IntegerField()),
        total_lotes=Coalesce(
            Sum(
                Case(
                    When(lotes__quantidade_pacotes__gt=0, then=1),
                    default=0,
                    output_field=IntegerField()
                )
            ), 0
        )
    )

    busca = request.GET.get('buscar', '').strip()
    if busca:
        tipos_produto = tipos_produto.filter(nome__icontains=busca)

    tipo = request.GET.get('tipo', 'TODOS')
    if tipo and tipo != 'TODOS':
        tipos_produto = tipos_produto.filter(tipo=tipo)

    ativo = request.GET.get('ativo', 'True')
    if ativo == 'False':
        tipos_produto = tipos_produto.filter(ativo=False)
    else:
        tipos_produto = tipos_produto.filter(ativo=True)

    ordem = request.GET.get('ordem', 'nome')
    if ordem == 'estoque_asc':
        tipos_produto = tipos_produto.order_by('total_estoque', 'nome')
    elif ordem == 'estoque_desc':
        tipos_produto = tipos_produto.order_by('-total_estoque', 'nome')
    else:
        tipos_produto = tipos_produto.order_by('nome')

    return render(request, 'produtos/listar_tipos.html', {
        'tipos_produto': tipos_produto,
        'tipos': TipoProduto.PRODUTO_TIPO,
        'busca': busca,
        'tipo_selecionado': tipo,
        'ordem': ordem,
        'ativo': ativo,
    })

@login_required
@user_passes_test(is_estoquista)
def cadastrar_tipo_produto(request):
    if request.method == 'POST':
        form = TipoProdutoForm(request.POST)
        lote_form = Loteform(request.POST)

        if form.is_valid():
            with transaction.atomic():
                produto = form.save()
                qtd_inicial = request.POST.get('quantidade_pacotes')

                # Só cria lote inicial se o estoquista informou quantidade > 0
                if qtd_inicial and int(qtd_inicial) > 0:
                    lote_form = Loteform(request.POST, tipo_produto=produto)
                    if lote_form.is_valid():
                        lote = lote_form.save(commit=False)
                        lote.tipo_produto = produto
                        lote.save()
                        messages.success(request, f"Produto '{produto.nome}' e lote inicial (#{lote.id}) cadastrados com sucesso!")
                        return redirect('listar_tipos_produto')
                    else:
                        # Cancela a transação e exibe os erros do lote na tela
                        transaction.set_rollback(True)
                else:
                    messages.success(request, f"Produto '{produto.nome}' cadastrado no catálogo (sem lote inicial).")
                    return redirect('listar_tipos_produto')
    else:
        form = TipoProdutoForm()
        lote_form = Loteform()

    return render(request, 'produtos/cadastrar_tipo.html', {'form': form, 'lote_form': lote_form})

@login_required
@user_passes_test(pode_ver_estoque)
def listar_lotes(request, tipo_produto_id):
    tipo_produto = get_object_or_404(TipoProduto, pk=tipo_produto_id)
    lotes = Lote.objects.filter(tipo_produto=tipo_produto).order_by(F('data_validade').asc(nulls_last=True), 'id')

    hoje = date.today()
    alerta_dias = 30

    total_pacotes = 0
    total_volume = 0
    lotes_vencidos = 0

    for lote in lotes:
        total_pacotes += lote.quantidade_pacotes
        total_volume += lote.quantidade_total_unidade

        if lote.data_validade is None:
            lote.alerta_classe = 'lote-sem-validade'
            lote.status_validade = 'Sem Validade'
        elif lote.data_validade < hoje:
            lote.alerta_classe = 'lote-vencido'
            lote.status_validade = 'Vencido'
            if lote.quantidade_pacotes > 0:
                lotes_vencidos += 1
        elif lote.data_validade <= hoje + timedelta(days=alerta_dias):
            lote.alerta_classe = 'lote-proximo-vencimento'
            dias_restantes = (lote.data_validade - hoje).days
            lote.status_validade = f'Vence em {dias_restantes} d'
        else:
            lote.alerta_classe = 'lote-ok'
            lote.status_validade = 'Regular'

    context = {
        'tipo_produto': tipo_produto,
        'lotes': lotes,
        'total_pacotes': total_pacotes,
        'total_volume': total_volume,
        'lotes_vencidos': lotes_vencidos,
    }
    return render(request, 'produtos/listar_lotes.html', context)
    
@login_required
@user_passes_test(is_estoquista)
def cadastrar_lote(request, tipo_produto_id):
    tipo_produto = get_object_or_404(TipoProduto, id=tipo_produto_id)

    if request.method == 'POST':
        form = Loteform(request.POST, tipo_produto=tipo_produto)
        if form.is_valid():
            lote = form.save(commit=False)
            lote.tipo_produto = tipo_produto 
            lote.save()
            return redirect('listar_lotes', tipo_produto_id=tipo_produto.id)
    else:
        form = Loteform(tipo_produto=tipo_produto)
    
    context = {
        'form': form,
        'tipo_produto': tipo_produto,
    }
    return render(request, 'produtos/cadastrar_lote.html', context)

@login_required
@user_passes_test(is_estoquista)
def editar_tipo_produto(request, tipo_produto_id):
    tipo_produto = get_object_or_404(TipoProduto, pk=tipo_produto_id)
    
    if request.method == 'POST':
        form = TipoProdutoForm(request.POST, instance=tipo_produto)
        if form.is_valid():
            form.save()
            return redirect('listar_tipos_produto')
    else:
        form = TipoProdutoForm(instance=tipo_produto)
        
    return render(request, 'produtos/cadastrar_tipo.html', {
        'form': form, 
        'editar': True
    })
    
@login_required
@user_passes_test(is_estoquista)
def excluir_tipo_produto(request, tipo_produto_id):
    tipo_produto = get_object_or_404(TipoProduto, pk=tipo_produto_id)
    
    if request.method == 'POST':
        tipo_produto.ativo = False
        tipo_produto.save()
        messages.success(request, f"Produto '{tipo_produto.nome}' foi arquivado com sucesso.")
        return redirect('listar_tipos_produto')

    return render(request, 'produtos/excluir_tipo.html', {'tipo_produto': tipo_produto}) 

@login_required
@user_passes_test(is_estoquista)
def reativar_tipo_produto(request, tipo_produto_id):
    tipo_produto = get_object_or_404(TipoProduto, pk=tipo_produto_id)
    
    if request.method == 'POST':
        tipo_produto.ativo = True
        tipo_produto.save()
        messages.success(request, f"Produto '{tipo_produto.nome}' foi reativado com sucesso.")
        return redirect('listar_tipos_produto')
    
    return render(request, 'produtos/reativar_tipo.html', {'tipo_produto': tipo_produto})

@login_required
@user_passes_test(is_estoquista)
def adicionar_estoque(request, lote_id):
    lote = get_object_or_404(Lote, pk=lote_id)
    
    if request.method == 'POST':
        form = AdicionarEstoqueForm(request.POST) 
        
        if form.is_valid():
            novos_pacotes = form.cleaned_data['quantidade_pacotes'] 
            lote.quantidade_pacotes += novos_pacotes
            lote.save()
            
            return redirect('listar_lotes', tipo_produto_id=lote.tipo_produto.id)
    else:
        form = AdicionarEstoqueForm()
    
    return render(request, 'produtos/adicionar_estoque.html', {'form': form, 'lote': lote}) 

@login_required
@user_passes_test(is_estoquista)
def baixar_estoque(request, lote_id):
    lote = get_object_or_404(Lote, pk=lote_id)
    
    if request.method == 'POST':
        form = BaixaEstoqueForm(request.POST) 
        
        if form.is_valid():
            quantidade_remover = form.cleaned_data['quantidade_pacotes']
            
            if quantidade_remover > lote.quantidade_pacotes:
                form.add_error('quantidade_pacotes', "Não há unidades suficientes no estoque.")
            else:
                lote.quantidade_pacotes -= quantidade_remover
                lote.save()
                return redirect('listar_lotes', tipo_produto_id=lote.tipo_produto.id)   
    else:      
        form = BaixaEstoqueForm() 
    
    return render(request, 'produtos/baixar_estoque.html', {
        'lote': lote,
        'form': form, 
    })

@login_required
@user_passes_test(is_estoquista)
def editar_lote(request, lote_id):
    lote = get_object_or_404(Lote, pk=lote_id)
    
    if request.method == 'POST':
        form = Loteform(request.POST, instance=lote)
        if form.is_valid():
            form.save()
            return redirect('listar_lotes', tipo_produto_id=lote.tipo_produto.id)
    else:
        form = Loteform(instance=lote)
        
    return render(request, 'produtos/cadastrar_lote.html', {
        'form': form, 
        'editar': True,
        'lote': lote,
        'tipo_produto': lote.tipo_produto,
    })

@login_required
@user_passes_test(is_estoquista)
def excluir_lote(request, lote_id):
    lote = get_object_or_404(Lote, pk=lote_id)
    
    if request.method == 'POST':
        lote.delete()
        return redirect('listar_lotes', tipo_produto_id=lote.tipo_produto.id)
    
    return render(request, 'produtos/excluir_lote.html', {'lote': lote})

def exportar_excel(dados, mes, ano, usuario, total_pedidos, total_pedidos_carne, lista_detalhada_carne):
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Relatório de Consumo"

    ws['A1'] = f"Balanço de Consumo por Unidade: {usuario}"
    ws['A1'].font = Font(bold=True, size=14)
    
    mes_str = f"{mes}/{ano}" if mes != '0' else f"Anual {ano}"
    ws['A2'] = f"Referência: {mes_str}"
    ws['A3'] = f"Total de Pedidos: {total_pedidos}"
    ws['A4'] = f"Pedidos com Carne: {total_pedidos_carne}"

    headers = ['Produto', 'Unidade', 'Qtd Total', 'Preço Unit. (R$)', 'Subtotal (R$)']
    header_fill = PatternFill(start_color="FFDDDDDD", end_color="FFDDDDDD", fill_type="solid")
    
    for col_num, header_title in enumerate(headers, 1):
        cell = ws.cell(row=6, column=col_num)
        cell.value = header_title
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')
        cell.fill = header_fill

    row_num = 7
    investimento_total = 0

    for item in dados:
        v_unit = float(item.get('preco_unitario_medio', 0) or 0)
        v_total = float(item.get('valor_total_produto', 0) or 0)
        investimento_total += v_total

        ws.cell(row=row_num, column=1).value = item['produto__nome']
        ws.cell(row=row_num, column=2).value = item['produto__unidade_medida']
        ws.cell(row=row_num, column=3).value = item['total_solicitado']
        ws.cell(row=row_num, column=4).value = float(v_unit)
        ws.cell(row=row_num, column=5).value = float(v_total)
        
        ws.cell(row=row_num, column=1).value = item['produto__nome']
        ws.cell(row=row_num, column=2).value = item['produto__unidade_medida']
        ws.cell(row=row_num, column=2).alignment = Alignment(horizontal='center')
        
        ws.cell(row=row_num, column=3).value = item['total_solicitado']
        ws.cell(row=row_num, column=3).alignment = Alignment(horizontal='center')
        
        # Colunas de Dinheiro
        c_unit = ws.cell(row=row_num, column=4)
        c_unit.value = v_unit
        c_unit.number_format = '#,##0.00' 

        c_total = ws.cell(row=row_num, column=5)
        c_total.value = v_total
        c_total.number_format = '#,##0.00'
        
        row_num += 1

    row_num += 1
    ws.cell(row=row_num, column=4).value = "INVESTIMENTO TOTAL:"
    ws.cell(row=row_num, column=4).font = Font(bold=True)
    ws.cell(row=row_num, column=4).alignment = Alignment(horizontal='right')
    
    total_cell = ws.cell(row=row_num, column=5)
    total_cell.value = investimento_total
    total_cell.font = Font(bold=True)
    total_cell.number_format = 'R$ #,##0.00' 

    if lista_detalhada_carne:
        row_num += 3
        ws.cell(row=row_num, column=1).value = "Detalhamento: Observações de Proteína (Carne)"
        ws.cell(row=row_num, column=1).font = Font(bold=True, underline="single", color="990000")
        
        row_num += 1
        for obs in lista_detalhada_carne:
            if obs:
                ws.cell(row=row_num, column=1).value = f"• {obs}"
                ws.merge_cells(start_row=row_num, start_column=1, end_row=row_num, end_column=5)
                row_num += 1

    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except: pass
        ws.column_dimensions[column].width = max_length + 3

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    filename = f"relatorio_consumo_{usuario}_{mes if mes else 'anual'}_{ano}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    
    return response



def exportar_pdf(dados, mes, ano, usuario, total_pedidos, total_pedidos_carne, lista_detalhada_carne, grafico=None):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=relatorio_consumo_{usuario}_{mes}_{ano}.pdf'
    
    p = canvas.Canvas(response, pagesize=A4)
    p.setTitle(f"Relátorio_de_consumo_{usuario}_{mes}/{ano}")
    width, height = A4
    
    mes_int = int(mes) if mes else 0
    titulo_periodo = f"{mes}/{ano}" if mes_int > 0 else f"Anual {ano}"
    
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, 800, "Balanço de Consumo por Unidade") 
    p.setFont("Helvetica", 11)
    p.drawString(50, 777, f"Unidade Solicitante: {usuario}")
    p.drawString(50, 760, f"Referência: {titulo_periodo}")
    
    p.setStrokeColor(colors.black)
    p.rect(50, 690, 500, 60, stroke=1, fill=0) 
    
    p.setFont("Helvetica-Bold", 11)
    p.drawString(60, 730, f"Total de Pedidos Realizados: {total_pedidos}")
    
    p.setFillColor(colors.dodgerblue)
    p.drawString(60, 707, f"Pedidos contendo Proteína (Carne): {total_pedidos_carne}")
    p.setFillColor(colors.black)
    
    y = 660
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y, "Produto")
    p.drawString(280, y, "Unid")
    p.drawString(330, y, "Qtd")
    p.drawString(390, y, "V. Unit (R$)") 
    p.drawString(480, y, "Total (R$)")   
    
    p.setStrokeColor(colors.lightgrey)
    p.line(50, y-5, 550, y-5)
    
    y -= 25
    p.setFont("Helvetica", 10)
    
    valor_geral_relatorio = 0 

    for item in dados:
        p.drawString(50, y, item['produto__nome'][:40])
        
        p.drawString(280, y, item['produto__unidade_medida'])
        
        p.drawString(330, y, f"{item['total_solicitado']:,}")
        
        v_unit = item.get('preco_unitario_medio', 0) or 0
        p.drawString(390, y, f"{v_unit:,.2f}")
        
        v_total = item.get('valor_total_produto', 0) or 0
        p.drawString(480, y, f"{v_total:,.2f}")
        
        valor_geral_relatorio += float(v_total)
        
        y -= 20
        
        if y < 80:
            p.showPage()
            y = 800
            p.setFont("Helvetica-Bold", 11)
            p.drawString(50, y, "Produto (cont.)")
            p.drawString(280, y, "Unid")
            p.drawString(330, y, "Qtd")
            p.drawString(390, y, "V. Unit")
            p.drawString(480, y, "Total")
            y -= 25
            p.setFont("Helvetica", 10)

    p.setStrokeColor(colors.black)
    p.line(350, y, 550, y)
    y -= 15
    p.setFont("Helvetica-Bold", 10)
    p.drawString(365, y, "INVESTIMENTO TOTAL:")
    p.drawString(490, y, f"R$ {valor_geral_relatorio:,.2f}")

    if total_pedidos_carne > 0:
        if y < 150: 
            p.showPage()
            y = 800
        
        y -= 40
        p.setFillColor(colors.darkred)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, "Detalhamento: Observações de Proteína (Carne)")
        p.setFillColor(colors.black)
        p.line(50, y-5, 330, y-5)
        
        y -= 20
        p.setFont("Helvetica-Oblique", 9)
        for texto_carne in lista_detalhada_carne:
            if texto_carne: 
                texto_formatado = f"• {texto_carne[:110]}" 
                p.drawString(60, y, texto_formatado)
                y -= 15
                if y < 60:
                    p.showPage()
                    y = 800
    
    if grafico:
        img = ImageReader(grafico)
        altura_grafico = 160
        
        if y < 180:
            p.showPage()
            y = 800
            p.setFont("Helvetica-Bold", 12)
            p.drawString(50, y, "Análise de Investimento (Cont.)")
            y -= 30
        else:
            y -= 40

        p.drawImage(img, 50, y - altura_grafico, width=480, height=altura_grafico, preserveAspectRatio=True)
        y -= (altura_grafico + 20)
    
    p.save()
    return response



# Apenas secretário pode filtrar relatórios
@login_required
@user_passes_test(lambda u: u.is_secretario())
def filtros_relatorio_mensal(request):
    ano_atual = datetime.now().year
    anos_disponiveis = range(2026, ano_atual + 1)
    
    meses_lista = [
        ('0', 'Anual'), ('1', 'Janeiro'), ('2', 'Fevereiro'), ('3', 'Março'),
        ('4', 'Abril'), ('5', 'Maio'), ('6', 'Junho'), ('7', 'Julho'),
        ('8', 'Agosto'), ('9', 'Setembro'), ('10', 'Outubro'), ('11', 'Novembro'), ('12', 'Dezembro')
    ]
    
    diretores = Usuario.objects.filter(cargo='DIRETOR')

    context = {
        'anos': anos_disponiveis,
        'ano_atual': ano_atual,
        'meses': meses_lista,
        'diretores': diretores,
    }
    return render(request, 'produtos/filtros_relatorio.html', context)
    
    
    
def exportar_excel_origemProdutos(produtos_agri, produtos_comum, total_geral, total_agri, total_comum, porcentagem, mes, ano):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Balanço de Compras"

    estilo_titulo = Font(bold=True, size=14)
    estilo_cabecalho = Font(bold=True, color="FFFFFF")
    preenchimento_azul = PatternFill(start_color="FF1E90FF", end_color="FF1E90FF", fill_type="solid")
    preenchimento_verde = PatternFill(start_color="FF228B22", end_color="FF228B22", fill_type="solid")
    alinhamento_centro = Alignment(horizontal="center")
    borda_fina = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

    ws['A1'] = "Balanço de Compras: Origem Produto"
    ws['A1'].font = estilo_titulo
    ws['A2'] = f"Referência: {mes}/{ano}"
    
    ws['A4'] = "CATEGORIA"
    ws['B4'] = "PORCENTAGEM (%)"
    ws['C4'] = "TOTAL INVESTIDO (R$)"
    for cell in ws[4]: 
        cell.font = Font(bold=True)
        cell.border = borda_fina

    ws.append(["Compra Comum", f"{round((total_comum/total_geral*100), 2) if total_geral > 0 else 0}%", total_comum])
    ws.append(["Agricultura Familiar", f"{porcentagem}%", total_agri])
    ws.append(["GASTO TOTAL", "100%", total_geral])
    ws[ws.max_row][0].font = Font(bold=True)

    ws.append([]) 
    ws.append(["DETALHAMENTO: COMPRA COMUM"])
    ws[ws.max_row][0].font = Font(bold=True, color="1E90FF")
    
    colunas = ["Produto", "Qtd", "Unid", "Subtotal (R$)"]
    ws.append(colunas)
    for cell in ws[ws.max_row]:
        cell.fill = preenchimento_azul
        cell.font = estilo_cabecalho
        cell.alignment = alinhamento_centro

    for item in produtos_comum:
        ws.append([item['tipo_produto__nome'], item['qtd'], item['tipo_produto__unidade_medida'], item['subtotal'] or 0])

    ws.append([])
    ws.append(["DETALHAMENTO: AGRICULTURA FAMILIAR"])
    ws[ws.max_row][0].font = Font(bold=True, color="228B22")
    
    ws.append(colunas)
    for cell in ws[ws.max_row]:
        cell.fill = preenchimento_verde
        cell.font = estilo_cabecalho
        cell.alignment = alinhamento_centro

    for item in produtos_agri:
        ws.append([item['tipo_produto__nome'], item['qtd'], item['tipo_produto__unidade_medida'], item['subtotal'] or 0])

    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except: pass
        ws.column_dimensions[column].width = max_length + 2

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=relatorio_compras_{mes}_{ano}.xlsx'
    wb.save(response)
    return response 
    
    
    
def exportar_excel_tipos(dados, total_valor, total_produtos, total_lotes, mes, ano):
    wb = openpyxl.Workbook()
    
    ws_resumo = wb.active
    ws_resumo.title = "Resumo por Categoria"
    ws_resumo.append(["Balanço por Categoria", f"{mes}/{ano}"])
    ws_resumo.append(["Total de Produtos", total_produtos])
    ws_resumo.append(["Total de Itens", total_lotes])
    ws_resumo.append(["Investimento Total", total_valor])
    
    categorias_config = [
        ('ALIMENTO', 'Alimentos', "228B22"),   
        ('LIMPEZA', 'Limpeza', "1E90FF"),      
        ('ESCOLAR', 'Escolar', "FF8C00"),      
        ('OUTROS', 'Outros', "808080"),       
    ]

    for chave, label, cor_hex in categorias_config:
        info = dados[chave]
        if info['lista']:
            ws = wb.create_sheet(title=label)
            ws.sheet_properties.tabColor = cor_hex
            
            ws.append([f"DETALHAMENTO: {label.upper()}"])
            ws.append(["Produto", "Quantidade", "Unidade", "Subtotal (R$)"])
            
            for item in info['lista']:
                ws.append([
                    item['tipo_produto__nome'], 
                    item['qtd'], 
                    item['tipo_produto__unidade_medida'], 
                    item['subtotal']
                ])
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=relatorio_categorias_{mes}_{ano}.xlsx'
    wb.save(response)
    return response  
    


def exportar_pdf_origemProdutos(produtos_agri, produtos_comum, total_geral, total_agri, total_comum, porcentagem, mes, ano):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=relatorio_produtos_{mes}_{ano}.pdf'
    
    p = canvas.Canvas(response, pagesize=A4)
    p.setTitle(f"relatório_origem_produtos_{mes}/{ano}")
    titulo_periodo = f"{mes}/{ano}" if mes > 0 else f"Anual {ano}"
    
    porcentagem_comum = round((total_comum / total_geral * 100), 2) if total_geral > 0 else 0
    
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, "Balanço de Compras: Origem Produto")
    p.setFont("Helvetica", 12)
    p.drawString(100, 775, f"Referência: {titulo_periodo}")
    
    p.setStrokeColor(colors.dodgerblue)
    p.rect(100, 705, 400, 60, stroke=1, fill=0) 
    
    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(colors.dodgerblue)
    p.drawString(120, 740, f"Índice de Compra Comum: {porcentagem_comum}%")
    
    p.setFont("Helvetica", 10)
    p.setFillColor(colors.black)
    p.drawString(120, 720, f"Gasto no Mercado/Atacado: R$ {total_comum:,.2f}")
    
    cor_meta = colors.green if porcentagem >= 15 else colors.red
    p.setStrokeColor(cor_meta)
    p.rect(100, 620, 400, 75, stroke=1, fill=0) 
    
    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(cor_meta)
    p.drawString(120, 675, f"Índice de Agricultura Familiar: {porcentagem}%")
    
    p.setFont("Helvetica", 10)
    p.setFillColor(colors.black)
    p.drawString(120, 655, f"Gasto com produto de Agricultura: R$ {total_agri:,.2f}")
    
    if porcentagem < 15:
        p.setFont("Helvetica-Oblique", 9)
        p.setFillColor(colors.red)
        p.drawString(120, 635, "* Atenção: Abaixo do limite legal de 15%")
    
    p.setFont("Helvetica-Bold", 11)
    p.drawCentredString(300, 595, f"GASTO TOTAL EM ALIMENTOS: R$ {total_geral:,.2f}")
    
    y = 565 
    
    def desenhar_cabecalho_tabela(y_pos, titulo, cor):
        p.setFillColor(cor)
        p.setFont("Helvetica-Bold", 11)
        p.drawString(100, y_pos, titulo)
        y_pos -= 20
        p.setFillColor(colors.black)
        p.drawString(100, y_pos, "Produto")
        p.drawString(300, y_pos, "Qtd")
        p.drawString(380, y_pos, "Unid")
        p.drawString(450, y_pos, "Subtotal (R$)")
        return y_pos - 15

    y = desenhar_cabecalho_tabela(y, "Detalhe: Compra Comum", colors.dodgerblue)
    p.setFont("Helvetica", 10)
    for item in produtos_comum:
        p.drawString(100, y, item['tipo_produto__nome'][:30])
        p.drawString(300, y, str(item['qtd']))
        p.drawString(380, y, item['tipo_produto__unidade_medida'])
        subtotal = item['subtotal'] or 0
        p.drawString(450, y, f"{subtotal:,.2f}")
        y -= 15
        if y < 60: p.showPage(); y = 800
        
    y -= 30 # Garante que as tabelas não enconstem uma na outra
    
    y = desenhar_cabecalho_tabela(y, "Detalhe: Agricultura Familiar", colors.green)
    p.setFont("Helvetica", 10)
    for item in produtos_agri:
        p.drawString(100, y, item['tipo_produto__nome'][:30])
        p.drawString(300, y, str(item['qtd']))
        p.drawString(380, y, item['tipo_produto__unidade_medida'])
        subtotal = item['subtotal'] or 0
        p.drawString(450, y, f"{subtotal:,.2f}")
        y -= 15
        if y < 60: p.showPage(); y = 800

    p.save()
    return response



def exportar_pdf_tipos(dados, total_valor, total_lotes, total_produtos, mes, ano):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=relatorio_tipos_{mes}_{ano}.pdf'
    p = canvas.Canvas(response, pagesize=A4)
    p.setTitle(f"Relatório_tipos_produtos_{mes}/{ano}")
    
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 810, "Balanço de Compras por Categoria")
    p.setFont("Helvetica", 12)
    p.drawString(100, 787, f"Referência: {mes}/{ano} | Total Geral: R$ {total_valor:,.2f}")

    p.setStrokeColor(colors.black)
    p.rect(100, 710, 400, 65, stroke=1, fill=0)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(110, 760, f"Total de Produtos Cadastrados: {total_produtos}")
    p.drawString(110, 740, f"Total de Lotes Cadastrados (Todos os tipos): {total_lotes}")
    p.drawString(110, 720, f"Investimento Total no Período: R$ {total_valor:,.2f}")

    y = 680
    categorias_config = [
        ('ALIMENTO', 'Alimentos', colors.green),
        ('LIMPEZA', 'Materiais de Limpeza', colors.dodgerblue),
        ('ESCOLAR', 'Materiais Escolares', colors.orange),
        ('OUTROS', 'Outros/Diversos', colors.grey),
    ]

    for chave, label, cor in categorias_config:
        info = dados[chave]
        if info['lista']:
            p.setFillColor(cor)
            p.setFont("Helvetica-Bold", 12)
            p.drawString(100, y, f"Tipo: {label} (Total: R$ {info['valor']:,.2f})")
            y -= 20
            
            p.setFillColor(colors.black)
            p.setFont("Helvetica-Bold", 10)
            p.drawString(100, y, "Produto")
            p.drawString(300, y, "Qtd")
            p.drawString(450, y, "Subtotal")
            y -= 15
            
            p.setFont("Helvetica", 9)
            for item in info['lista']:
                p.drawString(100, y, item['tipo_produto__nome'][:35])
                p.drawString(300, y, f"{item['qtd']} {item['tipo_produto__unidade_medida']}")
                subtotal = item['subtotal'] or 0
                p.drawString(450, y, f"R$ {subtotal:,.2f}")
                y -= 15
                if y < 60:
                    p.showPage()
                    y = 800
            y -= 20 

    p.save()
    return response



# Apenas secretário pode gerar relatório de consumo
@login_required
@user_passes_test(lambda u: u.is_secretario())
def gerar_relatorio_mensal(request):
    mes = request.GET.get('mes')
    ano = request.GET.get('ano')
    diretor_id = request.GET.get('diretor')
    formato = request.GET.get('formato')

    filtros_pedidos = {
        'data_pedido__year': ano,
        'status__in': ['PENDENTE', 'APROVADO', 'ENTREGUE']
    }
    filtros_itens = {
        'pedido__data_pedido__year': ano,
        'pedido__status__in': ['PENDENTE', 'APROVADO', 'ENTREGUE']
    }

    if mes and mes != '0':
        filtros_pedidos['data_pedido__month'] = mes
        filtros_itens['pedido__data_pedido__month'] = mes

    nome_diretor = "Todas as Escolas"
    if diretor_id and diretor_id != 'todos':
        filtros_pedidos['solicitante_id'] = diretor_id
        filtros_itens['pedido__solicitante_id'] = diretor_id

        diretor_obj = get_object_or_404(Usuario, id=diretor_id)
        if hasattr(diretor_obj, 'escola') and diretor_obj.escola:
            nome_diretor = diretor_obj.escola.nome_escola
        else:
            nome_diretor = diretor_obj.username

    pedidos_no_periodo = Pedido.objects.filter(**filtros_pedidos)
    total_pedidos = pedidos_no_periodo.count()

    # CORREÇÃO: Usa ItemEspecial em vez do campo antigo observacao_carne
    pedidos_especiais = pedidos_no_periodo.filter(
        itens_especiais__isnull=False
    ).select_related('solicitante', 'solicitante__escola').prefetch_related('itens_especiais').distinct()
    
    total_pedidos_carne = pedidos_especiais.count()
    is_todas_escolas = (diretor_id == 'todos' or not diretor_id)

    lista_detalhada_carne = []
    for p in pedidos_especiais:
        resumo_itens = ", ".join([f"{ie.quantidade} {ie.unidade} de {ie.descricao}" for ie in p.itens_especiais.all()])
        if is_todas_escolas:
            nome_exibicao = p.solicitante.escola.nome_escola if hasattr(p.solicitante, 'escola') else p.solicitante.username
            lista_detalhada_carne.append(f"{nome_exibicao}: {resumo_itens}")
        else:
            lista_detalhada_carne.append(resumo_itens)

    preco_real_subquery = Lote.objects.filter(
        tipo_produto_id=OuterRef('produto_id')
    ).order_by('-id').values('preco_unitario')[:1]

    dados_raw = ItemPedido.objects.filter(**filtros_itens).values(
        'produto__nome',
        'produto__unidade_medida',
        'produto_id'
    ).annotate(
        total_solicitado=Sum('quantidade'),
        valor_total_produto=Sum(
            F('quantidade') * Coalesce(Subquery(preco_real_subquery), 0, output_field=DecimalField()),
            output_field=DecimalField(max_digits=10, decimal_places=2)
        )
    ).order_by('produto__nome')

    dados = []
    for item in dados_raw:
        qtd = item.get('total_solicitado') or 0
        total_rs = item.get('valor_total_produto') or 0
        dados.append({
            'produto__nome': item['produto__nome'],
            'produto__unidade_medida': item['produto__unidade_medida'],
            'total_solicitado': qtd,
            'preco_unitario_medio': float(total_rs / qtd) if qtd > 0 else 0,
            'valor_total_produto': float(total_rs)
        })

    grafico_buffer = None
    if is_todas_escolas:
        dados_grafico = ItemPedido.objects.filter(**filtros_itens).values(
            'pedido__solicitante__username',
            'pedido__solicitante__escola__nome_escola'
        ).annotate(
            total_escola=Sum(
                F('quantidade') * Coalesce(Subquery(preco_real_subquery), 0, output_field=DecimalField()),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        ).order_by('-total_escola')

        if dados_grafico.exists():
            grafico_buffer = gerar_grafico_consumo_escolas(dados_grafico)

    if formato == 'excel':
        return exportar_excel(dados, mes, ano, nome_diretor, total_pedidos, total_pedidos_carne, lista_detalhada_carne)
    return exportar_pdf(dados, mes, ano, nome_diretor, total_pedidos, total_pedidos_carne, lista_detalhada_carne, grafico_buffer)



def gerar_grafico_consumo_escolas(dados_grafico):
    
    escolas = []
    valores = []
    
    for item in dados_grafico:
        nome_oficial = item.get('pedido__solicitante__escola__nome_escola')
        username = item.get('pedido__solicitante__username')
        
        label = nome_oficial if nome_oficial else username
        escolas.append(label)
        valores.append(float(item['total_escola'] or 0))
    
    total_periodo = sum(valores) if sum(valores) > 0 else 1

    fig, ax = plt.subplots(figsize=(10, len(escolas) * 0.5 + 2))
    bars = ax.barh(escolas, valores, color='#1E90FF', height=0.6) 

    for bar in bars:
        largura = bar.get_width()
        porcentagem = (largura / total_periodo) * 100
        
        valor_fmt = f"{largura:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        porcentagem_fmt = f"{porcentagem:.1f}".replace(".", ",")
        
        label_texto = f"R$ {valor_fmt} ({porcentagem_fmt}%)"
        
        ax.text(largura + (total_periodo * 0.02), bar.get_y() + bar.get_height()/2,
                label_texto, va='center', fontweight='bold', fontsize=10, color='#333333') 

    ax.set_title('Divisão de Gastos por Unidade (%)', fontsize=12, pad=15)
    ax.xaxis.set_visible(False)
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    
    ax.invert_yaxis()
    ax.tick_params(axis='y', length=0)

    plt.tight_layout()
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=120)
    plt.close(fig)
    buffer.seek(0)
    return buffer



# Apenas secretário pode gerar relatório de origem
@login_required
@user_passes_test(lambda u: u.is_secretario())
def gerar_relatorio_origem(request):
    mes = int(request.GET.get('mes', 0))
    ano = int(request.GET.get('ano', 2026))
    formato = request.GET.get('formato')

    filtros = {'data_cadastro__year': ano}
    if mes > 0:
        filtros['data_cadastro__month'] = mes

    lotes_base = Lote.objects.filter(tipo_produto__tipo='ALIMENTO', **filtros).select_related('tipo_produto')

    lotes_agri = lotes_base.filter(tipo_produto__origem_compra='AGRICULTURA')
    total_agri = lotes_agri.aggregate(total=Sum(F('quantidade_pacotes') * F('preco_unitario')))['total'] or 0
    
    lotes_comum = lotes_base.filter(tipo_produto__origem_compra='COMUM')
    total_comum = lotes_comum.aggregate(total=Sum(F('quantidade_pacotes') * F('preco_unitario')))['total'] or 0

    total_geral = total_agri + total_comum
    porcentagem = round((total_agri / total_geral * 100), 2) if total_geral > 0 else 0

    produtos_agri = lotes_agri.values('tipo_produto__nome', 'tipo_produto__unidade_medida').annotate(
        qtd=Sum('quantidade_pacotes'), subtotal=Sum(F('quantidade_pacotes') * F('preco_unitario'))
    )
    
    produtos_comum = lotes_comum.values('tipo_produto__nome', 'tipo_produto__unidade_medida').annotate(
        qtd=Sum('quantidade_pacotes'), subtotal=Sum(F('quantidade_pacotes') * F('preco_unitario'))
    )

    if formato == 'pdf':
        return exportar_pdf_origemProdutos(produtos_agri, produtos_comum, total_geral, total_agri, total_comum, porcentagem, mes, ano)
    else:
        return exportar_excel_origemProdutos(produtos_agri, produtos_comum, total_geral, total_agri, total_comum, porcentagem, mes, ano)



# Apenas secretário pode gera relatório de tipo
@login_required
@user_passes_test(lambda u: u.is_secretario())
def gerar_relatorio_tipos(request):
    mes = int(request.GET.get('mes', 0))
    ano = int(request.GET.get('ano', 2026))
    formato = request.GET.get('formato')
    
    filtros = {'data_cadastro__year': ano}
    if mes > 0:
        filtros['data_cadastro__month'] = mes
        
    lotes_base = Lote.objects.filter(**filtros).select_related('tipo_produto')
    total_produtosDistintos = lotes_base.values('tipo_produto').distinct().count()
    total_lotes = lotes_base.count()
    
    def dados_por_tipo(slug_tipo):
        queryset = lotes_base.filter(tipo_produto__tipo=slug_tipo)
        total_valor = queryset.aggregate(total=Sum(F('quantidade_pacotes') * F('preco_unitario')))['total'] or 0
        qtd_itens = queryset.aggregate(total=Sum('quantidade_pacotes'))['total'] or 0
        detalhes = list(queryset.values('tipo_produto__nome', 'tipo_produto__unidade_medida').annotate(
            qtd=Sum('quantidade_pacotes'),
            subtotal=Sum(F('quantidade_pacotes') * F('preco_unitario'))
        ))
        return {'valor': total_valor, 'qtd': qtd_itens, 'detalhes': detalhes, 'lista': detalhes}
    
    dados = {
        'ALIMENTO': dados_por_tipo('ALIMENTO'),
        'LIMPEZA': dados_por_tipo('LIMPEZA'),
        'ESCOLAR': dados_por_tipo('ESCOLAR'),
        'OUTROS': dados_por_tipo('OUTROS')
    }
    
    total_geral_valor = sum(d['valor'] for d in dados.values())
    total_geral_itens = sum(d['qtd'] for d in dados.values())
    total_lotes = lotes_base.count()
    
    if formato == 'pdf':
        return exportar_pdf_tipos(dados, total_geral_valor, total_geral_itens, total_lotes, mes, ano)
    else:
        return exportar_excel_tipos(dados, total_geral_valor, total_geral_itens, total_lotes, mes, ano)



# Apenas diretor pode fazer um pedido
@login_required
def criar_pedido(request):
    # Captura a categoria escolhida no clique do botão (via URL)
    categoria = request.GET.get('categoria')

    # Cria o pedido com a categoria correta se ela for válida
    if categoria in ['ALIMENTICIO_LIMPEZA', 'ESCOLAR']:
        pedido = Pedido.objects.create(
            solicitante=request.user,
            status='PENDENTE',
            categoria=categoria
        )
        return redirect('detalhe_pedido', pedido_id=pedido.id)

    return redirect('meus_pedidos')


# Apenas um diretor pode ver os detalhes do seu pedido
@login_required
@user_passes_test(lambda u: u.is_diretor())
def detalhe_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, solicitante=request.user)
    
    # Filtra os produtos válidos baseado na CATEGORIA do pedido
    if pedido.categoria == 'ESCOLAR':
        produtos_validos = TipoProduto.objects.filter(ativo=True, tipo='ESCOLAR')
    else:
        produtos_validos = TipoProduto.objects.filter(ativo=True, tipo__in=['ALIMENTO', 'LIMPEZA', 'OUTROS'])

    # Soma o estoque e remove os zerados
    produtos_validos = produtos_validos.annotate(
        total_estoque=Coalesce(
            Sum('lotes__quantidade_pacotes'),
            0,
            output_field=IntegerField()
        )
    ).filter(total_estoque__gt=0)
    
    form_comum = ItemPedidoForm()
    form_comum.fields['produto'].queryset = produtos_validos
    form_especial = ItemEspecialForm(categoria=pedido.categoria) # Formulário que criaremos no próximo passo
    
    if request.method == 'POST':
        # Se o formulário enviado for o de Item Comum
        if 'add_item_comum' in request.POST:
            form_comum = ItemPedidoForm(request.POST)
            form_comum.fields['produto'].queryset = produtos_validos
            
            if form_comum.is_valid():
                produto_selecionado = form_comum.cleaned_data['produto']
                quantidade_adicionar = form_comum.cleaned_data['quantidade']
                
                estoque_atual = produtos_validos.get(pk=produto_selecionado.pk).total_estoque
                item_existente = ItemPedido.objects.filter(pedido=pedido, produto=produto_selecionado).first()
                quantidade_existente = item_existente.quantidade if item_existente else 0
                quantidade_final_desejada = quantidade_existente + quantidade_adicionar

                # Validação de Estoque Insuficiente
                if quantidade_final_desejada > estoque_atual:
                    messages.error(request, f"Estoque insuficiente para '{produto_selecionado.nome}'. "
                                            f"Disponível: {estoque_atual}, "
                                            f"Solicitado no total: {quantidade_final_desejada}.")
                else:
                    if item_existente:
                        item_existente.quantidade += quantidade_adicionar
                        item_existente.save()
                        messages.success(request, f"Quantidade de '{produto_selecionado.nome}' atualizada.")
                    else:
                        item = form_comum.save(commit=False)
                        item.pedido = pedido
                        item.save()
                        messages.success(request, f"'{produto_selecionado.nome}' adicionado ao pedido.")
                
                return redirect('detalhe_pedido', pedido_id=pedido.id)

        # Se o formulário enviado for o de Item Especial
        elif 'add_item_especial' in request.POST:
            form_especial = ItemEspecialForm(request.POST, categoria=pedido.categoria)
            if form_especial.is_valid():
                item_esp = form_especial.save(commit=False)
                item_esp.pedido = pedido
                item_esp.save()
                messages.success(request, f"Solicitação especial '{item_esp.descricao}' adicionada.")
                return redirect('detalhe_pedido', pedido_id=pedido.id)
                
    itens_do_pedido = pedido.itens.all()
    itens_especiais = pedido.itens_especiais.all()

    context = {
        'pedido': pedido,
        'itens': itens_do_pedido,
        'itens_especiais': itens_especiais,
        'form': form_comum,
        'form_especial': form_especial,
    }
    return render(request, 'pedidos/detalhe_pedido.html', context)


# Apenas diretor pode remover um item comum de um pedido
@login_required
@user_passes_test(lambda u: u.is_diretor())
def remover_item_pedido(request, item_id):
    item = get_object_or_404(ItemPedido, id=item_id)
    pedido_id = item.pedido.id

    if item.pedido.solicitante == request.user:
        item.delete()
        messages.success(request, "Item removido do pedido.")
        return redirect('detalhe_pedido', pedido_id=pedido_id)
    else:
        return HttpResponseForbidden("Você não tem permissão para remover este item.")



# Nova função: Remover Item Especial
@login_required
@user_passes_test(lambda u: u.is_diretor())
def remover_item_especial(request, item_id):
    item = get_object_or_404(ItemEspecial, id=item_id)
    pedido_id = item.pedido.id

    if item.pedido.solicitante == request.user:
        item.delete()
        messages.success(request, "Solicitação especial removida.")
        return redirect('detalhe_pedido', pedido_id=pedido_id)
    else:
        return HttpResponseForbidden("Você não tem permissão para remover este item.")


# Apenas diretor pode ver seus próprios pedidos
@login_required
@user_passes_test(lambda u: u.is_diretor())
def meus_pedidos(request):
    pedidos_do_diretor = Pedido.objects.filter(
        solicitante=request.user
    ).filter(
        Q(itens__isnull=False) | Q(itens_especiais__isnull=False)
    ).distinct().order_by('-data_pedido')
    
    context = {
        'pedidos': pedidos_do_diretor
    }
    
    return render(request, 'pedidos/meus_pedidos.html', context)


# Apenas diretor pode finalizar um pedido
@login_required
@user_passes_test(lambda u: u.is_diretor())
def finalizar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)
    
    if request.method == 'POST':
        # O campo 'observacao_carne' não existe mais. 
        # Tudo isso é tratado agora pelos Itens Especiais!
        pedido.status = 'PENDENTE' 
        pedido.save()
        messages.success(request, "Pedido finalizado e enviado para aprovação!")
        
        return redirect('meus_pedidos')

    return redirect('detalhe_pedido', pedido_id=pedido.id)

# Apenas diretor pode verificar o estoque disponível
@login_required
@user_passes_test(lambda u: u.is_diretor())
def listar_estoque_disponivel(request):
    produtos = TipoProduto.objects.filter(ativo=True).annotate(
        total_estoque=Coalesce(
            Sum('lotes__quantidade_pacotes'), 
            0,
            output_field=IntegerField()
        )
    ).order_by('nome')
    
    return render(request, 'produtos/estoque_disponivel.html', {'produtos': produtos})


# Apenas diretor pode excluir seu próprio pedido
@login_required
@user_passes_test(lambda u: u.is_diretor())
def excluir_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, solicitante=request.user)

    if request.method == 'POST':
        if pedido.status == 'PENDENTE':
            numero_pedido = pedido.id
            pedido.delete()
            messages.success(request, f"Pedido #{numero_pedido} foi excluído com sucesso.")
        else:
            messages.error(request, f"Este pedido não pode ser excluído pois seu status é '{pedido.get_status_display()}'.")

    return redirect('meus_pedidos')


# Nutricionista e Secretário veem pedidos pendentes (filtrados por categoria)
@login_required
@user_passes_test(lambda u: u.is_nutricionista() or u.is_secretario())
def listar_pedidos_pendentes(request):
    pedidos = Pedido.objects.filter(
        status='PENDENTE'
    ).filter(
        Q(itens__isnull=False) | Q(itens_especiais__isnull=False)
    ).select_related('solicitante__escola').distinct().order_by('data_pedido')
    
    # Filtro de Categoria baseado no Cargo
    if request.user.is_nutricionista():
        pedidos = pedidos.filter(categoria='ALIMENTICIO_LIMPEZA')
    elif request.user.is_secretario():
        pedidos = pedidos.filter(categoria='ESCOLAR')
        
    return render(request, 'pedidos/listar_pedidos_pendentes.html', {'pedidos': pedidos})


# Gestores veem detalhes do pedido
@login_required
@user_passes_test(lambda u: u.is_nutricionista() or u.is_secretario() or u.is_estoquista())
def detalhe_pedido_gestor(request, pedido_id):
    pedido = get_object_or_404(Pedido.objects.select_related('solicitante', 'solicitante__escola'), id=pedido_id)

    if request.user.is_secretario() and pedido.categoria != 'ESCOLAR':
        return HttpResponseForbidden("Apenas a Nutricionista ou Estoquista podem acessar pedidos alimentícios.")
    elif request.user.is_nutricionista() and pedido.categoria != 'ALIMENTICIO_LIMPEZA':
        return HttpResponseForbidden("Apenas a Secretaria ou Estoquista podem acessar pedidos escolares.")

    return render(request, 'pedidos/detalhe_pedido_gestor.html', {'pedido': pedido})


# Gestores aprovam pedido (SEM dar baixa no estoque)
@login_required
@user_passes_test(lambda u: u.is_nutricionista() or u.is_secretario())
def aprovar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)
    
    if pedido.categoria == 'ESCOLAR' and not request.user.is_secretario():
        messages.error(request, "Apenas a Secretaria pode aprovar pedidos de Material Escolar.")
        return redirect('listar_pedidos_pendentes')
    elif pedido.categoria == 'ALIMENTICIO_LIMPEZA' and not request.user.is_nutricionista():
        messages.error(request, "Apenas a Nutricionista pode aprovar pedidos Alimentícios/Limpeza.")
        return redirect('listar_pedidos_pendentes')
        
    if pedido.status != 'PENDENTE':
        messages.error(request, f"O pedido #{pedido.id} não está pendente.")
        return redirect('listar_pedidos_pendentes')
    
    if request.method == 'POST':
        pedido.status = 'APROVADO'
        pedido.save()
        messages.success(request, f"Pedido #{pedido.id} aprovado! Ele foi encaminhado ao Estoquista para separação e envio.")

    return redirect('listar_pedidos_pendentes')


@login_required
@user_passes_test(lambda u: u.is_nutricionista() or u.is_secretario())
def rejeitar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)
    
    if request.method == 'POST':
        motivo = request.POST.get('justificativa')
        pedido.status = 'REJEITADO'
        pedido.justificativa_rejeicao = motivo
        pedido.save()
        messages.success(request, f"Pedido #{pedido.id} rejeitado. Motivo registrado.")
        return redirect('listar_pedidos_pendentes')
    
    return redirect('detalhe_pedido_gestor', pedido_id=pedido.id)


@login_required
@user_passes_test(lambda u: u.is_nutricionista() or u.is_secretario() or u.is_estoquista())
def historico_pedidos(request):
    pedidos_recentes = Pedido.objects.filter(
        status__in=['APROVADO', 'REJEITADO', 'ENTREGUE']
    ).select_related('solicitante__escola').order_by('-data_pedido')

    if request.user.is_nutricionista():
        pedidos_recentes = pedidos_recentes.filter(categoria='ALIMENTICIO_LIMPEZA')
    elif request.user.is_secretario():
        pedidos_recentes = pedidos_recentes.filter(categoria='ESCOLAR')

    return render(request, 'pedidos/historico_pedidos.html', {'pedidos': pedidos_recentes[:50]})


@login_required
@user_passes_test(lambda u: u.is_nutricionista() or u.is_secretario())
def verificar_pedidos_pendentes(request):
    # Ignora rascunhos vazios sem itens
    contagem = Pedido.objects.filter(status='PENDENTE').filter(
        Q(itens__isnull=False) | Q(itens_especiais__isnull=False)
    ).distinct()
    if request.user.is_nutricionista():
        contagem = contagem.filter(categoria='ALIMENTICIO_LIMPEZA')
    elif request.user.is_secretario():
        contagem = contagem.filter(categoria='ESCOLAR')

    return JsonResponse({'count': contagem.count(), 'success': True})

# --- NOVAS VIEWS DO ESTOQUISTA ---

@login_required
@user_passes_test(is_estoquista)
def listar_pedidos_envio(request):
    # O Estoquista vê todos os pedidos APROVADOS (aguardando envio)
    pedidos = Pedido.objects.filter(status='APROVADO').order_by('data_pedido')
    return render(request, 'pedidos/listar_pedidos_envio.html', {'pedidos': pedidos})

@login_required
@user_passes_test(is_estoquista)
def detalhe_pedido_envio(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, status='APROVADO')
    return render(request, 'pedidos/detalhe_pedido_envio.html', {'pedido': pedido})

@login_required
@user_passes_test(is_estoquista)
def despachar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, status='APROVADO')

    if request.method == 'POST':
        itens_estoque_ids = request.POST.getlist('itens_estoque')
        itens_especiais_ids = request.POST.getlist('itens_especiais')

        if not itens_estoque_ids and not itens_especiais_ids:
            messages.warning(request, "Marque pelo menos um item na caixa de seleção para registrar a baixa/entrega.")
            return redirect('detalhe_pedido_envio', pedido_id=pedido.id)

        try:
            with transaction.atomic():
                # 1. Processa apenas os itens de estoque marcados agora e que ainda não foram entregues
                itens_para_baixar = pedido.itens.filter(id__in=itens_estoque_ids, entregue=False)

                if itens_para_baixar.exists():
                    produtos_ids = itens_para_baixar.values_list('produto_id', flat=True)
                    produtos_com_estoque = TipoProduto.objects.filter(id__in=produtos_ids).annotate(
                        estoque_atual=Coalesce(Sum('lotes__quantidade_pacotes'), 0, output_field=IntegerField())
                    )
                    estoque_map = {p.id: p.estoque_atual for p in produtos_com_estoque}

                    for item in itens_para_baixar:
                        if item.quantidade > estoque_map.get(item.produto.id, 0):
                            raise Exception(f"Estoque insuficiente para '{item.produto.nome}' (Disponível: {estoque_map.get(item.produto.id, 0)}).")

                    for item in itens_para_baixar:
                        quantidade_a_baixar = item.quantidade
                        lotes_disponiveis = Lote.objects.filter(
                            tipo_produto=item.produto,
                            quantidade_pacotes__gt=0
                        ).order_by(F('data_validade').asc(nulls_last=True), 'id')

                        for lote in lotes_disponiveis:
                            if quantidade_a_baixar == 0:
                                break
                            if lote.quantidade_pacotes >= quantidade_a_baixar:
                                lote.quantidade_pacotes -= quantidade_a_baixar
                                quantidade_a_baixar = 0
                            else:
                                quantidade_a_baixar -= lote.quantidade_pacotes
                                lote.quantidade_pacotes = 0
                            lote.save()

                        item.entregue = True
                        item.save()

                # 2. Marca os itens especiais selecionados como entregues
                if itens_especiais_ids:
                    pedido.itens_especiais.filter(id__in=itens_especiais_ids, entregue=False).update(entregue=True)

                # 3. Verifica se ainda resta algum item não entregue no pedido
                ainda_faltam_comuns = pedido.itens.filter(entregue=False).exists()
                ainda_faltam_especiais = pedido.itens_especiais.filter(entregue=False).exists()

                if not ainda_faltam_comuns and not ainda_faltam_especiais:
                    pedido.status = 'ENTREGUE'
                    pedido.save()
                    messages.success(request, f"Pedido #{pedido.id} totalmente separado e concluído como Entregue!")
                    return redirect('listar_pedidos_envio')
                else:
                    messages.success(request, "Itens selecionados foram baixados e salvos! O pedido permanece na fila para entrega dos itens restantes.")
                    return redirect('detalhe_pedido_envio', pedido_id=pedido.id)

        except Exception as e:
            messages.error(request, f"Erro ao processar separação do pedido #{pedido.id}: {e}")
            return redirect('detalhe_pedido_envio', pedido_id=pedido.id)

    return redirect('listar_pedidos_envio')