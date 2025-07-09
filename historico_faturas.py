import json
import os
from datetime import datetime
import pandas as pd
import re

HISTORICO_FILE = 'dados_historico.json'

def extrair_info_parcelas(descricao):
    """Extrai informações de parcelas da descrição"""
    padrao = r'(\d+)/(\d+)'
    match = re.search(padrao, descricao)
    if match:
        parcela_atual = int(match.group(1))
        total_parcelas = int(match.group(2))
        return parcela_atual, total_parcelas
    return None, None

def calcular_parcelas_futuras(transacao, mes_atual, ano_atual):
    """Calcula as parcelas futuras de uma transação"""
    parcela_atual, total_parcelas = extrair_info_parcelas(transacao['Descrição'])
    if not parcela_atual or not total_parcelas:
        return []
    
    parcelas_futuras = []
    valor_parcela = transacao['Valor']
    mes = mes_atual
    ano = ano_atual
    
    for i in range(parcela_atual + 1, total_parcelas + 1):
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1
            
        parcelas_futuras.append({
            'mes': mes,
            'ano': ano,
            'parcela': i,
            'total_parcelas': total_parcelas,
            'valor': valor_parcela,
            'descricao': transacao['Descrição'],
            'categoria': transacao['Categoria']
        })
    
    return parcelas_futuras

def carregar_historico():
    """Carrega o histórico de faturas do arquivo JSON"""
    if os.path.exists(HISTORICO_FILE):
        try:
            with open(HISTORICO_FILE, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                if 'gastos_fixos' not in dados:
                    dados['gastos_fixos'] = []
                return dados
        except:
            return {'faturas': {}, 'entradas': {}, 'gastos_fixos': []}
    return {'faturas': {}, 'entradas': {}, 'gastos_fixos': []}

def salvar_historico(dados):
    """Salva o histórico de faturas no arquivo JSON"""
    if 'gastos_fixos' not in dados:
        dados['gastos_fixos'] = []
    with open(HISTORICO_FILE, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def limpar_historico():
    """Limpa todo o histórico de faturas"""
    if os.path.exists(HISTORICO_FILE):
        os.remove(HISTORICO_FILE)
    return {'faturas': {}, 'entradas': {}}

def limpar_fatura(mes, ano):
    """Remove uma fatura específica do histórico"""
    historico = carregar_historico()
    periodo = f"{ano}-{mes:02d}"
    if periodo in historico['faturas']:
        del historico['faturas'][periodo]
        salvar_historico(historico)
    return historico

def adicionar_fatura(df, mes, ano):
    """Adiciona uma nova fatura ao histórico"""
    historico = carregar_historico()
    
    # Criar chave única para o mês/ano
    periodo = f"{ano}-{mes:02d}"
    
    # Preparar dados para salvar
    resumo_categorias = df.groupby('Categoria')['Valor'].sum().round(2).to_dict()
    total_gasto = df['Valor'].sum().round(2)
    
    # Converter DataFrame para lista de dicionários
    transacoes = df.to_dict('records')
    
    # Calcular parcelas futuras
    todas_parcelas_futuras = []
    for transacao in transacoes:
        parcelas_futuras = calcular_parcelas_futuras(transacao, mes, ano)
        todas_parcelas_futuras.extend(parcelas_futuras)
    
    # Dados da fatura
    dados_fatura = {
        'total_gasto': total_gasto,
        'gastos_por_categoria': resumo_categorias,
        'transacoes': transacoes,
        'parcelas_futuras': todas_parcelas_futuras,
        'data_processamento': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Adicionar ao histórico
    historico['faturas'][periodo] = dados_fatura
    
    # Salvar histórico atualizado
    salvar_historico(historico)
    return historico

def obter_parcelas_futuras(mes_atual, ano_atual):
    """Obtém todas as parcelas futuras a partir do mês atual"""
    historico = carregar_historico()
    todas_parcelas = []
    
    # Coletar todas as parcelas futuras de todas as faturas
    for periodo, dados in historico['faturas'].items():
        if 'parcelas_futuras' in dados:
            for parcela in dados['parcelas_futuras']:
                # Verificar se a parcela é para um mês futuro
                if (parcela['ano'] > ano_atual) or \
                   (parcela['ano'] == ano_atual and parcela['mes'] >= mes_atual):
                    todas_parcelas.append(parcela)
    
    # Ordenar por data
    todas_parcelas.sort(key=lambda x: (x['ano'], x['mes'], x['descricao']))
    return todas_parcelas

def calcular_total_parcelas_futuras(mes_atual, ano_atual):
    """Calcula o total de parcelas futuras por mês"""
    parcelas = obter_parcelas_futuras(mes_atual, ano_atual)
    totais_mes = {}
    
    for parcela in parcelas:
        periodo = f"{parcela['ano']}-{parcela['mes']:02d}"
        if periodo not in totais_mes:
            totais_mes[periodo] = {
                'total': 0,
                'parcelas': []
            }
        totais_mes[periodo]['total'] += parcela['valor']
        totais_mes[periodo]['parcelas'].append(parcela)
    
    return totais_mes

def adicionar_entradas(mes, ano, entradas):
    """Adiciona ou atualiza as entradas de um mês
    
    Args:
        mes (int): Mês das entradas
        ano (int): Ano das entradas
        entradas (list): Lista de dicionários com as entradas do mês
            Cada entrada deve ter:
            - valor (float): Valor da entrada
            - descricao (str): Descrição da entrada
            - tipo (str): 'fixo' para salário fixo ou 'extra' para renda extra
    """
    historico = carregar_historico()
    
    # Criar chave única para o mês/ano
    periodo = f"{ano}-{mes:02d}"
    
    # Calcular totais
    total_fixo = sum(entrada['valor'] for entrada in entradas if entrada['tipo'] == 'fixo')
    total_extra = sum(entrada['valor'] for entrada in entradas if entrada['tipo'] == 'extra')
    
    # Dados das entradas
    dados_entradas = {
        'entradas': entradas,
        'total_fixo': total_fixo,
        'total_extra': total_extra,
        'total': total_fixo + total_extra,
        'data_atualizacao': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Adicionar ao histórico
    if 'entradas' not in historico:
        historico['entradas'] = {}
    
    historico['entradas'][periodo] = dados_entradas
    salvar_historico(historico)
    return historico

def limpar_entradas(mes, ano):
    """Remove as entradas de um mês específico"""
    historico = carregar_historico()
    periodo = f"{ano}-{mes:02d}"
    if 'entradas' in historico and periodo in historico['entradas']:
        del historico['entradas'][periodo]
        salvar_historico(historico)
    return historico

def obter_entradas(mes, ano):
    """Obtém as entradas de um mês específico"""
    historico = carregar_historico()
    periodo = f"{ano}-{mes:02d}"
    
    if 'entradas' in historico and periodo in historico['entradas']:
        return historico['entradas'][periodo]
    return None

def obter_fatura_anterior(mes_atual, ano_atual):
    """Obtém os dados da fatura do mês anterior"""
    historico = carregar_historico()
    
    # Calcular mês anterior
    mes_anterior = 12 if mes_atual == 1 else mes_atual - 1
    ano_anterior = ano_atual - 1 if mes_atual == 1 else ano_atual
    
    periodo_anterior = f"{ano_anterior}-{mes_anterior:02d}"
    return historico['faturas'].get(periodo_anterior, None)

def calcular_variacao(valor_atual, valor_anterior):
    """Calcula a variação percentual entre dois valores"""
    if not valor_anterior:
        return None
    variacao = ((valor_atual - valor_anterior) / valor_anterior) * 100
    return variacao

def formatar_variacao(variacao):
    """Formata a variação para exibição com seta"""
    if variacao is None:
        return "Sem histórico"
    
    if variacao > 0:
        return f"↑ +{variacao:.1f}%"
    elif variacao < 0:
        return f"↓ {variacao:.1f}%"
    return "= 0%"

def verificar_fatura_existe(mes, ano):
    """Verifica se já existe uma fatura para o mês/ano especificado"""
    historico = carregar_historico()
    periodo = f"{ano}-{mes:02d}"
    return periodo in historico['faturas'] 

def adicionar_gasto_fixo(transacao):
    """Adiciona uma transação à lista de gastos fixos"""
    historico = carregar_historico()
    
    # Verificar se já existe
    for gasto in historico['gastos_fixos']:
        # Normalizar as strings para comparação
        desc_gasto = gasto['descricao'].lower().strip()
        desc_transacao = transacao['descricao'].lower().strip()
        
        # Verificar se uma descrição contém a outra
        if (desc_gasto in desc_transacao or desc_transacao in desc_gasto) and \
           abs(gasto['valor'] - transacao['valor']) < 0.01:  # Comparação com tolerância para float
            # Atualizar categoria se necessário
            if gasto['categoria'] != transacao['categoria']:
                gasto['categoria'] = transacao['categoria']
                salvar_historico(historico)
            return historico
    
    # Adicionar novo gasto fixo
    gasto_fixo = {
        'descricao': transacao['descricao'],
        'valor': transacao['valor'],
        'categoria': transacao['categoria'],
        'data_adicao': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    historico['gastos_fixos'].append(gasto_fixo)
    salvar_historico(historico)
    return historico

def remover_gasto_fixo(descricao, valor):
    """Remove uma transação da lista de gastos fixos"""
    historico = carregar_historico()
    historico['gastos_fixos'] = [
        gasto for gasto in historico['gastos_fixos']
        if not ((gasto['descricao'].lower().strip() in descricao.lower().strip() or 
                descricao.lower().strip() in gasto['descricao'].lower().strip()) and 
                abs(gasto['valor'] - valor) < 0.01)  # Comparação com tolerância para float
    ]
    salvar_historico(historico)
    return historico

def obter_gastos_fixos():
    """Retorna a lista de gastos fixos"""
    historico = carregar_historico()
    return historico.get('gastos_fixos', [])

def calcular_total_gastos_fixos():
    """Calcula o total dos gastos fixos"""
    gastos_fixos = obter_gastos_fixos()
    return sum(gasto['valor'] for gasto in gastos_fixos)

def obter_historico_gastos_mensais():
    """Retorna um histórico dos gastos totais por mês"""
    historico = carregar_historico()
    gastos_mensais = []
    
    for periodo, dados in historico['faturas'].items():
        ano, mes = periodo.split('-')
        gastos_mensais.append({
            'periodo': periodo,
            'ano': int(ano),
            'mes': int(mes),
            'total': dados['total_gasto']
        })
    
    # Ordenar por data
    gastos_mensais.sort(key=lambda x: (x['ano'], x['mes']))
    return gastos_mensais 