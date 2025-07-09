import streamlit as st
import pandas as pd
import pdfplumber
import plotly.express as px
import plotly.graph_objects as go
import re
from datetime import datetime
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
    
    # Título principal com nome do usuário
    st.markdown(f"<h1 class='main-header'>Análise Faturas Nubank - {name}</h1>", unsafe_allow_html=True)
    
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

    # Seleção do mês
    mes_options = {
        'Janeiro': 1, 'Fevereiro': 2, 'Março': 3, 'Abril': 4,
        'Maio': 5, 'Junho': 6, 'Julho': 7, 'Agosto': 8,
        'Setembro': 9, 'Outubro': 10, 'Novembro': 11, 'Dezembro': 12
    }

    col1, col2 = st.columns([2, 1])
    with col1:
        mes_selecionado = st.selectbox(
            "Selecione o Mês",
            options=list(mes_options.keys()),
            index=datetime.now().month - 1
        )
        # Definir mes_num logo após a seleção
        mes_num = mes_options[mes_selecionado]

    with col2:
        ano_atual = datetime.now().year
        ano_selecionado = st.selectbox(
            "Ano",
            options=range(ano_atual-2, ano_atual+1),
            index=2
        )

    # Criar tabs
    tab_atual, tab_parcelas, tab_gastos_fixos, tab_historico, tab_analise = st.tabs([
        "📥 Fatura Atual",
        "🔄 Parcelas Futuras",
        "📌 Gastos Fixos",
        "📈 Histórico",
        "📊 Análise"
    ])

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
    @st.cache_data
    def classificar_transacao(descricao):
        """Classifica a transação em categorias"""
        descricao = descricao.lower()
        categorias = {
            'Alimentação': [
                'restaurante', 'ifood', 'food', 'mercado', 'supermercado', 'padaria',
                'confeitaria', 'bar', 'galeto', 'absurda', 'katzsu',
                'garota do', 'abbraccio', 'leblon resta', 'rainha',
                'zona sul', 'tabacaria', 'cafeteria', 'casa do alemao',
                'ferro e farinha', 'eleninha', 'buddario'
            ],
            'Transporte': [
                'uber', '99', 'taxi', 'combustivel', 'estacionamento', 'pedágio',
                'metro', 'brt', 'van', 'onibus', 'mobilidade', 'posto', 'gasolina'
            ],
            'Entretenimento': [
                'cinema', 'teatro', 'show', 'netflix', 'spotify', 'prime',
                'ingresso', 'livraria', 'livros', 'jogos', 'game', 'steam',
                'playstation', 'xbox', 'nintendo', 'hbo', 'disney'
            ],
            'Self Care': [
                'academia', 'farmacia', 'drogaria', 'pacheco', 'salao',
                'cabelereiro', 'spa', 'massagem', 'medico', 'dentista',
                'terapia', 'psicolog', 'nutri', 'personal', 'pilates',
                'yoga', 'crossfit'
            ],
            'Compras': [
                'amazon', 'americanas', 'magalu', 'mercado livre', 'shopee',
                'aliexpress', 'shein', 'renner', 'riachuelo', 'cea', 'zara',
                'nike', 'adidas', 'puma', 'centauro', 'decathlon', 'dafiti',
                'netshoes', 'natura', 'avon', 'boticario', 'sephora'
            ]
        }
        
        for categoria, palavras_chave in categorias.items():
            if any(palavra in descricao for palavra in palavras_chave):
                return categoria
        return 'Outros'

    # Função auxiliar para formatar valores
    def formatar_valor(valor):
        """Formata valor monetário com pontos e vírgulas"""
        return f"R$ {valor:,.2f}"

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

    # Na aba Fatura Atual
    with tab_atual:
        st.header("Fatura Atual")
        
        # Carregar faturas existentes
        faturas = carregar_faturas()
        
        # Seleção de mês e ano
        col1, col2 = st.columns(2)
        with col1:
            mes_selecionado = st.selectbox("Mês", options=list(mes_options.keys()))
            mes_num = mes_options[mes_selecionado]
        with col2:
            ano_selecionado = st.selectbox("Ano", options=list(range(2024, 2020, -1)))

        # Adicionar nova transação
        st.subheader("Adicionar Transação")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            descricao = st.text_input("Descrição da transação")
        with col2:
            valor = st.number_input("Valor", min_value=0.0, step=0.01)
        with col3:
            categoria = st.selectbox(
                "Categoria",
                options=["Alimentação", "Transporte", "Entretenimento", "Self Care", "Compras", "Outros"]
            )
            is_fixo = st.checkbox("Gasto Fixo 📌")

        if st.button("Adicionar Transação"):
            # Encontrar ou criar fatura para o mês/ano selecionado
            fatura = None
            for f in faturas:
                if f['mes'] == mes_num and f['ano'] == ano_selecionado:
                    fatura = f
                    break
            
            if fatura is None:
                fatura = {
                    'mes': mes_num,
                    'ano': ano_selecionado,
                    'transacoes': []
                }
                faturas.append(fatura)
            
            # Adicionar nova transação
            nova_transacao = {
                'descricao': descricao,
                'valor': valor,
                'categoria': categoria,
                'fixo': is_fixo
            }
            fatura['transacoes'].append(nova_transacao)
            salvar_faturas(faturas)
            st.success("Transação adicionada com sucesso!")

        # Mostrar transações do mês atual
        st.subheader("Transações do Mês")
        fatura_atual = None
        for f in faturas:
            if f['mes'] == mes_num and f['ano'] == ano_selecionado:
                fatura_atual = f
                break

        if fatura_atual and fatura_atual['transacoes']:
            for idx, transacao in enumerate(fatura_atual['transacoes']):
                col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 1, 1])
                with col1:
                    nova_descricao = st.text_input(
                        "Descrição",
                        value=transacao['descricao'],
                        key=f"desc_{idx}"
                    )
                with col2:
                    novo_valor = st.number_input(
                        "Valor",
                        value=float(transacao['valor']),
                        key=f"val_{idx}"
                    )
                with col3:
                    nova_categoria = st.selectbox(
                        "Categoria",
                        options=["Alimentação", "Transporte", "Entretenimento", "Self Care", "Compras", "Outros"],
                        key=f"cat_{idx}",
                        index=["Alimentação", "Transporte", "Entretenimento", "Self Care", "Compras", "Outros"].index(transacao['categoria'])
                    )
                with col4:
                    novo_fixo = st.checkbox(
                        "📌",
                        value=transacao.get('fixo', False),
                        key=f"fix_{idx}"
                    )
                with col5:
                    if st.button("🗑️", key=f"del_{idx}"):
                        fatura_atual['transacoes'].pop(idx)
                        salvar_faturas(faturas)
                        st.rerun()

                # Atualizar transação se houver mudanças
                if (nova_descricao != transacao['descricao'] or
                    novo_valor != transacao['valor'] or
                    nova_categoria != transacao['categoria'] or
                    novo_fixo != transacao.get('fixo', False)):
                    
                    fatura_atual['transacoes'][idx] = {
                        'descricao': nova_descricao,
                        'valor': novo_valor,
                        'categoria': nova_categoria,
                        'fixo': novo_fixo
                    }
                    salvar_faturas(faturas)
        else:
            st.info("Nenhuma transação cadastrada para este mês.")

    # Na aba Parcelas Futuras
    with tab_parcelas:
        st.header("Parcelas Futuras")
        # Mostrar apenas parcelas do mês atual
        mes_atual = datetime.now().month
        ano_atual = datetime.now().year
        
        parcelas_mes = []
        for fatura in faturas:
            for transacao in fatura['transacoes']:
                if transacao.get('fixo', False):
                    parcelas_mes.append({
                        'descricao': transacao['descricao'],
                        'valor': transacao['valor'],
                        'categoria': transacao['categoria'],
                        'data': f"{list(mes_options.keys())[mes_atual-1]}/{ano_atual}"
                    })
        
        if parcelas_mes:
            df_parcelas = pd.DataFrame(parcelas_mes)
            st.dataframe(df_parcelas)
        else:
            st.info("Nenhuma parcela para este mês.")

    # Na aba de Gastos Fixos
    with tab_gastos_fixos:
        st.header("Gastos Fixos")
        
        # Carregar faturas
        faturas = carregar_faturas()
        
        # Seção para adicionar novo gasto fixo
        st.subheader("Adicionar Gasto Fixo Mensal")
        col1, col2 = st.columns(2)
        with col1:
            descricao = st.text_input("Descrição", key="gasto_fixo_desc")
            valor = st.number_input("Valor Mensal", min_value=0.0, step=0.01, key="gasto_fixo_valor")
        with col2:
            categoria = st.selectbox(
                "Categoria",
                options=["Alimentação", "Transporte", "Entretenimento", "Self Care", "Compras", "Outros"],
                key="gasto_fixo_cat"
            )
        
        if st.button("Adicionar Gasto Fixo"):
            gastos_fixos = carregar_gastos_fixos()
            novo_gasto = {
                "descricao": descricao,
                "valor": valor,
                "categoria": categoria
            }
            gastos_fixos.append(novo_gasto)
            salvar_gastos_fixos(gastos_fixos)
            st.success("Gasto fixo adicionado com sucesso!")
            
        # Mostrar tabela de gastos fixos mensais
        st.subheader("Gastos Fixos Cadastrados")
        gastos_fixos = carregar_gastos_fixos()
        if gastos_fixos:
            df_fixos = pd.DataFrame(gastos_fixos)
            st.dataframe(df_fixos)
            
        # Mostrar transações marcadas como fixas
        st.subheader("Transações Marcadas como Fixas")
        transacoes_fixas = []
        for fatura in faturas:
            for transacao in fatura['transacoes']:
                if transacao.get('fixo', False):
                    transacao_com_data = {
                        'data': f"{list(mes_options.keys())[int(fatura['mes'])-1]}/{fatura['ano']}",
                        'descricao': transacao['descricao'],
                        'valor': transacao['valor'],
                        'categoria': transacao['categoria']
                    }
                    transacoes_fixas.append(transacao_com_data)
        
        if transacoes_fixas:
            df_transacoes_fixas = pd.DataFrame(transacoes_fixas)
            st.dataframe(df_transacoes_fixas)
        else:
            st.info("Nenhuma transação marcada como fixa.")

    # Na aba de Histórico
    with tab_historico:
        st.header("Histórico")
        
        # Tabela de totais mensais
        st.subheader("Totais Mensais")
        totais_mensais = []
        for fatura in sorted(faturas, key=lambda x: (int(x['ano']), int(x['mes']))):
            total_mes = sum(t['valor'] for t in fatura['transacoes'])
            totais_mensais.append({
                'Mês': f"{list(mes_options.keys())[int(fatura['mes'])-1]}/{fatura['ano']}",
                'Total': f"R$ {total_mes:.2f}"
            })
        
        if totais_mensais:
            df_totais = pd.DataFrame(totais_mensais)
            st.dataframe(df_totais)
        
        # Gráfico de evolução
        st.subheader("Evolução dos Gastos")
        
        # Preparar dados para o gráfico de evolução
        evolucao_data = []
        for fatura in sorted(faturas, key=lambda x: (int(x['ano']), int(x['mes']))):
            total_gasto = sum(t['valor'] for t in fatura['transacoes'])
            evolucao_data.append({
                'mes': int(fatura['mes']),
                'ano': int(fatura['ano']),
                'total': float(total_gasto)
            })
        
        if evolucao_data:
            # Criar gráfico de evolução
            df_evolucao = pd.DataFrame(evolucao_data)
            fig_evolucao = go.Figure()
            fig_evolucao.add_trace(go.Scatter(
                x=[f"{list(mes_options.keys())[int(row['mes'])-1]}/{int(row['ano'])}" for _, row in df_evolucao.iterrows()],
                y=df_evolucao['total'],
                mode='lines+markers',
                name='Total Gasto',
                line=dict(color='#4B0082', width=2),
                marker=dict(size=8)
            ))
            
            fig_evolucao.update_layout(
                title="Evolução dos Gastos",
                xaxis_title="Mês",
                yaxis_title="Valor Total (R$)",
                showlegend=False
            )
            
            st.plotly_chart(fig_evolucao, use_container_width=True)

    # Na aba de Análise
    with tab_analise:
        st.header("Análise")
        
        # Carregar faturas
        faturas = carregar_faturas()
        
        if faturas:
            # Preparar dados para comparação mensal por categoria
            categorias = ["Alimentação", "Transporte", "Entretenimento", "Self Care", "Compras", "Outros"]
            dados_comparacao = []
            
            # Pegar os dois meses mais recentes
            faturas_ordenadas = sorted(faturas, key=lambda x: (int(x['ano']), int(x['mes'])), reverse=True)[:2]
            if len(faturas_ordenadas) >= 2:
                for categoria in categorias:
                    valores = []
                    meses = []
                    for fatura in faturas_ordenadas:
                        total_categoria = sum(t['valor'] for t in fatura['transacoes'] if t['categoria'] == categoria)
                        valores.append(total_categoria)
                        meses.append(f"{list(mes_options.keys())[int(fatura['mes'])-1]}/{fatura['ano']}")
                    
                    for mes, valor in zip(meses, valores):
                        dados_comparacao.append({
                            'categoria': categoria,
                            'mes': mes,
                            'valor': valor
                        })
                
                # Criar gráfico de comparação
                df_comparacao = pd.DataFrame(dados_comparacao)
                fig_comparacao = go.Figure()
                
                for mes in df_comparacao['mes'].unique():
                    dados_mes = df_comparacao[df_comparacao['mes'] == mes]
                    fig_comparacao.add_trace(go.Bar(
                        name=mes,
                        x=dados_mes['categoria'],
                        y=dados_mes['valor'],
                        text=dados_mes['valor'].apply(lambda x: f'R$ {x:.2f}'),
                        textposition='auto',
                    ))
                
                fig_comparacao.update_layout(
                    title='Comparação de Gastos por Categoria',
                    xaxis_title='Categoria',
                    yaxis_title='Valor (R$)',
                    barmode='group',
                    showlegend=True,
                    height=500
                )
                
                st.plotly_chart(fig_comparacao, use_container_width=True)
        else:
            st.info("Nenhuma fatura cadastrada para análise.") 