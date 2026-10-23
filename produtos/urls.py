from django.urls import path
from . import views
from .views import verificar_pedidos_pendentes

urlpatterns = [
    # URLs para Tipos de Produto
    path('', views.listar_tipos_produto, name='listar_tipos_produto'),
    path('novo/', views.cadastrar_tipo_produto, name='cadastrar_tipo_produto'),
    path('editar/<int:tipo_produto_id>/', views.editar_tipo_produto, name='editar_tipo_produto'),
    path('excluir/<int:tipo_produto_id>/', views.excluir_tipo_produto, name='excluir_tipo_produto'),
    path('tipo/<int:tipo_produto_id>/reativar/', views.reativar_tipo_produto, name='reativar_tipo_produto'),

    # URLs para Lotes
    path('lotes/<int:tipo_produto_id>/', views.listar_lotes, name='listar_lotes'),
    path('lotes/<int:tipo_produto_id>/novo/', views.cadastrar_lote, name='cadastrar_lote'),
    path('lotes/editar/<int:lote_id>/', views.editar_lote, name='editar_lote'),
    path('lote/<int:lote_id>/adicionar/', views.adicionar_estoque, name='adicionar_estoque'),
    path('lotes/baixar/<int:lote_id>/', views.baixar_estoque, name='baixar_estoque'),
    path('lotes/excluir/<int:lote_id>/', views.excluir_lote, name='excluir_lote'),
    
    # URLs para relatórios
    path('relatorios/mensal/', views.filtros_relatorio_mensal, name='filtros_relatorio_mensal'),
    path('relatorios/mensal/gerar/', views.gerar_relatorio_mensal, name='gerar_relatorio_mensal'),
    path('relatorios/agricultura/', views.gerar_relatorio_origem, name='gerar_relatorio_origem'),
    path('relatorios/tipos/', views.gerar_relatorio_tipos, name='gerar_relatorio_tipos'),

    # URLs para pedidos de produtos
    path('pedidos/novo/', views.criar_pedido, name='criar_pedido'),
    path('pedidos/<int:pedido_id>/', views.detalhe_pedido, name='detalhe_pedido'),
    path('pedidos/item/remover/<int:item_id>/', views.remover_item_pedido, name='remover_item_pedido'),
    path('pedidos/remover-especial/<int:item_id>/', views.remover_item_especial, name='remover_item_especial'),
    path('pedidos/meus/', views.meus_pedidos, name='meus_pedidos'),
    path('pedidos/<int:pedido_id>/finalizar/', views.finalizar_pedido, name='finalizar_pedido'),
    path('estoque/', views.listar_estoque_disponivel, name='estoque_disponivel'),
    path('pedidos/<int:pedido_id>/excluir/', views.excluir_pedido, name='excluir_pedido'),
    path('pedidos/pendentes/', views.listar_pedidos_pendentes, name='listar_pedidos_pendentes'),
    path('pedidos/<int:pedido_id>/analisar/', views.detalhe_pedido_gestor, name='detalhe_pedido_gestor'),
    path('pedidos/<int:pedido_id>/aprovar/', views.aprovar_pedido, name='aprovar_pedido'),
    path('pedidos/<int:pedido_id>/rejeitar/', views.rejeitar_pedido, name='rejeitar_pedido'),
    path('pedidos/historico/', views.historico_pedidos, name='historico_pedidos'),
    path('api/pedidos/pendentes/contagem/', verificar_pedidos_pendentes, name='contagem_pedidos_pendentes'),
    path('pedidos/envio/', views.listar_pedidos_envio, name='listar_pedidos_envio'),
    path('pedidos/<int:pedido_id>/envio/', views.detalhe_pedido_envio, name='detalhe_pedido_envio'),
    path('pedidos/<int:pedido_id>/despachar/', views.despachar_pedido, name='despachar_pedido'),
]