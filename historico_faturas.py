import json
import os
import streamlit as st
from pathlib import Path

def get_user_data_file():
    """Retorna o caminho do arquivo de dados do usuário atual"""
    if 'user_data_dir' not in st.session_state:
        st.session_state['user_data_dir'] = 'data/default'
    user_dir = Path(st.session_state['user_data_dir'])
    return user_dir / 'faturas.json'

def carregar_dados():
    """Carrega os dados do arquivo JSON do usuário"""
    arquivo = get_user_data_file()
    if not arquivo.exists():
        return {'faturas': [], 'gastos_fixos': []}
    
    with open(arquivo) as f:
        return json.load(f)

def salvar_dados(dados):
    """Salva os dados no arquivo JSON do usuário"""
    arquivo = get_user_data_file()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    
    with open(arquivo, 'w') as f:
        json.dump(dados, f, indent=4)

def adicionar_fatura(fatura):
    """Adiciona uma nova fatura ao histórico"""
    dados = carregar_dados()
    dados['faturas'].append(fatura)
    salvar_dados(dados)

def obter_fatura_anterior(mes_atual):
    """Obtém a fatura do mês anterior"""
    dados = carregar_dados()
    for fatura in dados['faturas']:
        if fatura['mes'] == mes_atual:
            return fatura
    return None

def calcular_variacao(valor_atual, valor_anterior):
    """Calcula a variação percentual entre dois valores"""
    if not valor_anterior:
        return 0
    return ((valor_atual - valor_anterior) / valor_anterior) * 100

def formatar_variacao(variacao):
    """Formata a variação percentual para exibição"""
    if variacao > 0:
        return f"↑ {variacao:.1f}%"
    elif variacao < 0:
        return f"↓ {abs(variacao):.1f}%"
    return "="

def limpar_historico():
    """Limpa todo o histórico de faturas"""
    salvar_dados({'faturas': [], 'gastos_fixos': []})

def limpar_fatura(mes):
    """Remove uma fatura específica do histórico"""
    dados = carregar_dados()
    dados['faturas'] = [f for f in dados['faturas'] if f['mes'] != mes]
    salvar_dados(dados)

def adicionar_gasto_fixo(gasto):
    """Adiciona um novo gasto fixo"""
    dados = carregar_dados()
    if 'gastos_fixos' not in dados:
        dados['gastos_fixos'] = []
    dados['gastos_fixos'].append(gasto)
    salvar_dados(dados)

def remover_gasto_fixo(descricao, valor):
    """Remove um gasto fixo"""
    dados = carregar_dados()
    dados['gastos_fixos'] = [g for g in dados['gastos_fixos'] 
                            if not (g['descricao'] == descricao and abs(float(g['valor']) - valor) < 0.01)]
    salvar_dados(dados)

def obter_gastos_fixos():
    """Retorna a lista de gastos fixos"""
    return carregar_dados().get('gastos_fixos', []) 