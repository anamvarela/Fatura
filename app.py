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

    # Criar abas
    tab_inserir, tab_entradas, tab_analise, tab_parcelas, tab_fixos, tab_historico = st.tabs([
        "📥 Inserir Fatura",
        "💰 Entradas do Mês",
        "📊 Análise",
        "🔄 Parcelas Futuras",
        "📌 Gastos Fixos",
        "📈 Histórico"
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
                            mes_num = mes_options[mes_selecionado]
                            fatura = {
                                'mes': mes_num,
                                'ano': ano_selecionado,
                                'transacoes': df.to_dict('records')
                            }
                            historico = adicionar_fatura(fatura=fatura)
                            st.success(f"Fatura de {mes_selecionado}/{ano_selecionado} salva com sucesso!")
                        except Exception as e:
                            st.error(f"Erro ao salvar fatura: {str(e)}")
                else:
                    st.warning("Por favor, faça upload de uma fatura primeiro.")
        
        with col2:
            if st.button("🗑️ Limpar Dados do Mês", use_container_width=True):
                mes_num = mes_options[mes_selecionado]
                limpar_fatura(mes_num, ano_selecionado)
                st.success(f"Dados de {mes_selecionado}/{ano_selecionado} removidos!")

    # Na aba de Entradas do Mês
    with tab_entradas:
        st.header("💰 Entradas do Mês")
        
        # Formulário para adicionar entrada
        with st.form("form_entrada"):
            col1, col2, col3 = st.columns([2, 2, 1])
            
            with col1:
                valor_entrada = st.number_input("Valor", min_value=0.0, format="%.2f")
            
            with col2:
                descricao_entrada = st.text_input("Descrição")
            
            with col3:
                tipo_entrada = st.selectbox(
                    "Tipo",
                    options=["Salário", "Freelance", "Outros"]
                )
            
            if st.form_submit_button("Adicionar Entrada"):
                if valor_entrada > 0 and descricao_entrada:
                    adicionar_entrada(mes_num, ano_selecionado, valor_entrada, descricao_entrada, tipo_entrada)
                    st.success("✓ Entrada adicionada com sucesso!")
                else:
                    st.error("Por favor, preencha todos os campos.")

        # Mostrar entradas existentes
        entradas_existentes = obter_entradas(mes_num, ano_selecionado)
        if entradas_existentes:
            st.write("### Entradas Registradas")
            for idx, entrada in enumerate(entradas_existentes):
                col1, col2, col3, col4 = st.columns([1, 2, 1, 1])
                with col1:
                    st.write(f"R$ {entrada['valor']:.2f}")
                with col2:
                    st.write(entrada['descricao'])
                with col3:
                    st.write(entrada['tipo'])
                with col4:
                    if st.button("🗑️", key=f"del_entrada_{idx}"):
                        remover_entrada(
                            entrada['mes'],
                            entrada['ano'],
                            entrada['valor'],
                            entrada['descricao'],
                            entrada['tipo']
                        )
                        st.rerun()
            
            # Mostrar total
            total_entradas = sum(e['valor'] for e in entradas_existentes)
            st.metric("Total de Entradas", f"R$ {total_entradas:.2f}")
        else:
            st.info("Nenhuma entrada registrada para este mês.")

    # Na aba de Parcelas Futuras
    with tab_parcelas:
        st.header("🔄 Parcelas Futuras")
        
        # Formulário para adicionar nova compra parcelada
        with st.form("form_parcela"):
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                descricao_parcela = st.text_input("Descrição da Compra")
            
            with col2:
                valor_total = st.number_input("Valor Total", min_value=0.0, format="%.2f")
            
            with col3:
                num_parcelas = st.number_input("Número de Parcelas", min_value=1, value=1)
            
            data_inicio = st.date_input(
                "Data da Primeira Parcela",
                value=datetime.now(),
                min_value=datetime(2020, 1, 1),
                max_value=datetime(2030, 12, 31)
            )
            
            if st.form_submit_button("Adicionar Compra Parcelada"):
                if valor_total > 0 and descricao_parcela and num_parcelas > 0:
                    adicionar_parcela(descricao_parcela, valor_total, num_parcelas, data_inicio)
                    st.success("✓ Compra parcelada adicionada com sucesso!")
                else:
                    st.error("Por favor, preencha todos os campos.")
        
        # Mostrar parcelas do mês atual
        st.subheader(f"Parcelas de {mes_selecionado}/{ano_selecionado}")
        parcelas_mes = obter_parcelas_mes(mes_num, ano_selecionado)
        
        if parcelas_mes:
            total_mes = sum(p['valor_parcela'] for p in parcelas_mes)
            st.metric("Total de Parcelas do Mês", formatar_valor(total_mes))
            
            for parcela in parcelas_mes:
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                with col1:
                    st.write(parcela['descricao'])
                with col2:
                    st.write(formatar_valor(parcela['valor_parcela']))
                with col3:
                    st.write(f"Parcela {parcela['parcela_atual']}/{parcela['total_parcelas']}")
                with col4:
                    if st.button("🗑️", key=f"del_parcela_{parcela['descricao']}"):
                        remover_parcela(parcela['descricao'], parcela['valor_total'])
                        st.rerun()
        else:
            st.info("Nenhuma parcela para este mês.")

    # Na aba de Gastos Fixos
    with tab_fixos:
        st.header("📌 Gastos Fixos")
        
        # Seção para adicionar novo gasto fixo
        st.subheader("Adicionar Gasto Fixo Mensal")
        col1, col2 = st.columns(2)
        with col1:
            descricao = st.text_input("Descrição")
            valor = st.number_input("Valor Mensal", min_value=0.0, step=0.01)
        with col2:
            categoria = st.selectbox(
                "Categoria",
                options=["Alimentação", "Transporte", "Entretenimento", "Self Care", "Compras", "Outros"]
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
        st.header("📈 Histórico de Gastos")
        
        # Obter dados históricos
        dados = carregar_dados()
        faturas = dados.get('faturas', [])
        
        if not faturas:
            st.info("Nenhum dado histórico encontrado.")
            st.stop()
        
        # Preparar dados para o gráfico de evolução
        evolucao_data = []
        for fatura in sorted(faturas, key=lambda x: (x['ano'], x['mes'])):
            total_gasto = sum(t['valor'] for t in fatura['transacoes'])
            evolucao_data.append({
                'mes': int(fatura['mes']),
                'ano': int(fatura['ano']),
                'total': float(total_gasto)
            })
        
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
            title="Evolução dos Gastos Mensais",
            xaxis_title="Mês/Ano",
            yaxis_title="Valor Total (R$)",
            showlegend=True
        )
        
        st.plotly_chart(fig_evolucao, use_container_width=True)

    # Aba de Análise
    with tab_analise:
        st.header("📊 Análise de Gastos")
        
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
        
        # Calcular métricas
        total_atual = sum(t['valor'] for t in fatura_atual['transacoes'])
        total_anterior = sum(t['valor'] for t in fatura_anterior['transacoes']) if fatura_anterior else 0
        
        # Obter entradas do mês
        entradas_mes = obter_entradas(mes_num, ano_selecionado)
        total_entradas = sum(e['valor'] for e in entradas_mes)
        
        # Calcular variação
        if total_anterior > 0:
            variacao = ((total_atual - total_anterior) / total_anterior) * 100
            variacao_texto = f"{'+' if variacao > 0 else ''}{variacao:.1f}%"
        else:
            variacao_texto = "N/A"
        
        # Mostrar métricas no topo
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Total de Gastos",
                formatar_valor(total_atual)
            )
        
        with col2:
            if total_entradas > 0:
                percentual_gasto = (total_atual / total_entradas) * 100
                st.metric(
                    "Gastos / Entradas",
                    f"{percentual_gasto:.1f}%"
                )
            else:
                st.metric("Gastos / Entradas", "N/A")
        
        with col3:
            st.metric(
                "Variação do Mês Anterior",
                variacao_texto,
                delta=f"{formatar_valor(total_atual - total_anterior)}" if total_anterior > 0 else None
            )
        
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
        
        # Mostrar detalhamento por categoria
        st.write("### Detalhamento por Categoria")
        df = pd.DataFrame(fatura_atual['transacoes'])
        
        # Atualizar categorias com as já salvas
        for i, transacao in enumerate(fatura_atual['transacoes']):
            if 'categoria' in transacao:
                df.loc[i, 'categoria'] = transacao['categoria']
            else:
                df.loc[i, 'categoria'] = classificar_transacao(transacao['descricao'])
        
        # Calcular totais por categoria
        totais_categoria = df.groupby('categoria')['valor'].sum().sort_values(ascending=False)
        
        # Mostrar transações por categoria
        for categoria, total in totais_categoria.items():
            with st.expander(f"📁 {categoria} - {formatar_valor(total)} ({(total/total_atual*100):.1f}%) - {len(df[df['categoria'] == categoria])} transações"):
                gastos_categoria = df[df['categoria'] == categoria].sort_values('valor', ascending=False)
                
                # Criar container para reduzir espaçamento
                with st.container():
                    for idx, transacao in gastos_categoria.iterrows():
                        # Layout mais compacto
                        cols = st.columns([1, 3, 2, 0.5, 0.5])
                        
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
                        
                        # Se o botão de edição foi clicado, mostrar o formulário
                        if st.session_state.get(f'editing_{idx}', False):
                            with st.form(f"form_transacao_{idx}", clear_on_submit=True):
                                nova_categoria = st.selectbox(
                                    "Categoria",
                                    options=["Alimentação", "Transporte", "Entretenimento", "Self Care", "Compras", "Outros"],
                                    key=f"cat_{idx}",
                                    index=["Alimentação", "Transporte", "Entretenimento", "Self Care", "Compras", "Outros"].index(transacao['categoria'])
                                )
                                
                                is_fixo = st.checkbox("Marcar como gasto fixo", key=f"fix_{idx}")
                                
                                col1, col2 = st.columns([1, 1])
                                with col1:
                                    if st.form_submit_button("💾 Salvar"):
                                        try:
                                            # Atualizar categoria na transação
                                            fatura_atual['transacoes'][idx]['categoria'] = nova_categoria
                                            
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
                                            st.success("✓ Alterações salvas!")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Erro ao salvar alterações: {str(e)}")
                                
                                with col2:
                                    if st.form_submit_button("❌ Cancelar"):
                                        st.session_state[f'editing_{idx}'] = False
                                        st.rerun()
                        
                        st.markdown("---") 