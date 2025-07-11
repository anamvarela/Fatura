import streamlit as st
import pandas as pd
import pdfplumber
import plotly.express as px
import plotly.graph_objects as go
import re
from datetime import datetime, date
import calendar
from historico_faturas import (
    adicionar_fatura, obter_fatura_anterior,
    calcular_variacao, formatar_variacao,
    limpar_historico, limpar_fatura,
    adicionar_gasto_fixo, remover_gasto_fixo,
    obter_gastos_fixos, carregar_dados, salvar_dados,
    adicionar_entrada, remover_entrada, obter_entradas,
    adicionar_parcela, remover_parcela, marcar_parcela_paga,
    obter_parcelas_mes, calcular_total_parcelas_futuras,
    obter_parcelas_futuras, obter_historico_gastos_mensais,
    obter_historico_categorias, obter_media_gastos_categoria,
    obter_evolucao_gastos, classificar_transacao
)
import json
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from pathlib import Path
import time
import os
from dateutil.relativedelta import relativedelta
from collections import defaultdict
import hashlib

# Lista de categorias padrão
CATEGORIAS_PADRAO = ["Alimentação", "Transporte", "Entretenimento", "Self Care", "Roupas"]

def carregar_categorias():
    """Carrega as categorias do arquivo de configuração"""
    try:
        with open('categorias.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Se o arquivo não existir, cria com as categorias padrão
        categorias = CATEGORIAS_PADRAO
        with open('categorias.json', 'w') as f:
            json.dump(categorias, f, indent=4)
        return categorias

def salvar_categorias(categorias):
    """Salva as categorias no arquivo de configuração"""
    with open('categorias.json', 'w') as f:
        json.dump(categorias, f, indent=4)

def adicionar_categoria(nova_categoria):
    """Adiciona uma nova categoria à lista"""
    categorias = carregar_categorias()
    if nova_categoria not in categorias:
        categorias.append(nova_categoria)
        salvar_categorias(categorias)
        return True
    return False

def remover_categoria(categoria_remover):
    """Remove uma categoria da lista"""
    categorias = carregar_categorias()
    if categoria_remover in categorias:
        categorias.remove(categoria_remover)
        salvar_categorias(categorias)
        return True
    return False

def carregar_regras_classificacao():
    """Carrega as regras de classificação do arquivo"""
    try:
        with open('regras_classificacao.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def salvar_regras_classificacao(regras):
    """Salva as regras de classificação no arquivo"""
    with open('regras_classificacao.json', 'w', encoding='utf-8') as f:
        json.dump(regras, f, indent=2, ensure_ascii=False)

def adicionar_regra_classificacao(palavra_chave, categoria):
    """Adiciona uma nova regra de classificação"""
    regras = carregar_regras_classificacao()
    nova_regra = {
        'palavra_chave': palavra_chave.lower(),
        'categoria': categoria,
        'data_criacao': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    regras.append(nova_regra)
    salvar_regras_classificacao(regras)
    return True

def remover_regra_classificacao(palavra_chave):
    """Remove uma regra específica de classificação"""
    regras = carregar_regras_classificacao()
    regras_filtradas = [r for r in regras if r['palavra_chave'] != palavra_chave.lower()]
    if len(regras_filtradas) != len(regras):
        salvar_regras_classificacao(regras_filtradas)
        return True
    return False

def aplicar_regras_classificacao(descricao):
    """
    Aplica as regras de classificação definidas pelo usuário.
    
    Args:
        descricao (str): Descrição da transação
        
    Returns:
        str|None: Categoria encontrada ou None se nenhuma regra se aplicar
    """
    regras = carregar_regras_classificacao()
    descricao_lower = descricao.lower().strip()
    
    # Debug: Verificar se há regras carregadas
    if not regras:
        return None
    
    for regra in regras:
        palavra_chave = regra['palavra_chave'].lower().strip()
        # Verificar se a palavra-chave está presente na descrição
        if palavra_chave in descricao_lower:
            # Debug: Regra encontrada
            return regra['categoria']
    
    return None

def carregar_faturas():
    if os.path.exists('faturas.json'):
        with open('faturas.json', 'r') as f:
            return json.load(f)
    return []

def salvar_faturas(faturas):
    with open('faturas.json', 'w') as f:
        json.dump(faturas, f, indent=4)

def carregar_gastos_fixos():
    if os.path.exists('gastos_fixos.json'):
        with open('gastos_fixos.json', 'r') as f:
            return json.load(f)
    return []

def salvar_gastos_fixos(gastos_fixos):
    with open('gastos_fixos.json', 'w') as f:
        json.dump(gastos_fixos, f, indent=4)

def remover_transacao(fatura_mes, fatura_ano, descricao, valor):
    """Remove uma transação específica da fatura"""
    dados = carregar_dados()
    faturas = dados.get('faturas', [])
    
    for fatura in faturas:
        if fatura['mes'] == fatura_mes and fatura['ano'] == fatura_ano:
            fatura['transacoes'] = [t for t in fatura['transacoes'] 
                                  if not (t['descricao'] == descricao and abs(t['valor'] - valor) < 0.01)]
            break
    
    salvar_dados(dados)

def inicializar_classificacoes_base():
    """
    Inicializa a base de classificações com estabelecimentos conhecidos.
    Só cria se o arquivo não existir.
    """
    if not os.path.exists('classificacoes.json'):
        # Lista de estabelecimentos conhecidos
        classificacoes = {
            # Transporte - 99app e todas suas variações
            '99app': 'Transporte',
            '99 app': 'Transporte',
            '99*app': 'Transporte',
            '99 *app': 'Transporte',
            '99* app': 'Transporte',
            '99 * app': 'Transporte',
            '99app*': 'Transporte',
            '99 app*': 'Transporte',
            '*99app': 'Transporte',
            '* 99app': 'Transporte',
            '99app *': 'Transporte',
            '99app*99app': 'Transporte',
            '99app *99app': 'Transporte',
            '99app * 99app': 'Transporte',
            '99app* 99app': 'Transporte',
            
            # Restaurantes
            'abbraccio leblon': 'Alimentação',
            'absurda confeitaria': 'Alimentação',
            'amen gavea': 'Alimentação',
            'armazem 14 leblon': 'Alimentação',
            'art food rio bar e res': 'Alimentação',
            'bacio di latte': 'Alimentação',
            'bendita chica': 'Alimentação',
            'braseiro da gavea': 'Alimentação',
            'buddario': 'Alimentação',
            'cabana': 'Alimentação',
            'casa do alemao': 'Alimentação',
            'casa do pao de queijo': 'Alimentação',
            'choperiakaraoke': 'Alimentação',
            'emporio jardim': 'Alimentação',
            'fafato restaurante ba': 'Alimentação',
            'galeto leblon': 'Alimentação',
            'galeto rainha leblon': 'Alimentação',
            'la guapa': 'Alimentação',
            'la guapa - botafogo': 'Alimentação',
            'lena park': 'Alimentação',
            'nama restaurante': 'Alimentação',
            'natural delli buffet': 'Alimentação',
            'padaria oceanos': 'Alimentação',
            'pasta & basta': 'Alimentação',
            'pavilhao botafogo': 'Alimentação',
            'posi mozza': 'Alimentação',
            'reserva 11 beach club': 'Alimentação',
            'restaurante nanquim': 'Alimentação',
            'sardinha atividades ga': 'Alimentação',
            'sheesh downtown': 'Alimentação',
            'smoov barra sucos': 'Alimentação',
            'stuzzi': 'Alimentação',
            'tintin': 'Alimentação',
            'yogoberry': 'Alimentação',
            # Novos restaurantes encontrados nos dados históricos
            'eleninha': 'Alimentação',
            'dri': 'Alimentação',
            'jobi': 'Alimentação',
            'scarpi': 'Alimentação',
            'katzsu bar': 'Alimentação',
            'woods wine comercio': 'Alimentação',
            'tabacaria e cafeteria': 'Alimentação',
            'zig*caza lagoa': 'Alimentação',
            'zig*bud zone rj': 'Alimentação',
            'megamatterg': 'Alimentação'
        }
        salvar_classificacoes(classificacoes)

def carregar_classificacoes_salvas():
    """
    Carrega o dicionário de classificações já realizadas.
    Se não existir, inicializa com a base de estabelecimentos conhecidos.
    """
    inicializar_classificacoes_base()  # Garante que temos as classificações base
    try:
        with open('classificacoes.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def salvar_classificacoes(classificacoes):
    """
    Salva o dicionário de classificações em arquivo.
    """
    with open('classificacoes.json', 'w', encoding='utf-8') as f:
        json.dump(classificacoes, f, ensure_ascii=False, indent=4)

def atualizar_classificacao_salva(descricao, categoria):
    """
    Atualiza a base de classificações com uma nova classificação.
    """
    classificacoes = carregar_classificacoes_salvas()
    # Normaliza a descrição para evitar duplicatas por diferenças de case
    descricao_norm = descricao.lower().strip()
    classificacoes[descricao_norm] = categoria
    salvar_classificacoes(classificacoes)

def carregar_classificacoes_manuais():
    """
    Carrega o dicionário de classificações feitas manualmente (com o lápis).
    """
    try:
        with open('classificacoes_manuais.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def salvar_classificacoes_manuais(classificacoes_manuais):
    """
    Salva o dicionário de classificações manuais em arquivo.
    """
    with open('classificacoes_manuais.json', 'w', encoding='utf-8') as f:
        json.dump(classificacoes_manuais, f, ensure_ascii=False, indent=4)

def atualizar_classificacao_manual(descricao, categoria):
    """
    Atualiza a base de classificações manuais com uma nova classificação.
    """
    classificacoes_manuais = carregar_classificacoes_manuais()
    # Normaliza a descrição para evitar duplicatas por diferenças de case
    descricao_norm = descricao.lower().strip()
    classificacoes_manuais[descricao_norm] = categoria
    salvar_classificacoes_manuais(classificacoes_manuais)

def editar_categoria_transacao(fatura_mes, fatura_ano, descricao, valor, nova_categoria):
    """
    Edita a categoria de uma transação e salva a nova classificação como MANUAL.
    """
    dados = carregar_dados()
    faturas = dados.get('faturas', [])
    
    for fatura in faturas:
        if fatura['mes'] == fatura_mes and fatura['ano'] == fatura_ano:
            for transacao in fatura['transacoes']:
                if transacao['descricao'] == descricao and abs(transacao['valor'] - valor) < 0.01:
                    transacao['categoria'] = nova_categoria
                    # Salvar como classificação MANUAL (não será sobrescrita)
                    atualizar_classificacao_manual(descricao, nova_categoria)
                    break
    
    salvar_dados(dados)

def classificar_transacao(descricao):
    """
    Classifica automaticamente uma transação com base em sua descrição.
    ORDEM DE PRIORIDADE:
    1. Classificações manuais (feitas com lápis) - NUNCA são sobrescritas
    2. Regras do usuário (palavras-chave definidas)
    3. Regras especiais hardcoded (99app, mercado livre, etc.)
    4. Classificações automáticas salvas
    5. Regras automáticas baseadas em palavras-chave
    """
    descricao_original = descricao
    descricao = descricao.lower().strip()
    
    # 1. MÁXIMA PRIORIDADE: Verificar se foi classificada MANUALMENTE
    classificacoes_manuais = carregar_classificacoes_manuais()
    if descricao in classificacoes_manuais:
        return classificacoes_manuais[descricao]
    
    # 2. APLICAR REGRAS DO USUÁRIO (palavras-chave definidas pelo usuário)
    categoria_regra = aplicar_regras_classificacao(descricao)
    if categoria_regra:
        return categoria_regra
    
    # 3. VERIFICAÇÕES ESPECIAIS HARDCODED
    # 99APP - Regra especial para transporte
    if '99app' in descricao or ('99' in descricao and 'app' in descricao) or '99 app' in descricao:
        return 'Transporte'
    
    # Mercado Livre - Regra especial para roupas
    if 'mercado livre' in descricao or 'mercadolivre' in descricao:
        return 'Roupas'
    
    # Zig* - Regra especial para entretenimento
    if descricao.startswith('zig'):
        return 'Entretenimento'
    
    # 4. Verificar se já existe uma classificação automática salva
    classificacoes_salvas = carregar_classificacoes_salvas()
    if descricao in classificacoes_salvas:
        return classificacoes_salvas[descricao]

    # Verificar se é uma entrada - isso é tratado na função adicionar_fatura()
    # palavras_entrada = ['reembolso', 'cashback', 'rendimento', 'pagamento recebido', 'transferencia recebida']
    # if any(palavra in descricao for palavra in palavras_entrada):
    #     return "ENTRADA"

    # Dicionário de estabelecimentos por categoria
    categorias = {
        'Alimentação': [
            # Restaurantes e similares
            'restaurante', 'rest.', 'rest ', 'churrascaria', 'pizzaria', 'pizza',
            'hamburger', 'burger', 'lanchonete', 'bar', 'boteco', 'cantina',
            'galeto', 'padaria', 'confeitaria', 'doceria', 'cafeteria', 'café',
            'bistro', 'buffet', 'grill', 'espeto', 'pastelaria', 'pastel',
            'rotisserie', 'sushi', 'japanese', 'china in box', 'chinesa', 'thai',
            'mexicano', 'árabe', 'arabe', 'absurda', 'ferro e farinha',
            'outback', 'mcdonalds', 'mc donalds', 'burger king', 'bk', 'subway',
            'habibs', 'spoleto', 'giraffas', 'madero', 'dominos', 'pizza hut',
            'starbucks', 'kopenhagen', 'cacau show',
            # Delivery
            'ifood', 'rappi', 'uber eats', 'james delivery', 'aiqfome',
            # Mercados e similares
            'carrefour', 'extra', 'pao de acucar', 'assai', 'mundial', 'guanabara',
            'zona sul', 'hortifruti', 'supermarket', 'mercado', 'supermercado',
            'sacolao', 'feira', 'mercearia', 'atacado', 'atacadao', 'dia',
            'sams club', 'makro', 'tenda', 'quitanda', 'adega', 'emporio',
            'armazem', 'minimercado', 'mercadinho', 'acougue', 'açougue',
            'peixaria', 'supernosso', 'verdemar', 'epa', 'super', 'mart',
            # Restaurantes específicos baseados nos dados históricos
            'bendita chica', 'bendita', 'chica', 'amen gavea', 'amen',
            'art food', 'abbraccio', 'braseiro', 'gavea', 'nama',
            'nanquim', 'posi mozza', 'posi', 'mozza', 'smoov', 'sucos',
            'katzsu', 'katzsu bar', 'eleninha', 'buddario', 'dri',
            'jobi', 'scarpi', 'tintin', 'choperiakaraoke', 'chopp',
            'casa do alemao', 'alemao', 'tabacaria', 'cafeteria',
            'woods wine', 'woods', 'wine', 'reserva 11', 'beach club',
            'zig', 'caza', 'lagoa', 'sheesh', 'downtown', 'galeto',
            'rainha', 'leblon', 'natural delli', 'buffet', 'food'
        ],
        'Transporte': [
            # Apps de transporte (removido 99 pois já está tratado acima)
            'uber', 'cabify', 'taxi', 'táxi', 'transfer', 'shuttle', 'buser',
            # Combustível
            'posto', 'shell', 'ipiranga', 'petrobras', 'br posto', 'ale',
            'combustivel', 'gasolina', 'etanol', 'diesel', 'br mania',
            # Transporte público
            'metro', 'metrô', 'trem', 'onibus', 'ônibus', 'brt', 'vlt',
            'bilhete unico', 'bilhete único', 'cartao riocard', 'supervia',
            'cartão riocard', 'bom', 'bem', 'metrocard',
            # Estacionamento
            'estacionamento', 'parking', 'zona azul', 'parquimetro',
            'estapar', 'multipark', 'autopark','99app'
        ],
        'Entretenimento': [
            # Streaming
            'netflix', 'spotify', 'amazon prime', 'disney+', 'hbo max',
            'youtube premium', 'deezer', 'apple music', 'tidal',
            'paramount+', 'globoplay', 'crunchyroll', 'twitch',
            # Jogos
            'steam', 'playstation', 'psn', 'xbox', 'nintendo',
            'epic games', 'battle.net', 'origin', 'uplay', 'gog',
            # Eventos
            'cinema', 'teatro', 'show', 'evento', 'ingresso', 'tickets',
            'sympla', 'eventbrite', 'ticket360', 'ingressorapido',
            'livepass', 'ticketmaster', 'cinemark', 'kinoplex'
        ],
        'Self Care': [
            # Saúde
            'farmacia', 'drogaria', 'droga', 'pacheco', 'raia', 'drogasil',
            'farmácia', 'remedios', 'remédios', 'medicamentos', 'consulta',
            'medico', 'médico', 'dentista', 'psicólogo', 'psicologo',
            'terapeuta', 'fisioterapeuta', 'nutricionista', 'exame',
            'laboratorio', 'laboratório', 'clinica', 'clínica', 'hospital',
            'plano de saude', 'plano de saúde',
            # Beleza
            'salao', 'salão', 'cabelereiro', 'cabeleireiro', 'manicure',
            'pedicure', 'spa', 'massagem', 'estetica', 'estética',
            'barbearia', 'barber', 'depilacao', 'depilação', 'beauty',
            # Academia
            'academia', 'gym', 'crossfit', 'pilates', 'yoga', 'personal',
            'trainer', 'box', 'fitness', 'smart fit', 'bodytech', 'selfit'
        ],
        'Roupas': [
            # Lojas de departamento e vestuário (removido shop/store para evitar falsos positivos)
            'renner', 'cea', 'c&a', 'riachuelo', 'marisa', 'hering',
            'zara', 'forever 21', 'leader', 'h&m',
            # Lojas de esporte
            'centauro', 'decathlon', 'netshoes', 'nike', 'adidas', 'puma',
            # Lojas online
            'amazon', 'americanas', 'submarino', 'magalu', 'magazine luiza',
            'shopee', 'aliexpress', 'shein', 'mercado livre', 'kabum',
            # Outras lojas
            'casas bahia', 'ponto frio', 'fastshop', 'leroy merlin',
            'telhanorte', 'c&c', 'tok&stok', 'etna', 'camicado', 'mobly'
        ]
    }

    # Procurar por correspondências nas categorias
    for categoria, palavras_chave in categorias.items():
        if any(palavra in descricao for palavra in palavras_chave):
            return categoria

    return "Roupas"

def adicionar_fatura(fatura):
    """Adiciona uma nova fatura ao histórico"""
    dados = carregar_dados()
    faturas = dados.get('faturas', [])
    
    # Classificar transações e separar entradas de despesas
    transacoes_despesas = []
    entradas = dados.get('entradas', [])
    
    for transacao in fatura['transacoes']:
        descricao_lower = transacao['descricao'].lower()
        
        # VERIFICAR PRIMEIRO se é estorno/desconto (vai para entradas)
        if 'estorno' in descricao_lower or 'desconto' in descricao_lower:
            entrada = {
                'descricao': transacao['descricao'],
                'valor': transacao['valor'],
                'mes': fatura['mes'],
                'ano': fatura['ano']
            }
            entradas.append(entrada)
        else:
            # Se não for entrada, classificar normalmente e manter como despesa
            if 'categoria' not in transacao:
                transacao['categoria'] = classificar_transacao(transacao['descricao'])
            transacoes_despesas.append(transacao)
    
    # Atualizar a fatura apenas com despesas
    fatura['transacoes'] = transacoes_despesas
    dados['entradas'] = entradas
    
    # Verificar se já existe uma fatura para este mês/ano
    for i, f in enumerate(faturas):
        if f['mes'] == fatura['mes'] and f['ano'] == fatura['ano']:
            faturas[i] = fatura
            dados['faturas'] = faturas
            salvar_dados(dados)
            return
    
    # Se não existe, adicionar nova fatura
    faturas.append(fatura)
    dados['faturas'] = faturas
    salvar_dados(dados)

# Função auxiliar para formatar valores
def formatar_valor(valor):
    """Formata um valor monetário com pontos para milhares e vírgula para decimais"""
    return f"R$ {valor:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

def adicionar_gasto_fixo_novo(transacao):
    """Adiciona um novo gasto fixo"""
    gasto = {
        'descricao': transacao['descricao'],
        'valor': transacao['valor'],
        'categoria': transacao.get('categoria', 'Outros'),
        'data_adicao': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    adicionar_gasto_fixo(gasto)
    st.success('✅ Gasto fixo adicionado com sucesso!')
    st.experimental_rerun()

def remover_gasto_fixo_novo(descricao, valor):
    """Remove um gasto fixo"""
    remover_gasto_fixo(descricao, valor)
    st.success('✅ Gasto fixo removido com sucesso!')
    st.experimental_rerun()

def corrigir_classificacoes_99app():
    """
    Corrige todas as classificações incorretas do 99app que estão como 'Roupas' para 'Transporte'.
    """
    dados = carregar_dados()
    faturas = dados.get('faturas', [])
    
    corrigidas = 0
    for fatura in faturas:
        for transacao in fatura.get('transacoes', []):
            descricao = transacao.get('descricao', '').lower()
            # Verifica se é uma transação do 99app e se está classificada incorretamente
            if ('99app' in descricao or ('99' in descricao and 'app' in descricao) or '99 app' in descricao):
                if transacao.get('categoria') == 'Roupas':
                    transacao['categoria'] = 'Transporte'
                    corrigidas += 1
                    print(f"Corrigindo classificação de '{transacao['descricao']}' para Transporte")
                    # Salva a classificação correta
                    atualizar_classificacao_salva(descricao, 'Transporte')
    
    salvar_dados(dados)
    return corrigidas

def corrigir_classificacoes_restaurantes():
    """
    Corrige todas as classificações incorretas de restaurantes que estão como 'Roupas' ou 'Outros' para 'Alimentação'.
    """
    dados = carregar_dados()
    faturas = dados.get('faturas', [])
    
    # Lista de restaurantes conhecidos
    restaurantes_conhecidos = [
        'bendita chica', 'bendita', 'amen gavea', 'amen', 'art food',
        'abbraccio', 'braseiro', 'gavea', 'nama', 'nanquim', 'posi mozza',
        'posi', 'mozza', 'smoov', 'sucos', 'katzsu', 'eleninha', 'buddario',
        'dri', 'jobi', 'scarpi', 'tintin', 'choperiakaraoke', 'chopp',
        'alemao', 'tabacaria', 'woods wine', 'woods', 'wine', 'reserva 11',
        'beach club', 'zig', 'caza', 'lagoa', 'sheesh', 'downtown',
        'galeto', 'rainha', 'leblon', 'natural delli', 'buffet', 'absurda',
        'confeitaria', 'zona sul', 'restaurante', 'bar', 'cafeteria'
    ]
    
    corrigidas = 0
    for fatura in faturas:
        for transacao in fatura.get('transacoes', []):
            descricao = transacao.get('descricao', '').lower()
            categoria_atual = transacao.get('categoria', '')
            
            # Verifica se é um restaurante e se está classificado incorretamente
            if any(rest in descricao for rest in restaurantes_conhecidos):
                if categoria_atual in ['Roupas', 'Outros']:
                    transacao['categoria'] = 'Alimentação'
                    corrigidas += 1
                    print(f"Corrigindo classificação de '{transacao['descricao']}' para Alimentação")
                    # Salva a classificação correta
                    atualizar_classificacao_salva(descricao, 'Alimentação')
    
    salvar_dados(dados)
    return corrigidas


def limpar_fatura(mes, ano):
    """
    Remove todos os dados da fatura do mês e ano selecionados.
    Inclui: transações, entradas e gastos fixos específicos do mês.
    IMPORTANTE: O indicador visual (check verde) aparece apenas quando há FATURAS,
    mas este botão remove todos os tipos de dados.
    """
    dados = carregar_dados()
    
    # Contar itens antes da remoção
    faturas_removidas = 0
    entradas_removidas = 0
    gastos_fixos_removidos = 0
    
    # Contar faturas que serão removidas
    for fatura in dados.get('faturas', []):
        if fatura['mes'] == mes and fatura['ano'] == ano:
            faturas_removidas += len(fatura.get('transacoes', []))
    
    # Contar entradas que serão removidas
    if 'entradas' in dados:
        entradas_removidas = len([
            entrada for entrada in dados['entradas']
            if entrada.get('mes') == mes and entrada.get('ano') == ano
        ])
    
    # Contar gastos fixos
    gastos_fixos_removidos = len(dados.get('gastos_fixos', []))
    
    # Encontrar e remover a fatura específica
    dados['faturas'] = [
        fatura for fatura in dados['faturas']
        if not (fatura['mes'] == mes and fatura['ano'] == ano)
    ]
    
    # Remover entradas específicas do mês
    if 'entradas' in dados:
        dados['entradas'] = [
            entrada for entrada in dados['entradas']
            if not (entrada.get('mes') == mes and entrada.get('ano') == ano)
        ]
    
    # Remover gastos fixos específicos do mês (se tiverem referência de mês/ano)
    # ou simplesmente limpar todos os gastos fixos (caso não tenham referência temporal)
    if 'gastos_fixos' in dados:
        # Como gastos fixos geralmente não têm referência temporal específica,
        # vamos limpar todos os gastos fixos quando limpar o mês
        dados['gastos_fixos'] = []
    
    # Salvar os dados atualizados
    salvar_dados(dados)
    
    # Exibir mensagens de sucesso com detalhes
    st.success(f"✓ Todos os dados de {mes}/{ano} removidos com sucesso!")
    
    if faturas_removidas > 0:
        st.success(f"  - {faturas_removidas} transações da fatura removidas")
    else:
        st.info("  - Nenhuma transação encontrada para remover")
    
    if entradas_removidas > 0:
        st.success(f"  - {entradas_removidas} entradas do mês removidas")
    else:
        st.info("  - Nenhuma entrada encontrada para remover")
    
    if gastos_fixos_removidos > 0:
        st.success(f"  - {gastos_fixos_removidos} gastos fixos removidos")
    else:
        st.info("  - Nenhum gasto fixo encontrado para remover")
    
    time.sleep(0.5)
    st.rerun()

def reaplicar_regras_todas_transacoes():
    """
    Reaplica todas as regras de classificação às transações existentes.
    
    IMPORTANTE: Preserva classificações manuais feitas com o lápis.
    Só atualiza transações que não foram classificadas manualmente.
    """
    dados = carregar_dados()
    transacoes_atualizadas = 0
    transacoes_preservadas = 0
    entradas = dados.get('entradas', [])
    
    # Carregar classificações manuais (feitas com lápis)
    classificacoes_manuais = carregar_classificacoes_manuais()
    
    # Aplicar regras às faturas
    for fatura in dados.get('faturas', []):
        transacoes_para_remover = []
        
        for i, transacao in enumerate(fatura.get('transacoes', [])):
            descricao_lower = transacao['descricao'].lower().strip()
            
            # Verificar se deve ir para entradas
            if 'estorno' in descricao_lower or 'desconto' in descricao_lower:
                # Mover para entradas
                entrada = {
                    'descricao': transacao['descricao'],
                    'valor': transacao['valor'],
                    'mes': fatura['mes'],
                    'ano': fatura['ano']
                }
                entradas.append(entrada)
                transacoes_para_remover.append(i)
                transacoes_atualizadas += 1
            else:
                # Verificar se foi classificada MANUALMENTE (com lápis)
                foi_classificada_manualmente = descricao_lower in classificacoes_manuais
                
                if foi_classificada_manualmente:
                    # Preservar classificação manual - NUNCA sobrescrever
                    transacoes_preservadas += 1
                    # Garantir que a categoria manual seja mantida
                    categoria_manual = classificacoes_manuais[descricao_lower]
                    if transacao.get('categoria', '') != categoria_manual:
                        transacao['categoria'] = categoria_manual
                    continue
                
                # Só aplicar nova classificação se não foi feita manualmente
                categoria_original = transacao.get('categoria', '')
                categoria_nova = classificar_transacao(transacao['descricao'])
                
                if categoria_original != categoria_nova:
                    transacao['categoria'] = categoria_nova
                    transacoes_atualizadas += 1
        
        # Remover transações que foram movidas para entradas
        for i in reversed(transacoes_para_remover):
            del fatura['transacoes'][i]
    
    # Atualizar entradas nos dados
    dados['entradas'] = entradas
    
    # Salvar os dados atualizados
    salvar_dados(dados)
    
    # Retornar informações sobre o que foi feito
    return {
        'atualizadas': transacoes_atualizadas,
        'preservadas': transacoes_preservadas
    }



# Configuração da página
st.set_page_config(
    page_title="Análise Faturas Nubank",
    page_icon="📊",
    layout="wide",
)

# Inicializar variáveis de sessão
if 'user_data_dir' not in st.session_state:
    st.session_state['user_data_dir'] = 'data/default'

# Carregar configurações de autenticação
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

# Criar o autenticador
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# Adicionar login
name, authentication_status, username = authenticator.login('Login')

if authentication_status == False:
    st.error('Username/password is incorrect')
elif authentication_status == None:
    st.warning('Please enter your username and password')
elif authentication_status:
    # Criar diretório do usuário se não existir
    user_dir = Path(f"data/{username}")
    user_dir.mkdir(parents=True, exist_ok=True)
    
    # Configurar caminhos específicos do usuário
    st.session_state['user_data_dir'] = str(user_dir)
    
    # Adicionar logout na sidebar
    with st.sidebar:
        authenticator.logout('Logout')
    
    # Título principal
    st.markdown(f"<h1 class='main-header'>Análise</h1>", unsafe_allow_html=True)
    
    # Inicializar estados
    if 'checkbox_states' not in st.session_state:
        st.session_state.checkbox_states = {}

    # Configurações de estilo
    st.markdown("""
        <style>
        .main-header {
            font-size: 2.5rem;
            color: #4B0082;
            margin-bottom: 2rem;
        }
        .stButton > button {
            background-color: #4B0082;
            color: white;
        }
        .stButton > button:hover {
            background-color: #3B0062;
            color: white;
        }
        div[data-testid="stMetricValue"] {
            color: #4B0082;
        }
        </style>
    """, unsafe_allow_html=True)

    # Função para verificar se há faturas para um mês específico
    def tem_fatura_mes(mes, ano):
        """
        Verifica se há fatura salva para um mês específico.
        
        IMPORTANTE: Esta função determina se o check verde (✅) aparece no seletor de mês.
        Verifica APENAS faturas, não entradas nem gastos fixos.
        
        Args:
            mes (int): Número do mês (1-12)
            ano (int): Ano (ex: 2024)
            
        Returns:
            bool: True se há fatura salva para o mês/ano, False caso contrário
        """
        dados = carregar_dados()
        
        # Verificar apenas faturas (não entradas nem gastos fixos)
        tem_faturas = any(
            f['mes'] == mes and f['ano'] == ano 
            for f in dados.get('faturas', [])
        )
        
        return tem_faturas
    
    # Seleção do mês com indicadores visuais
    mes_options_base = {
        'Janeiro': 1, 'Fevereiro': 2, 'Março': 3, 'Abril': 4,
        'Maio': 5, 'Junho': 6, 'Julho': 7, 'Agosto': 8,
        'Setembro': 9, 'Outubro': 10, 'Novembro': 11, 'Dezembro': 12
    }
    
    # Inicializar opções básicas de mês (serão atualizadas após seleção do ano)
    mes_options = {nome: num for nome, num in mes_options_base.items()}

    # Funções de processamento
    @st.cache_data(ttl=600)
    def processar_pdf(arquivo_pdf):
        """Processa o arquivo PDF da fatura"""
        try:
            texto_completo = []
            with pdfplumber.open(arquivo_pdf) as pdf:
                for pagina in pdf.pages:
                    texto_completo.append(pagina.extract_text())
            
            texto_completo = '\n'.join(texto_completo)
            linhas = texto_completo.split('\n')
            
            transacoes = []
            for linha in linhas:
                if re.search(r'\d{2} [A-Z]{3}', linha):
                    try:
                        # Ignorar linhas de IOF e totais
                        if any(termo in linha.lower() for termo in [
                            'iof de', 'total de', 'pagamento em'
                        ]):
                            continue
                            
                        data = re.search(r'\d{2} [A-Z]{3}', linha).group()
                        valor = re.search(r'R\$ \d+[.,]\d{2}', linha)
                        if valor:
                            valor = float(valor.group().replace('R$ ', '').replace('.', '').replace(',', '.'))
                            descricao = re.sub(r'\d{2} [A-Z]{3}|R\$ \d+[.,]\d{2}', '', linha).strip()
                            
                            # Limpar números de cartão da descrição
                            descricao = re.sub(r'•{4} \d{4}', '', descricao).strip()
                            
                            # Ignorar se a descrição estiver vazia após limpeza
                            if not descricao:
                                continue
                                
                            transacoes.append({
                                'data': data,
                                'descricao': descricao,
                                'valor': valor
                            })
                    except Exception as e:
                        st.warning(f"Erro ao processar linha: {linha}")
                        continue
            
            if not transacoes:
                st.error("Não foi possível encontrar transações no arquivo. Certifique-se de que este é um arquivo de fatura do Nubank.")
                return None
            
            # Criar fatura
            mes_num = mes_options[mes_selecionado]
            fatura = {
                'mes': mes_num,
                'ano': ano_selecionado,
                'transacoes': transacoes
            }
            
            # Retornar DataFrame para exibição
            return pd.DataFrame(transacoes)
        except Exception as e:
            st.error(f"Erro ao processar o PDF: {str(e)}")
            return None

    # Função para classificar transações
    def classificar_transacao(descricao):
        descricao = descricao.lower()
        
        # Verificar se contém "estorno" ou "desconto" - isso é tratado na função adicionar_fatura()
        # Não classificamos aqui, apenas retornamos categoria normal
        
        # Verificar se é Zig* (entretenimento)
        if descricao.startswith('zig'):
            return 'Entretenimento'
        
        # VERIFICAÇÃO ESPECIAL PARA 99APP - MÁXIMA PRIORIDADE
        if '99app' in descricao or ('99' in descricao and 'app' in descricao) or '99 app' in descricao:
            return "Transporte"
        
        # VERIFICAÇÕES ESPECIAIS PARA ROUPAS (antes de verificar mercado)
        if 'mercado livre' in descricao or 'mercadolivre' in descricao:
            return "Roupas"
        
        # APLICAR REGRAS DO USUÁRIO (antes das regras automáticas)
        categoria_regra = aplicar_regras_classificacao(descricao)
        if categoria_regra:
            return categoria_regra
        
        # Alimentação
        if any(palavra in descricao for palavra in [
            'ifood', 'rappi', 'uber eats', 'restaurante', 'padaria', 'mercado',
            'supermercado', 'hortifruti', 'açougue', 'acougue', 'cafeteria',
            'cafe', 'café', 'bar', 'lanchonete', 'food', 'burger',
            # Restaurantes específicos
            'bendita chica', 'bendita', 'chica', 'amen gavea', 'amen',
            'art food', 'abbraccio', 'braseiro', 'gavea', 'nama',
            'nanquim', 'posi mozza', 'posi', 'mozza', 'smoov', 'sucos',
            'katzsu', 'eleninha', 'buddario', 'dri', 'jobi', 'scarpi',
            'tintin', 'choperiakaraoke', 'chopp', 'alemao', 'tabacaria',
            'woods wine', 'woods', 'wine', 'reserva 11', 'beach club',
            'zig', 'caza', 'lagoa', 'sheesh', 'downtown', 'galeto',
            'rainha', 'leblon', 'natural delli', 'buffet', 'absurda',
            'confeitaria', 'zona sul'
        ]):
            return "Alimentação"
        
        # Transporte
        if any(palavra in descricao for palavra in [
            'uber', '99 pop', '99pop', 'taxi', 'táxi', 'combustivel', 'combustível',
            'estacionamento', 'metro', 'metrô', 'onibus', 'ônibus', 'bilhete',
            'posto', 'gasolina', 'etanol', 'alcool', 'álcool', 'uber*', 'uber x'
        ]):
            return "Transporte"
        
        # Entretenimento
        if any(palavra in descricao for palavra in [
            'netflix', 'spotify', 'cinema', 'teatro', 'show', 'ingresso',
            'prime video', 'disney+', 'hbo', 'jogos', 'game', 'playstation',
            'xbox', 'steam', 'livraria', 'livro', 'música', 'musica',
            'streaming', 'assinatura'
        ]):
            return "Entretenimento"
        
        # Self Care
        if any(palavra in descricao for palavra in [
            'academia', 'farmacia', 'farmácia', 'drogaria', 'medico', 'médico',
            'dentista', 'psicólogo', 'psicologo', 'terapia', 'spa', 'massagem',
            'salao', 'salão', 'cabelereiro', 'manicure', 'pedicure', 'pilates',
            'yoga', 'crossfit', 'gym', 'consulta', 'exame', 'clinica', 'clínica',
            'hospital', 'remedio', 'remédio'
        ]):
            return "Self Care"
        
        # Roupas (incluindo o que antes era "Outros")
        return "Roupas"

    # Função auxiliar para formatar valores
    def formatar_valor(valor):
        """Formata um valor monetário com pontos para milhares e vírgula para decimais"""
        return f"R$ {valor:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

    def adicionar_gasto_fixo_novo(transacao):
        """Adiciona um novo gasto fixo"""
        gasto = {
            'descricao': transacao['descricao'],
            'valor': transacao['valor'],
            'categoria': transacao.get('categoria', 'Outros'),
            'data_adicao': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        adicionar_gasto_fixo(gasto)
        st.success('✅ Gasto fixo adicionado com sucesso!')
        st.experimental_rerun()

    def remover_gasto_fixo_novo(descricao, valor):
        """Remove um gasto fixo"""
        remover_gasto_fixo(descricao, valor)
        st.success('✅ Gasto fixo removido com sucesso!')
        st.experimental_rerun()

    def gerar_chave_transacao(transacao, prefixo=""):
        """Gera uma chave única para a transação baseada em seus atributos"""
        # Criar uma string com todos os atributos relevantes
        chave_base = f"{transacao['descricao']}_{transacao['valor']}_{prefixo}"
        # Gerar um hash curto (8 caracteres) para garantir unicidade
        return hashlib.md5(chave_base.encode()).hexdigest()[:8]

    # Criar seleção de mês e ano
    col1, col2 = st.columns([2, 1])
    
    with col2:
        ano_atual = datetime.now().year
        ano_selecionado = st.selectbox(
            "Ano",
            options=range(ano_atual-2, ano_atual+1),
            index=2,
            key="ano_selecionado"
        )
    
    # Recriar opções do mês com base no ano selecionado
    mes_options = {}
    for nome_mes, num_mes in mes_options_base.items():
        if tem_fatura_mes(num_mes, ano_selecionado):
            mes_options[f"✅ {nome_mes}"] = num_mes
        else:
            mes_options[f"⚪ {nome_mes}"] = num_mes

    with col1:
        opcoes_mes = list(mes_options.keys())
        
        # Verificar se há uma solicitação para manter um mês específico (após upload)
        if 'mes_manter_selecao' in st.session_state:
            mes_para_manter = st.session_state['mes_manter_selecao']
            # Procurar o mês nas opções (pode estar com ✅ ou ⚪)
            for opcao in opcoes_mes:
                if mes_para_manter in opcao:
                    st.session_state.mes_selecionado = opcao
                    break
            # Limpar a flag
            del st.session_state['mes_manter_selecao']
        
        # Inicializar com mês atual apenas se não existir no session_state
        elif 'mes_selecionado' not in st.session_state:
            mes_atual = datetime.now().month
            nome_mes_atual = list(mes_options_base.keys())[mes_atual - 1]
            
            # Procurar a opção do mês atual (com ou sem check)
            for opcao in opcoes_mes:
                if nome_mes_atual in opcao:
                    st.session_state.mes_selecionado = opcao
                    break
            else:
                # Se não encontrar, usar o primeiro da lista
                st.session_state.mes_selecionado = opcoes_mes[0]
        
        # Verificar se a seleção atual ainda existe nas opções (após mudança de ano)
        elif st.session_state.mes_selecionado not in opcoes_mes:
            # Se a seleção atual não existe mais, encontrar equivalente sem/com check
            mes_limpo = st.session_state.mes_selecionado.replace('✅ ', '').replace('⚪ ', '')
            for opcao in opcoes_mes:
                if mes_limpo in opcao:
                    st.session_state.mes_selecionado = opcao
                    break
            else:
                st.session_state.mes_selecionado = opcoes_mes[0]
        
        mes_selecionado = st.selectbox(
            "Selecione o Mês",
            options=opcoes_mes,
            help="✅ indica meses com faturas salvas",
            key="mes_selecionado"
        )
        # Definir mes_num logo após a seleção
        mes_num = mes_options[mes_selecionado]

    # Criar tabs
    tab_inserir, tab_entradas, tab_analise, tab_parcelas, tab_fixos, tab_historico = st.tabs([
        "📥 Inserir Fatura",
        "💰 Entradas do Mês",
        "📊 Análise",
        "🔄 Parcelas Futuras",
        "📌 Gastos Fixos",
        "📈 Histórico"
    ])

    # Aba de Inserir Fatura
    with tab_inserir:
        st.subheader("Inserir Nova Fatura")
        
        # Upload do arquivo
        arquivo = st.file_uploader("Faça upload da sua fatura (PDF)", type=['pdf'])
        
        if arquivo is not None:
            df = processar_pdf(arquivo)
            if df is not None:
                # Aplicar categorização inicial
                df['categoria'] = df['descricao'].apply(classificar_transacao)

        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💾 Salvar Fatura", use_container_width=True):
                if arquivo is not None:
                    if df is not None:
                        try:
                            fatura = {
                                'mes': mes_num,
                                'ano': ano_selecionado,
                                'transacoes': df.to_dict('records')
                            }
                            adicionar_fatura(fatura)
                            # Limpar nome do mês de checks visuais para exibição
                            nome_mes_limpo = mes_selecionado.replace('✅ ', '').replace('⚪ ', '')
                            st.success(f"Fatura de {nome_mes_limpo}/{ano_selecionado} salva com sucesso!")
                            
                            # Manter a seleção do mês atual (nome limpo) para o próximo rerun
                            st.session_state['mes_manter_selecao'] = nome_mes_limpo
                            st.rerun()  # Atualizar indicadores visuais
                        except Exception as e:
                            st.error(f"Erro ao salvar fatura: {str(e)}")
                else:
                    st.warning("Por favor, faça upload de uma fatura primeiro.")
        
        with col2:
            # Contar dados existentes para o mês selecionado
            dados_existentes = carregar_dados()
            
            # Contar itens do mês atual
            transacoes_mes = 0
            for fatura in dados_existentes.get('faturas', []):
                if fatura['mes'] == mes_num and fatura['ano'] == ano_selecionado:
                    transacoes_mes += len(fatura.get('transacoes', []))
            
            entradas_mes = len([
                e for e in dados_existentes.get('entradas', [])
                if e.get('mes') == mes_num and e.get('ano') == ano_selecionado
            ])
            
            gastos_fixos_total = len(dados_existentes.get('gastos_fixos', []))
            
            # Verificar se há fatura (para mostrar estado correto do botão)
            tem_fatura = tem_fatura_mes(mes_num, ano_selecionado)
            
            # Inicializar estado do botão de confirmação
            if f'confirm_clear_{mes_num}_{ano_selecionado}' not in st.session_state:
                st.session_state[f'confirm_clear_{mes_num}_{ano_selecionado}'] = False
            
            if not st.session_state[f'confirm_clear_{mes_num}_{ano_selecionado}']:
                # Mostrar botão com preview dos dados
                total_itens = transacoes_mes + entradas_mes + gastos_fixos_total
                
                if total_itens > 0:
                    # Diferentes textos baseados no que tem
                    if tem_fatura:
                        botao_texto = f"🗑️ Limpar TODOS os Dados do Mês ({total_itens} itens)"
                    else:
                        botao_texto = f"🗑️ Limpar Dados do Mês ({total_itens} itens - sem fatura)"
                    
                    if st.button(botao_texto, use_container_width=True, type="secondary"):
                        st.session_state[f'confirm_clear_{mes_num}_{ano_selecionado}'] = True
                        st.rerun()
                else:
                    st.button("🗑️ Limpar TODOS os Dados do Mês (vazio)", use_container_width=True, disabled=True)
            else:
                st.error("⚠️ **CONFIRMAÇÃO NECESSÁRIA**")
                # Limpar nome do mês de checks visuais para exibição
                nome_mes_limpo = mes_selecionado.replace('✅ ', '').replace('⚪ ', '')
                st.warning(f"Isso vai apagar TODOS os dados de {nome_mes_limpo}/{ano_selecionado}:")
                if transacoes_mes > 0:
                    st.write(f"• {transacoes_mes} transações da fatura")
                if entradas_mes > 0:
                    st.write(f"• {entradas_mes} entradas registradas")
                if gastos_fixos_total > 0:
                    st.write(f"• {gastos_fixos_total} gastos fixos")
                if transacoes_mes == 0 and entradas_mes == 0 and gastos_fixos_total == 0:
                    st.write("• Nenhum dado encontrado para remover")
                st.write("")
                
                col2a, col2b = st.columns(2)
                with col2a:
                    if st.button("✅ SIM, Apagar Tudo", use_container_width=True, type="primary"):
                        limpar_fatura(mes_num, ano_selecionado)
                        st.session_state[f'confirm_clear_{mes_num}_{ano_selecionado}'] = False
                with col2b:
                    if st.button("❌ Cancelar", use_container_width=True):
                        st.session_state[f'confirm_clear_{mes_num}_{ano_selecionado}'] = False
                        st.rerun()

    # Na aba de Entradas do Mês
    with tab_entradas:
        st.header("💰 Entradas do Mês")
        
        # Formulário para adicionar entrada
        with st.form("form_entrada"):
            col1, col2, col3, col4 = st.columns([2, 3, 1.5, 1])
            
            with col1:
                valor_entrada = st.number_input("Valor", min_value=0.0, format="%.2f")
            
            with col2:
                descricao_entrada = st.text_input("Descrição")
            
            with col3:
                tipo_entrada = st.selectbox(
                    "Tipo",
                    options=["Salário", "Freelance", "Outros"]
                )
            
            with col4:
                st.write("")  # Espaço para alinhar
                if st.form_submit_button("Adicionar Entrada", use_container_width=True):
                    if valor_entrada > 0 and descricao_entrada:
                        adicionar_entrada(mes_num, ano_selecionado, valor_entrada, descricao_entrada, tipo_entrada)
                        st.success("✓ Entrada adicionada com sucesso!")
                        # Manter a seleção do mês atual
                        nome_mes_limpo = mes_selecionado.replace('✅ ', '').replace('⚪ ', '')
                        st.session_state['mes_manter_selecao'] = nome_mes_limpo
                        st.rerun()  # Atualizar indicadores visuais
                    else:
                        st.error("Por favor, preencha todos os campos.")

        # Mostrar entradas existentes
        entradas_existentes = obter_entradas(mes_num, ano_selecionado)
        if entradas_existentes:
            # Mostrar total em cima
            total_entradas = sum(e['valor'] for e in entradas_existentes)
            st.metric("Total de Entradas", formatar_valor(total_entradas))
            
            # Criar DataFrame para tabela organizada
            df_entradas = pd.DataFrame([{
                'Valor': formatar_valor(entrada['valor']),
                'Descrição': entrada['descricao'],
                'Tipo': entrada.get('tipo', 'Outros'),
                'Ações': f"del_entrada_{idx}"
            } for idx, entrada in enumerate(entradas_existentes)])
            
            # Mostrar tabela
            st.write("### Entradas Registradas")
            for idx, entrada in enumerate(entradas_existentes):
                col1, col2, col3, col4 = st.columns([1.5, 3, 1.5, 0.5])
                with col1:
                    st.write(formatar_valor(entrada['valor']))
                with col2:
                    st.write(entrada['descricao'])
                with col3:
                    st.write(entrada.get('tipo', 'Outros'))
                with col4:
                    if st.button("🗑️", key=f"del_entrada_{idx}", help="Deletar entrada"):
                        remover_entrada(
                            entrada['mes'],
                            entrada['ano'],
                            entrada['valor'],
                            entrada['descricao'],
                            entrada.get('tipo', 'Outros')
                        )
                        # Manter a seleção do mês atual
                        nome_mes_limpo = mes_selecionado.replace('✅ ', '').replace('⚪ ', '')
                        st.session_state['mes_manter_selecao'] = nome_mes_limpo
                        st.rerun()
                        
                # Linha fina entre itens
                if idx < len(entradas_existentes) - 1:
                    st.markdown("<hr style='margin: 0.5rem 0; border: 0.5px solid #ddd;'>", unsafe_allow_html=True)
        else:
            st.info("Nenhuma entrada registrada para este mês.")

    # Na aba de Análise
    with tab_analise:
        # Inicializar session_state para categoria aberta
        if 'categoria_aberta' not in st.session_state:
            st.session_state.categoria_aberta = None

        # Carregar categorias do arquivo
        categorias = carregar_categorias()

        # Botão para gerenciar classificações
        with st.expander("⚙️ Gerenciar Classificações"):
            tab1, tab2, tab3 = st.tabs(["Criar/Deletar Categorias", "Regras Automáticas", "Regras Existentes"])
            
            with tab1:
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.write("**Criar Nova Classificação**")
                    with st.form("nova_classificacao", clear_on_submit=True):
                        nova_cat = st.text_input("Nome da Nova Classificação")
                        if st.form_submit_button("Criar"):
                            if nova_cat:
                                categorias = carregar_categorias()
                                if nova_cat not in categorias:
                                    categorias.append(nova_cat)
                                    salvar_categorias(categorias)
                                    st.success(f"✓ Classificação '{nova_cat}' criada com sucesso!")
                                    time.sleep(0.5)
                                    st.rerun()
                                else:
                                    st.error("Esta classificação já existe!")
                
                with col2:
                    st.write("**Deletar Classificação**")
                    with st.form("deletar_classificacao", clear_on_submit=True):
                        if categorias:
                            cat_deletar = st.selectbox("Categoria para Deletar", options=categorias)
                            if st.form_submit_button("🗑️ Deletar", type="secondary"):
                                if remover_categoria(cat_deletar):
                                    st.success(f"✓ Classificação '{cat_deletar}' deletada com sucesso!")
                                    time.sleep(0.5)
                                    st.rerun()
                                else:
                                    st.error("Erro ao deletar classificação!")
                        else:
                            st.info("Nenhuma categoria disponível para deletar")
                            # Botão desabilitado quando não há categorias para deletar
                            st.form_submit_button("🗑️ Deletar", disabled=True)
            
            with tab2:
                st.write("**Criar Nova Regra Automática**")
                st.info("💡 Defina palavras-chave para classificar automaticamente suas transações")
                
                with st.form("nova_regra_auto", clear_on_submit=True):
                    col1, col2, col3 = st.columns([2, 2, 1])
                    
                    with col1:
                        palavra_chave = st.text_input("Palavra-chave", placeholder="ex: ifood, uber, netflix")
                    
                    with col2:
                        categoria_regra = st.selectbox("Classificar como:", options=categorias)
                    
                    with col3:
                        st.write("")  # Espaço para alinhamento
                        if st.form_submit_button("Adicionar Regra"):
                            if palavra_chave and categoria_regra:
                                if adicionar_regra_classificacao(palavra_chave, categoria_regra):
                                    st.success(f"✓ Regra criada: '{palavra_chave}' → {categoria_regra}")
                                    
                                    # Aplicar a regra imediatamente às transações existentes
                                    with st.spinner("Aplicando regra às transações existentes..."):
                                        resultado = reaplicar_regras_todas_transacoes()
                                        if resultado['atualizadas'] > 0:
                                            st.success(f"✓ Regra aplicada a {resultado['atualizadas']} transações!")
                                            
                                            # Mostrar exemplos de transações afetadas
                                            dados = carregar_dados()
                                            exemplos = []
                                            for fatura in dados.get('faturas', []):
                                                for transacao in fatura.get('transacoes', []):
                                                    if palavra_chave.lower() in transacao['descricao'].lower():
                                                        exemplos.append(transacao['descricao'])
                                                        if len(exemplos) >= 3:  # Mostrar até 3 exemplos
                                                            break
                                                    if len(exemplos) >= 3:
                                                        break
                                                
                                                if exemplos:
                                                    st.info(f"📋 Exemplos de transações afetadas: {', '.join(exemplos[:3])}")
                                                else:
                                                    st.info("ℹ️ Nenhuma transação existente foi afetada por esta regra")
                                    
                                    # Manter a seleção do mês atual
                                    nome_mes_limpo = mes_selecionado.replace('✅ ', '').replace('⚪ ', '')
                                    st.session_state['mes_manter_selecao'] = nome_mes_limpo
                                    
                                    time.sleep(0.5)
                                    st.rerun()
                                else:
                                    st.error("Erro ao criar regra!")
                            else:
                                st.error("Por favor, preencha todos os campos!")
                
                st.markdown("---")
                st.write("**Exemplo de uso:**")
                st.write("- Palavra-chave: `ifood` → Classificação: `Alimentação`")
                st.write("- Palavra-chave: `uber` → Classificação: `Transporte`")
                st.write("- Palavra-chave: `netflix` → Classificação: `Entretenimento`")
            
            with tab3:
                st.write("**Regras Automáticas Existentes**")
                regras = carregar_regras_classificacao()
                
                if regras:
                    st.write(f"Total de regras: {len(regras)}")
                    
                    for idx, regra in enumerate(regras):
                        col1, col2, col3 = st.columns([2, 2, 1])
                        
                        with col1:
                            st.write(f"**{regra['palavra_chave']}**")
                        
                        with col2:
                            st.write(f"→ {regra['categoria']}")
                        
                        with col3:
                            if st.button("🗑️", key=f"del_regra_{idx}", help="Deletar regra"):
                                if remover_regra_classificacao(regra['palavra_chave']):
                                    st.success(f"✓ Regra '{regra['palavra_chave']}' deletada!")
                                    time.sleep(0.5)
                                    st.rerun()
                        
                        if idx < len(regras) - 1:
                            st.markdown("<hr style='margin: 0.5rem 0; border: 0.5px solid #ddd;'>", unsafe_allow_html=True)
                else:
                    st.info("Nenhuma regra automática criada ainda.")
                    st.write("Use a aba 'Regras Automáticas' para criar sua primeira regra!")
                
                # Teste das regras - mostrar quantas transações seriam afetadas
                st.markdown("---")
                if st.button("🔍 Testar Regras nas Transações Atuais", use_container_width=True):
                    with st.spinner("Testando regras..."):
                        dados = carregar_dados()
                        regras = carregar_regras_classificacao()
                        classificacoes_manuais = carregar_classificacoes_manuais()
                        
                        if not regras:
                            st.warning("❌ Nenhuma regra criada ainda!")
                        else:
                            st.write("### Teste das Regras:")
                            
                            total_transacoes_afetadas = 0
                            total_transacoes_ignoradas = 0
                            
                            for regra in regras:
                                st.write(f"**Regra:** '{regra['palavra_chave']}' → {regra['categoria']}")
                                
                                # Contar transações que batem com esta regra
                                transacoes_encontradas = []
                                transacoes_ignoradas = []
                                
                                for fatura in dados.get('faturas', []):
                                    for transacao in fatura.get('transacoes', []):
                                        desc = transacao['descricao'].lower().strip()
                                        palavra = regra['palavra_chave'].lower().strip()
                                        
                                        if palavra in desc:
                                            # Verificar se é classificação manual (será preservada)
                                            if desc in classificacoes_manuais:
                                                transacoes_ignoradas.append({
                                                    'descricao': transacao['descricao'],
                                                    'categoria_atual': transacao.get('categoria', 'Não definida'),
                                                    'mes': fatura['mes'],
                                                    'ano': fatura['ano']
                                                })
                                            else:
                                                transacoes_encontradas.append({
                                                    'descricao': transacao['descricao'],
                                                    'categoria_atual': transacao.get('categoria', 'Não definida'),
                                                    'mes': fatura['mes'],
                                                    'ano': fatura['ano']
                                                })
                                
                                if transacoes_encontradas:
                                    st.success(f"✅ {len(transacoes_encontradas)} transações serão afetadas:")
                                    for i, t in enumerate(transacoes_encontradas[:3]):  # Mostrar apenas as 3 primeiras
                                        categoria_icon = "🔒" if t['categoria_atual'] == regra['categoria'] else "📝"
                                        st.write(f"  {categoria_icon} {t['descricao']} (atual: {t['categoria_atual']})")
                                    if len(transacoes_encontradas) > 3:
                                        st.write(f"  ... e mais {len(transacoes_encontradas) - 3} transações")
                                    total_transacoes_afetadas += len(transacoes_encontradas)
                                
                                if transacoes_ignoradas:
                                    st.info(f"🔒 {len(transacoes_ignoradas)} transações serão PRESERVADAS (classificação manual):")
                                    for i, t in enumerate(transacoes_ignoradas[:2]):  # Mostrar apenas as 2 primeiras
                                        st.write(f"  🔒 {t['descricao']} (manual: {t['categoria_atual']})")
                                    if len(transacoes_ignoradas) > 2:
                                        st.write(f"  ... e mais {len(transacoes_ignoradas) - 2} transações")
                                    total_transacoes_ignoradas += len(transacoes_ignoradas)
                                
                                if not transacoes_encontradas and not transacoes_ignoradas:
                                    st.warning(f"⚠️ Nenhuma transação encontrada com '{regra['palavra_chave']}'")
                                    st.write("   💡 Verifique se a palavra-chave está escrita corretamente")
                                
                                st.write("")
                            
                            # Resumo final
                            st.markdown("---")
                            st.write("### Resumo do Teste:")
                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric("Transações que serão atualizadas", total_transacoes_afetadas)
                            with col2:
                                st.metric("Transações preservadas (manuais)", total_transacoes_ignoradas)
                
                # Botão para reaplicar regras
                st.markdown("---")
                st.write("### Reaplicar Regras")
                st.info("🔒 **Importante:** Este botão preserva todas as classificações feitas manualmente (com o lápis). Apenas transações não editadas manualmente serão atualizadas.")
                
                if st.button("🔄 Reaplicar Regras a Todas as Transações", use_container_width=True):
                    with st.spinner("Reaplicando regras..."):
                        # Limpar cache para garantir que as regras mais recentes sejam carregadas
                        st.cache_data.clear()
                        
                        resultado = reaplicar_regras_todas_transacoes()
                        
                        # Mostrar resultado detalhado
                        if resultado['atualizadas'] > 0 or resultado['preservadas'] > 0:
                            st.success(f"✅ Reaplicação concluída!")
                            if resultado['atualizadas'] > 0:
                                st.success(f"📝 {resultado['atualizadas']} transações foram atualizadas com novas regras")
                            if resultado['preservadas'] > 0:
                                st.info(f"🔒 {resultado['preservadas']} transações preservadas (classificação manual)")
                                
                            # Mostrar quais regras foram aplicadas
                            regras = carregar_regras_classificacao()
                            if regras:
                                st.write("**Regras aplicadas:**")
                                for regra in regras:
                                    st.write(f"• '{regra['palavra_chave']}' → {regra['categoria']}")
                        else:
                            st.info("ℹ️ Nenhuma transação foi modificada - todas já estão classificadas corretamente!")
                        
                        # Manter a seleção do mês atual
                        nome_mes_limpo = mes_selecionado.replace('✅ ', '').replace('⚪ ', '')
                        st.session_state['mes_manter_selecao'] = nome_mes_limpo
                        st.rerun()
        
        # Carregar dados
        dados = carregar_dados()
        faturas = dados.get('faturas', [])
        
        # Filtrar fatura atual e anterior
        fatura_atual = None
        fatura_anterior = None
        mes_anterior = mes_num - 1 if mes_num > 1 else 12
        ano_anterior = ano_selecionado if mes_num > 1 else ano_selecionado - 1
        
        for fatura in faturas:
            if fatura['mes'] == mes_num and fatura['ano'] == ano_selecionado:
                fatura_atual = fatura
            elif fatura['mes'] == mes_anterior and fatura['ano'] == ano_anterior:
                fatura_anterior = fatura
        
        if not fatura_atual:
            st.warning("Nenhuma fatura encontrada para este mês.")
            st.stop()
        
        # Calcular dados para métricas
        df = pd.DataFrame(fatura_atual['transacoes'])
        
        # Atualizar categorias com as já salvas
        for i, transacao in enumerate(fatura_atual['transacoes']):
            if 'categoria' in transacao:
                df.loc[i, 'categoria'] = transacao['categoria']
            else:
                df.loc[i, 'categoria'] = classificar_transacao(transacao['descricao'])
        
        # Filtrar transações com categoria ENTRADA (não devem aparecer na análise)
        df = df[df['categoria'] != 'ENTRADA']
        
        # Calcular totais por categoria (filtrar ENTRADA se existir)
        totais_categoria = df.groupby('categoria')['valor'].sum().sort_values(ascending=False)
        
        # Remover categoria ENTRADA se existir (não deve aparecer na análise)
        if 'ENTRADA' in totais_categoria.index:
            totais_categoria = totais_categoria.drop('ENTRADA')

        # Calcular total geral
        total_atual = totais_categoria.sum()
        
        # Calcular entradas do mês atual
        entradas_mes = obter_entradas(mes_num, ano_selecionado)
        total_entradas = sum(e['valor'] for e in entradas_mes)
        
        # Calcular total anterior
        total_anterior = 0
        if fatura_anterior:
            total_anterior = sum(t['valor'] for t in fatura_anterior['transacoes'])
        
        # Calcular variação
        variacao = total_atual - total_anterior
        percentual_variacao = (variacao / total_anterior * 100) if total_anterior > 0 else 0
        
        # Mostrar métricas
        st.write("### Resumo do Mês")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Gasto Total",
                formatar_valor(total_atual)
            )
        
        with col2:
            if total_entradas > 0:
                percentual_utilizado = (total_atual / total_entradas) * 100
                st.metric(
                    "% Utilizado das Entradas",
                    f"{percentual_utilizado:.1f}%"
                )
            else:
                st.metric(
                    "% Utilizado das Entradas",
                    "Sem entradas registradas"
                )
        
        with col3:
            if fatura_anterior:
                # Criar texto com cor baseada na variação
                if variacao > 0:
                    # Vermelho se gastou mais
                    cor_html = "color: red;"
                    sinal = "+"
                elif variacao < 0:
                    # Verde se gastou menos
                    cor_html = "color: green;"
                    sinal = ""
                else:
                    cor_html = "color: gray;"
                    sinal = ""
                
                st.metric(
                    "Variação Mensal",
                    f"{sinal}{percentual_variacao:.1f}%"
                )
                
                # Adicionar explicação colorida
                st.markdown(
                    f"<div style='{cor_html} font-size: 12px; text-align: center;'>"
                    f"{'Gasto maior' if variacao > 0 else 'Gasto menor' if variacao < 0 else 'Igual'} "
                    f"({formatar_valor(abs(variacao))})"
                    f"</div>",
                    unsafe_allow_html=True
                )
            else:
                st.metric(
                    "Variação Mensal",
                    "Sem dados anteriores"
                )
        
        # Mostrar detalhamento por categoria
        st.write("### Detalhamento por Categoria")

        # Mostrar transações por categoria
        for categoria, total in totais_categoria.items():
            # Usar o estado para controlar se o expander está aberto
            is_open = st.session_state.categoria_aberta == categoria
            with st.expander(
                f"📁 {categoria} - {formatar_valor(total)} ({(total/total_atual*100):.1f}%)",
                expanded=is_open
            ):
                gastos_categoria = df[df['categoria'] == categoria].sort_values('valor', ascending=False)
                
                # Criar container para reduzir espaçamento
                with st.container():
                    for idx, transacao in gastos_categoria.iterrows():
                        # Layout mais compacto
                        cols = st.columns([1, 3, 2, 0.5, 0.5, 0.5])
                        
                        with cols[0]:
                            st.write(transacao['data'])
                        
                        with cols[1]:
                            st.write(transacao['descricao'])
                        
                        with cols[2]:
                            st.write(formatar_valor(transacao['valor']))
                        
                        with cols[3]:
                            if any(g['descricao'] == transacao['descricao'] and abs(g['valor'] - transacao['valor']) < 0.01 for g in dados.get('gastos_fixos', [])):
                                st.write("📌")
                        
                        with cols[4]:
                            if st.button("✏️", key=f"edit_{idx}"):
                                st.session_state[f'editing_{idx}'] = True
                                # Salvar a categoria atual para manter aberta
                                st.session_state.categoria_aberta = categoria
                        
                        with cols[5]:
                            if st.button("🗑️", key=f"del_{idx}"):
                                # Salvar a categoria atual para manter aberta
                                st.session_state.categoria_aberta = categoria
                                remover_transacao(
                                    fatura_atual['mes'],
                                    fatura_atual['ano'],
                                    transacao['descricao'],
                                    transacao['valor']
                                )
                                st.success("✓ Transação excluída com sucesso!")
                                time.sleep(0.5)  # Pequena pausa para mostrar a mensagem
                                st.rerun()
                        
                        # Se o botão de edição foi clicado, mostrar o formulário
                        if st.session_state.get(f'editing_{idx}', False):
                            with st.form(f"form_transacao_{idx}", clear_on_submit=True):
                                # Garantir que a categoria existe na lista
                                categoria_atual = transacao['categoria']
                                try:
                                    index_categoria = categorias.index(categoria_atual)
                                except ValueError:
                                    # Se a categoria não existir, adicionar à lista e usar como índice
                                    categorias.append(categoria_atual)
                                    salvar_categorias(categorias)
                                    index_categoria = len(categorias) - 1
                                
                                nova_categoria = st.selectbox(
                                    "Categoria",
                                    options=categorias,  # Usar categorias do arquivo
                                    key=f"cat_{idx}",
                                    index=index_categoria
                                )
                                
                                is_fixo = st.checkbox("Marcar como gasto fixo", key=f"fix_{idx}")
                                
                                col1, col2 = st.columns([1, 1])
                                with col1:
                                    if st.form_submit_button("💾 Salvar"):
                                        try:
                                            # Atualizar categoria na transação
                                            fatura_atual['transacoes'][idx]['categoria'] = nova_categoria
                                            
                                            # IMPORTANTE: Salvar como classificação MANUAL (não será sobrescrita pelo botão reaplicar)
                                            atualizar_classificacao_manual(transacao['descricao'], nova_categoria)
                                            
                                            # Atualizar gastos fixos
                                            if is_fixo:
                                                gasto_fixo = {
                                                    'descricao': transacao['descricao'],
                                                    'valor': transacao['valor'],
                                                    'categoria': nova_categoria,
                                                    'data_adicao': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                                }
                                                if not any(g['descricao'] == transacao['descricao'] and abs(g['valor'] - transacao['valor']) < 0.01 for g in dados['gastos_fixos']):
                                                    dados['gastos_fixos'].append(gasto_fixo)
                                            else:
                                                dados['gastos_fixos'] = [
                                                    g for g in dados['gastos_fixos']
                                                    if not (g['descricao'] == transacao['descricao'] and abs(g['valor'] - transacao['valor']) < 0.01)
                                                ]
                                            
                                            # Atualizar fatura no histórico
                                            for i, f in enumerate(dados['faturas']):
                                                if f['mes'] == mes_num and f['ano'] == ano_selecionado:
                                                    dados['faturas'][i] = fatura_atual
                                                    break
                                            
                                            # Salvar todas as alterações
                                            salvar_dados(dados)
                                            st.session_state[f'editing_{idx}'] = False
                                            # Manter a categoria aberta após salvar
                                            st.session_state.categoria_aberta = categoria
                                            st.success("✓ Alterações salvas como classificação manual!")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Erro ao salvar alterações: {str(e)}")
                                
                                with col2:
                                    if st.form_submit_button("❌ Cancelar"):
                                        st.session_state[f'editing_{idx}'] = False
                                        # Manter a categoria aberta após cancelar
                                        st.session_state.categoria_aberta = categoria
                                        st.rerun()
                        
                        st.markdown("---")

        # Gráfico de Comparação por Categoria
        # Preparar dados para o gráfico
        meses_dados = {}
        categorias_todas = set()
        
        # Coletar dados de todas as faturas
        for fatura in faturas:
            mes_ano = f"{list(mes_options.keys())[int(fatura['mes'])-1]}/{fatura['ano']}"
            meses_dados[mes_ano] = {'mes': fatura['mes'], 'ano': fatura['ano']}
            
            # Processar transações da fatura
            df_fatura = pd.DataFrame(fatura['transacoes'])
            if not df_fatura.empty:
                # Aplicar classificação
                for i, transacao in enumerate(fatura['transacoes']):
                    if 'categoria' in transacao:
                        df_fatura.loc[i, 'categoria'] = transacao['categoria']
                    else:
                        df_fatura.loc[i, 'categoria'] = classificar_transacao(transacao['descricao'])
                
                # Filtrar transações com categoria ENTRADA
                df_fatura = df_fatura[df_fatura['categoria'] != 'ENTRADA']
                
                # Se não sobrou nenhuma transação, pular
                if df_fatura.empty:
                    continue
                
                # Calcular totais por categoria
                totais_fatura = df_fatura.groupby('categoria')['valor'].sum()
                meses_dados[mes_ano]['categorias'] = totais_fatura.to_dict()
                
                # Adicionar categorias (excluindo ENTRADA)
                categorias_grafico = [cat for cat in totais_fatura.index.tolist() if cat != 'ENTRADA']
                categorias_todas.update(categorias_grafico)
        
        # Remover ENTRADA das categorias_todas como medida de segurança
        categorias_todas.discard('ENTRADA')
        
        # Ordenar meses cronologicamente
        meses_ordenados = sorted(meses_dados.keys(), key=lambda x: (meses_dados[x]['ano'], meses_dados[x]['mes']))
        
        # Preparar dados para o gráfico
        if len(meses_ordenados) >= 2:  # Só mostrar se tiver pelo menos 2 meses
            fig = go.Figure()
            
            # Tons de roxo para os meses
            cores_roxo = ['#9966CC', '#8A2BE2', '#6A0DAD', '#4B0082', '#663399', '#7B68EE', '#9370DB', '#BA55D3']
            
            # Criar barras para cada mês
            for i, mes in enumerate(meses_ordenados):
                valores = []
                # Filtrar categorias para remover ENTRADA
                categorias_ordenadas = sorted([cat for cat in categorias_todas if cat != 'ENTRADA'])
                
                for categoria in categorias_ordenadas:
                    valor = meses_dados[mes].get('categorias', {}).get(categoria, 0)
                    valores.append(valor)
                
                fig.add_trace(go.Bar(
                    name=mes,
                    x=categorias_ordenadas,
                    y=valores,
                    text=[formatar_valor(v) if v > 0 else '' for v in valores],
                    textposition='auto',
                    textfont=dict(color='white'),
                    marker_color=cores_roxo[i % len(cores_roxo)]
                ))
            
            fig.update_layout(
                title="Comparação de Gastos por Categoria",
                xaxis_title="Categoria",
                yaxis_title="Valor (R$)",
                yaxis=dict(range=[0, 6000]),
                barmode='group',
                height=600,
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📊 Gráfico de comparação será exibido quando houver dados de pelo menos 2 meses.")

    # Na aba de Parcelas Futuras
    with tab_parcelas:
        st.header("🔄 Parcelas Futuras")
        
        # Carregar dados
        dados = carregar_dados()
        faturas = dados.get('faturas', [])
        
        # Identificar parcelas em todas as faturas
        todas_parcelas = {}  # Dicionário para agrupar parcelas por descrição
        for fatura in faturas:
            for transacao in fatura['transacoes']:
                descricao = transacao['descricao'].lower()
                
                # Pular transações do 99app e antecipadas para evitar detecção incorreta de parcelas
                if any(termo in descricao for termo in ['99app', '99 app', '99app *99app', 'antecipada']):
                    continue
                
                # Procurar padrões de parcelas usando regex mais específica
                # Aceita: "1/12", "01/12", "1 de 12", "parcela 1 de 12", etc.
                padrao_parcela = re.search(r'(?:parcela\s+)?(\d{1,2})(?:\s*[/de]\s*|\s+de\s+)(\d{1,2})', descricao)
                if padrao_parcela:
                    parcela_atual = int(padrao_parcela.group(1))
                    total_parcelas = int(padrao_parcela.group(2))
                    
                    # Validações para evitar falsos positivos
                    if (parcela_atual < 1 or parcela_atual > total_parcelas or 
                        total_parcelas < 2 or total_parcelas > 60):
                        continue
                    
                    # Criar chave única para a compra (removendo o padrão de parcela)
                    chave = re.sub(r'(?:parcela\s+)?\d{1,2}(?:\s*[/de]\s*|\s+de\s+)\d{1,2}', '', descricao).strip()
                    
                    if chave not in todas_parcelas:
                        todas_parcelas[chave] = {
                            'descricao': chave,
                            'valor_parcela': transacao['valor'],
                            'total_parcelas': total_parcelas,
                            'parcelas_vistas': {parcela_atual},
                            'primeira_parcela': {
                                'mes': fatura['mes'],
                                'ano': fatura['ano']
                            }
                        }
                    else:
                        todas_parcelas[chave]['parcelas_vistas'].add(parcela_atual)
        
        # Calcular parcelas futuras
        parcelas_futuras = {}
        mes_atual = datetime.now().month
        ano_atual = datetime.now().year
        
        for compra in todas_parcelas.values():
            # Calcular mês/ano da primeira parcela
            data_primeira = date(compra['primeira_parcela']['ano'], 
                               compra['primeira_parcela']['mes'], 1)
            
            # Para cada parcela que falta
            for n_parcela in range(1, compra['total_parcelas'] + 1):
                if n_parcela not in compra['parcelas_vistas']:
                    # Calcular data da parcela
                    meses_a_adicionar = n_parcela - 1
                    data_parcela = data_primeira + relativedelta(months=meses_a_adicionar)
                    
                    # Se é uma parcela futura
                    if data_parcela >= date(ano_atual, mes_atual, 1):
                        chave_mes = (data_parcela.year, data_parcela.month)
                        if chave_mes not in parcelas_futuras:
                            parcelas_futuras[chave_mes] = []
                        
                        parcelas_futuras[chave_mes].append({
                            'descricao': compra['descricao'],
                            'valor': compra['valor_parcela'],
                            'parcela': n_parcela,
                            'total_parcelas': compra['total_parcelas']
                        })
        
        # Mostrar parcelas futuras agrupadas por mês
        for (ano, mes), parcelas in sorted(parcelas_futuras.items()):
            mes_nome = list(mes_options.keys())[mes-1]
            st.subheader(f"{mes_nome}/{ano}")
            
            total_mes = sum(p['valor'] for p in parcelas)
            st.markdown(f"**Total do Mês:** {formatar_valor(total_mes)}")
            
            for parcela in parcelas:
                col1, col2, col3 = st.columns([3, 2, 2])
                with col1:
                    st.write(parcela['descricao'])
                with col2:
                    st.write(formatar_valor(parcela['valor']))
                with col3:
                    st.write(f"Parcela {parcela['parcela']}/{parcela['total_parcelas']}")
                st.markdown("---")

    # Na aba de Gastos Fixos
    with tab_fixos:
        st.header("📌 Gastos Fixos")
        
        # Carregar dados
        dados = carregar_dados()
        gastos_fixos = dados.get('gastos_fixos', [])
        
        # Formulário para adicionar gasto fixo
        with st.form("form_gasto_fixo"):
            col1, col2, col3, col4 = st.columns([2, 3, 1.5, 1])
            
            with col1:
                valor = st.number_input("Valor Mensal", min_value=0.0, step=0.01, format="%.2f")
            
            with col2:
                descricao = st.text_input("Descrição")
            
            with col3:
                categoria = st.selectbox(
                    "Categoria",
                                                options=["Alimentação", "Transporte", "Entretenimento", "Self Care", "Roupas", "Outros"]
                )
            
            with col4:
                st.write("")  # Espaço para alinhar
                if st.form_submit_button("Adicionar Gasto Fixo", use_container_width=True):
                    if valor > 0 and descricao:
                        novo_gasto = {
                            'descricao': descricao,
                            'valor': valor,
                            'categoria': categoria,
                            'data_adicao': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        dados['gastos_fixos'].append(novo_gasto)
                        salvar_dados(dados)
                        st.success("✓ Gasto fixo adicionado com sucesso!")
                        # Manter a seleção do mês atual
                        nome_mes_limpo = mes_selecionado.replace('✅ ', '').replace('⚪ ', '')
                        st.session_state['mes_manter_selecao'] = nome_mes_limpo
                        st.rerun()  # Atualizar indicadores visuais
                    else:
                        st.error("Por favor, preencha todos os campos.")
        
        # Mostrar gastos fixos existentes
        if gastos_fixos:
            # Mostrar total em cima
            total_fixo = sum(g['valor'] for g in gastos_fixos)
            st.metric("Total Mensal", formatar_valor(total_fixo))
            
            st.write("### Gastos Fixos Cadastrados")
            for idx, gasto in enumerate(gastos_fixos):
                col1, col2, col3, col4 = st.columns([1.5, 3, 1.5, 0.5])
                with col1:
                    st.write(formatar_valor(gasto['valor']))
                with col2:
                    st.write(gasto['descricao'])
                with col3:
                    st.write(gasto['categoria'])
                with col4:
                    if st.button("🗑️", key=f"del_fixo_{idx}", help="Deletar gasto fixo"):
                        dados['gastos_fixos'].remove(gasto)
                        salvar_dados(dados)
                        # Manter a seleção do mês atual
                        nome_mes_limpo = mes_selecionado.replace('✅ ', '').replace('⚪ ', '')
                        st.session_state['mes_manter_selecao'] = nome_mes_limpo
                        st.rerun()
                        
                # Linha fina entre itens
                if idx < len(gastos_fixos) - 1:
                    st.markdown("<hr style='margin: 0.5rem 0; border: 0.5px solid #ddd;'>", unsafe_allow_html=True)
        else:
            st.info("Nenhum gasto fixo cadastrado.")

    # Na aba de Histórico
    with tab_historico:
        st.header("📊 Histórico de Gastos")
        
        # Carregar dados históricos
        dados = carregar_dados()
        faturas = dados.get('faturas', [])
        
        if not faturas:
            st.warning("Nenhum dado histórico encontrado.")
            st.stop()
        
        # Criar DataFrame com histórico
        historico = []
        for fatura in faturas:
            # Usar nomes de mês limpos (sem checks) para o histórico
            mes_nome = list(mes_options_base.keys())[int(fatura['mes'])-1]
            mes_ano = f"{mes_nome}/{fatura['ano']}"
            total = sum(t['valor'] for t in fatura['transacoes'])
            historico.append({
                'Mês': mes_ano,
                'Total': total,
                'mes_num': fatura['mes'],
                'ano': fatura['ano']
            })
        
        df_historico = pd.DataFrame(historico)
        df_historico = df_historico.sort_values(by=['ano', 'mes_num'])
        
        # Criar gráfico de linha
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_historico['Mês'],
            y=df_historico['Total'],
            mode='lines+markers+text',
            text=df_historico['Total'].apply(lambda x: formatar_valor(x)),
            textposition='top center',
            line=dict(color='#4B0082', width=2),
            marker=dict(color='#9370DB', size=8)
        ))
        
        fig.update_layout(
            title='Evolução dos Gastos',
            xaxis_title='Mês',
            yaxis_title='Valor Total (R$)',
            showlegend=False,
            height=400,
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(color='#4B0082'),
            yaxis=dict(
                range=[4000, 10000],
                tickformat=',.0f',
                tickprefix='R$ '
            )
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Tabela de histórico
        df_display = df_historico[['Mês', 'Total']].copy()
        df_display['Total'] = df_display['Total'].apply(formatar_valor)
        st.dataframe(
            df_display,
            hide_index=True,
            column_config={
                "Mês": st.column_config.TextColumn("Mês"),
                "Total": st.column_config.TextColumn("Total", width="small")
            }
        )

    # Estilo para tabelas mais finas e botões menores
    st.markdown("""
<style>
    .dataframe {
        font-size: 12px;
    }
    .dataframe td, .dataframe th {
        padding: 4px !important;
        border: 1px solid #ddd !important;
    }
    div[data-testid="stHorizontalBlock"] {
        gap: 0.5rem !important;
    }
    div[data-testid="column"] {
        padding: 0 !important;
    }
    hr {
        margin: 0.5rem 0 !important;
        border-color: #ddd !important;
    }
    /* Botões menores */
    .stButton > button {
        height: 2.5rem !important;
        font-size: 0.875rem !important;
        padding: 0.25rem 0.75rem !important;
    }
    /* Botões de deletar ainda menores */
    button[title="Deletar entrada"], button[title="Deletar gasto fixo"] {
        height: 2rem !important;
        width: 2rem !important;
        font-size: 1rem !important;
        padding: 0 !important;
        min-width: 2rem !important;
    }
    /* Espaçamento entre linhas das tabelas */
    .block-container .element-container {
        margin-bottom: 0.5rem !important;
    }
    /* Linhas de separação mais sutis */
    .separator-line {
        border: none;
        height: 1px;
        background-color: #e0e0e0;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True) 