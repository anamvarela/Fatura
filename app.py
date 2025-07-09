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

    # Aba de Análise
    with tab_analise:
        st.header("📊 Análise de Gastos")
        
        # Carregar dados do histórico
        dados = carregar_dados()
        faturas = dados.get('faturas', [])
        gastos_fixos = dados.get('gastos_fixos', [])
        
        # Filtrar fatura do mês atual
        fatura_atual = None
        for fatura in faturas:
            if fatura['mes'] == mes_num and fatura['ano'] == ano_selecionado:
                fatura_atual = fatura
                break
        
        if not fatura_atual:
            st.warning("Nenhuma fatura encontrada para este mês.")
            st.stop()
        
        # Preparar dados para análise
        df = pd.DataFrame(fatura_atual['transacoes'])
        df['categoria'] = df['descricao'].apply(classificar_transacao)
        
        # Calcular totais por categoria
        totais_categoria = df.groupby('categoria')['valor'].sum().sort_values(ascending=False)
        
        # Mostrar detalhamento por categoria
        st.write("### Detalhamento por Categoria")
        for categoria, total in totais_categoria.items():
            with st.expander(f"📁 {categoria} - {formatar_valor(total)} ({(total/totais_categoria.sum()*100):.1f}%) - {len(df[df['categoria'] == categoria])} transações"):
                gastos_categoria = df[df['categoria'] == categoria].sort_values('valor', ascending=False)
                
                # Criar container para reduzir espaçamento
                with st.container():
                    for idx, transacao in gastos_categoria.iterrows():
                        # Verificar se é gasto fixo
                        is_gasto_fixo = any(
                            g['descricao'] == transacao['descricao'] and 
                            g['valor'] == transacao['valor'] 
                            for g in gastos_fixos
                        )
                        
                        # Layout mais compacto
                        cols = st.columns([1, 3, 2, 0.5, 0.5])
                        
                        with cols[0]:
                            st.write(transacao['data'])
                        
                        with cols[1]:
                            st.write(transacao['descricao'])
                        
                        with cols[2]:
                            st.write(formatar_valor(transacao['valor']))
                        
                        with cols[3]:
                            if is_gasto_fixo:
                                st.write("📌")
                        
                        with cols[4]:
                            if st.button("✏️", key=f"edit_{idx}"):
                                st.session_state[f'editing_{idx}'] = True
                        
                        # Se o botão de edição foi clicado, mostrar o formulário
                        if st.session_state.get(f'editing_{idx}', False):
                            with st.form(f"form_transacao_{idx}"):
                                nova_categoria = st.selectbox(
                                    "Categoria",
                                    options=["Alimentação", "Transporte", "Entretenimento", "Self Care", "Compras", "Outros"],
                                    key=f"cat_{idx}",
                                    index=["Alimentação", "Transporte", "Entretenimento", "Self Care", "Compras", "Outros"].index(transacao['categoria'])
                                )
                                
                                is_fixo = st.checkbox("Marcar como gasto fixo", key=f"fix_{idx}", value=is_gasto_fixo)
                                
                                col1, col2 = st.columns([1, 1])
                                with col1:
                                    if st.form_submit_button("💾 Salvar"):
                                        # Atualizar categoria
                                        fatura_atual['transacoes'][idx]['categoria'] = nova_categoria
                                        
                                        # Se marcado como fixo, adicionar aos gastos fixos
                                        if is_fixo and not is_gasto_fixo:
                                            gasto_fixo = {
                                                'descricao': transacao['descricao'],
                                                'valor': transacao['valor'],
                                                'categoria': nova_categoria,
                                                'data_adicao': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                            }
                                            adicionar_gasto_fixo(gasto_fixo)
                                        
                                        # Se desmarcado como fixo, remover dos gastos fixos
                                        elif not is_fixo and is_gasto_fixo:
                                            remover_gasto_fixo(transacao['descricao'], transacao['valor'])
                                        
                                        # Salvar alterações
                                        for i, f in enumerate(dados['faturas']):
                                            if f['mes'] == mes_num and f['ano'] == ano_selecionado:
                                                dados['faturas'][i] = fatura_atual
                                                break
                                        salvar_dados(dados)
                                        st.session_state[f'editing_{idx}'] = False
                                        st.success("✓ Alterações salvas com sucesso!")
                                        time.sleep(0.5)  # Pequena pausa para mostrar a mensagem
                                        st.rerun()
                                
                                with col2:
                                    if st.form_submit_button("❌ Cancelar"):
                                        st.session_state[f'editing_{idx}'] = False
                                        st.rerun()
                        
                        # Linha mais fina para separar transações
                        st.markdown("---")
        
        # Criar gráfico de barras
        fig_barras = go.Figure(data=[
            go.Bar(
                x=totais_categoria.index,
                y=totais_categoria.values,
                marker_color='#4B0082'
            )
        ])
        
        # Configurar layout
        fig_barras.update_layout(
            title="Distribuição de Gastos por Categoria",
            xaxis_title="Categoria",
            yaxis_title="Valor Total (R$)",
            showlegend=False
        )
        
        # Mostrar gráfico
        st.plotly_chart(fig_barras, use_container_width=True)

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
            st.metric("Total de Parcelas do Mês", f"R$ {total_mes:.2f}")
            
            for parcela in parcelas_mes:
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                with col1:
                    st.write(parcela['descricao'])
                with col2:
                    st.write(f"R$ {parcela['valor_parcela']:.2f}")
                with col3:
                    st.write(f"{parcela['numero']}/{parcela['total_parcelas']}")
                with col4:
                    if not parcela['paga']:
                        if st.button("✓", key=f"pagar_{parcela['descricao']}_{parcela['numero']}"):
                            marcar_parcela_paga(parcela['descricao'], parcela['numero'])
                            st.rerun()
                    else:
                        st.write("✓ Paga")
        else:
            st.info("Nenhuma parcela para este mês.")
        
        # Mostrar parcelas futuras
        st.subheader("Visão Futura")
        total_futuro = calcular_total_parcelas_futuras(mes_num, ano_selecionado)
        st.metric("Total de Parcelas Futuras", f"R$ {total_futuro:.2f}")
        
        parcelas_futuras = obter_parcelas_futuras(mes_num, ano_selecionado)
        if parcelas_futuras:
            for mes_ano, parcelas in parcelas_futuras.items():
                ano, mes = mes_ano.split('-')
                nome_mes = list(mes_options.keys())[int(mes) - 1]
                
                with st.expander(f"{nome_mes}/{ano} - Total: R$ {sum(p['valor'] for p in parcelas):.2f}"):
                    for parcela in parcelas:
                        st.write(f"• {parcela['descricao']}: R$ {parcela['valor']:.2f} ({parcela['numero']}/{parcela['total_parcelas']})")
        else:
            st.info("Nenhuma parcela futura encontrada.")

    # Aba de Gastos Fixos
    with tab_fixos:
        st.markdown("### 📌 Gastos Fixos")
        
        # Formulário para adicionar novo gasto fixo
        with st.form("form_gasto_fixo"):
            col1, col2 = st.columns([2, 1])
            with col1:
                descricao = st.text_input("Descrição do Gasto")
            with col2:
                valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
            
            if st.form_submit_button("➕ Adicionar Gasto Fixo"):
                if descricao and valor > 0:
                    gasto = {
                        'descricao': descricao,
                        'valor': valor,
                        'categoria': 'Outros'
                    }
                    adicionar_gasto_fixo(gasto)
                    st.success('✅ Gasto fixo adicionado com sucesso!')
                    st.experimental_rerun()
                else:
                    st.error("Por favor, preencha todos os campos.")
        
        # Lista de gastos fixos
        gastos_fixos = obter_gastos_fixos()
        if gastos_fixos:
            total_fixo = sum(float(g['valor']) for g in gastos_fixos)
            st.metric("Total Gastos Fixos", f"R$ {total_fixo:,.2f}")
            
            # Criar DataFrame para exibição
            df_fixos = pd.DataFrame(gastos_fixos)
            if not df_fixos.empty:
                df_fixos['Valor'] = df_fixos['valor'].apply(lambda x: f"R$ {float(x):,.2f}")
                df_fixos['Descrição'] = df_fixos['descricao']
                df_fixos = df_fixos[['Descrição', 'Valor']]
                
                # Exibir tabela com botão de exclusão
                for idx, row in df_fixos.iterrows():
                    col1, col2, col3 = st.columns([2, 1, 0.5])
                    with col1:
                        st.write(row['Descrição'])
                    with col2:
                        st.write(row['Valor'])
                    with col3:
                        if st.button("🗑️", key=f"del_fix_{idx}", help="Excluir gasto fixo"):
                            valor_float = float(row['Valor'].replace('R$ ', '').replace('.', '').replace(',', '.'))
                            remover_gasto_fixo(row['Descrição'], valor_float)
                            st.success('✅ Gasto fixo removido com sucesso!')
                            st.experimental_rerun()
                    st.markdown('---')
        else:
            st.info("Nenhum gasto fixo cadastrado.")

    # Na aba de Histórico
    with tab_historico:
        st.header("📈 Histórico de Gastos")
        
        # Obter dados históricos
        historico = obter_historico_gastos_mensais()
        evolucao = obter_evolucao_gastos()
        medias_categoria = obter_media_gastos_categoria()
        
        if not historico:
            st.info("Nenhum dado histórico encontrado.")
            st.stop()
        
        # Mostrar evolução dos gastos
        st.subheader("Evolução dos Gastos")
        df_evolucao = pd.DataFrame(evolucao)
        
        # Criar gráfico de linha
        fig_evolucao = go.Figure()
        fig_evolucao.add_trace(go.Scatter(
            x=[f"{row['mes']}/{row['ano']}" for _, row in df_evolucao.iterrows()],
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
        
        # Mostrar médias por categoria
        st.subheader("Média de Gastos por Categoria")
        if medias_categoria:
            df_medias = pd.DataFrame(list(medias_categoria.items()), columns=['Categoria', 'Média'])
            df_medias = df_medias.sort_values('Média', ascending=False)
            
            fig_medias = go.Figure(data=[go.Bar(
                x=df_medias['Categoria'],
                y=df_medias['Média'],
                marker_color='#4B0082'
            )])
            
            fig_medias.update_layout(
                title="Média de Gastos por Categoria",
                xaxis_title="Categoria",
                yaxis_title="Valor Médio (R$)",
                showlegend=False
            )
            
            st.plotly_chart(fig_medias, use_container_width=True)
            
            # Mostrar tabela com os valores
            for _, row in df_medias.iterrows():
                st.write(f"**{row['Categoria']}**: R$ {row['Média']:.2f}")
        
        # Mostrar detalhes por mês
        st.subheader("Detalhamento Mensal")
        for chave in sorted(historico.keys(), reverse=True):
            dados = historico[chave]
            mes_nome = list(mes_options.keys())[dados['mes'] - 1]
            
            with st.expander(f"{mes_nome}/{dados['ano']}"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Total Gasto", f"R$ {dados['total_gastos']:.2f}")
                
                with col2:
                    st.metric("Total Entradas", f"R$ {dados['total_entradas']:.2f}")
                
                with col3:
                    st.metric("Total Parcelas", f"R$ {dados['total_parcelas']:.2f}")
                
                # Mostrar gastos por categoria
                if dados['gastos_categoria']:
                    st.write("#### Gastos por Categoria")
                    for categoria, valor in sorted(dados['gastos_categoria'].items(), key=lambda x: x[1], reverse=True):
                        st.write(f"**{categoria}**: R$ {valor:.2f}") 