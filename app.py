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
    adicionar_entrada, remover_entrada, obter_entradas
)
import json
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from pathlib import Path

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
                'transacoes': transacoes,
                'total': sum(t['valor'] for t in transacoes)
            }
            
            # Adicionar fatura ao histórico
            adicionar_fatura(fatura)
            
            return pd.DataFrame(transacoes)
        except Exception as e:
            st.error(f"Erro ao processar o PDF: {str(e)}")
            return None

    # Função para classificar transações (mantém a mesma)
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
                'uber', '99', 'taxi', 'combustível', 'posto', 'estacionamento',
                'transfer'
            ],
            'Entretenimento': [
                'netflix', 'spotify', 'cinema', 'teatro', 'show', 'ingresso',
                'kinoplex', 'apple.com', 'google play', 'playstation',
                'xbox', 'steam', 'battle.net', 'origin', 'ubisoft'
            ],
            'Self Care': [
                'farmácia', 'hospital', 'médico', 'consulta', 'clínica',
                'laboratório', 'exame', 'wellhub', 'espaco laser', 'espaço laser',
                'drogasil', 'venancio', 'pacheco', 'raia', 'suaacademia'
            ],
            'Compras': [
                'shopping', 'loja', 'magazine', 'americanas', 'amazon',
                'vipeconceito', 'havaianas', 'energia', 'água', 'internet', 
                'telefone', 'celular', 'parcela', 'pagamento', 'mercado livre',
                'voah', 'track field', 'sk acessorios'
            ]
        }
        
        # Casos especiais primeiro
        descricao_lower = descricao.lower()
        if 'track field' in descricao_lower:
            return 'Compras'
        if 'absurda confeitaria' in descricao_lower:
            return 'Alimentação'
        if 'mercadolivre' in descricao_lower:
            return 'Compras'
        if 'buddario' in descricao_lower:
            return 'Alimentação'
        if 'suaacademia' in descricao_lower:
            return 'Self Care'
        if 'sk acessorios' in descricao_lower:
            return 'Compras'
        
        # Verificar cada categoria
        for categoria, palavras_chave in categorias.items():
            if any(palavra in descricao_lower for palavra in palavras_chave):
                return categoria
                
        # Se não encontrou em nenhuma categoria, verificar palavras parciais
        palavras_descricao = descricao_lower.split()
        for palavra in palavras_descricao:
            # Alimentação
            if any(termo in palavra for termo in ['rest', 'cafe', 'bar', 'food']):
                return 'Alimentação'
            # Self Care
            if any(termo in palavra for termo in ['farm', 'drog', 'med', 'spa']):
                return 'Self Care'
            # Compras
            if any(termo in palavra for termo in ['shop', 'store', 'loja', 'pag']):
                return 'Compras'
        
        return 'Outros'

    # Função auxiliar para formatar valores
    def formatar_valor(valor):
        """Formata valor monetário com pontos e vírgulas"""
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

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
                df['Categoria'] = df['Descrição'].apply(classificar_transacao)
    
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💾 Salvar Fatura", use_container_width=True):
                if arquivo is not None:
                    if df is not None:
                        try:
                            mes_num = mes_options[mes_selecionado]
                            historico = adicionar_fatura(df, mes_num, ano_selecionado)
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
        
        # Adicionar coluna de categoria
        df['categoria'] = df['descricao'].apply(classificar_transacao)
        
        # Calcular totais por categoria
        totais_categoria = df.groupby('categoria')['valor'].sum().sort_values(ascending=False)
        
        # Criar gráfico de pizza
        fig_pizza = go.Figure(data=[go.Pie(
            labels=totais_categoria.index,
            values=totais_categoria.values,
            hole=.3
        )])
        
        # Configurar layout
        fig_pizza.update_layout(
            title="Distribuição de Gastos por Categoria",
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # Mostrar gráfico
        st.plotly_chart(fig_pizza, use_container_width=True)
        
        # Mostrar tabela de gastos por categoria
        st.write("### Detalhamento por Categoria")
        for categoria in totais_categoria.index:
            with st.expander(f"{categoria}: R$ {totais_categoria[categoria]:.2f}"):
                gastos_categoria = df[df['categoria'] == categoria].sort_values('valor', ascending=False)
                for _, gasto in gastos_categoria.iterrows():
                    st.write(f"- {gasto['descricao']}: R$ {gasto['valor']:.2f}")

    # Aba de Parcelas Futuras
    with tab_parcelas:
        st.subheader("Análise de Parcelas Futuras")
        
        # Obter parcelas futuras
        mes_num = mes_options[mes_selecionado]
        totais_futuros = calcular_total_parcelas_futuras(mes_num, ano_selecionado)
        
        if totais_futuros:
            # Criar DataFrame para visualização
            dados_futuros = []
            for periodo, info in totais_futuros.items():
                ano, mes = periodo.split('-')
                mes_nome = list(mes_options.keys())[int(mes)-1]
                dados_futuros.append({
                    'Período': f"{mes_nome}/{ano}",
                    'Total': info['total'],
                    'Quantidade': len(info['parcelas']),
                    'periodo_key': periodo  # para ordenação
                })
            
            df_futuros = pd.DataFrame(dados_futuros)
            df_futuros = df_futuros.sort_values('periodo_key').drop('periodo_key', axis=1)
            
            # Mostrar total geral de parcelas futuras
            total_geral = sum(info['total'] for info in totais_futuros.values())
            st.metric(
                "Total em Parcelas Futuras",
                f"R$ {total_geral:.2f}",
                help="Soma de todas as parcelas futuras"
            )
            
            # Tabela expansível por mês
            for periodo, info in sorted(totais_futuros.items()):
                ano, mes = periodo.split('-')
                mes_nome = list(mes_options.keys())[int(mes)-1]
                
                with st.expander(
                    f"📅 {mes_nome}/{ano} - R$ {info['total']:.2f} "
                    f"({len(info['parcelas'])} parcelas)"
                ):
                    # Agrupar parcelas por categoria
                    df_parcelas = pd.DataFrame(info['parcelas'])
                    resumo_categorias = df_parcelas.groupby('categoria')['valor'].agg(['sum', 'count']).round(2)
                    resumo_categorias.columns = ['Total (R$)', 'Quantidade']
                    resumo_categorias = resumo_categorias.sort_values('Total (R$)', ascending=False)
                    
                    # Mostrar resumo por categoria
                    st.markdown("#### Resumo por Categoria")
                    for categoria, row in resumo_categorias.iterrows():
                        st.markdown(f"**{categoria}**: R$ {row['Total (R$)']:.2f} ({row['Quantidade']} parcelas)")
                    
                    # Mostrar todas as parcelas
                    st.markdown("#### Detalhamento das Parcelas")
                    for parcela in sorted(info['parcelas'], key=lambda x: (-x['valor'], x['descricao'])):
                        st.markdown(
                            f"- {parcela['descricao']} - {formatar_valor(parcela['valor'])} "
                            f"(Parcela {parcela['parcela']}/{parcela['total_parcelas']})"
                        )
            
            # Gráfico de barras dos totais futuros
            st.subheader("Visualização")
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df_futuros['Período'],
                y=df_futuros['Total'],
                marker_color='#4B0082'
            ))
            
            fig.update_layout(
                title='Total de Parcelas por Mês',
                xaxis_title='Mês',
                yaxis_title='Valor Total (R$)',
                height=400
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Não há parcelas futuras registradas.") 

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

    # Aba de Histórico
    with tab_historico:
        st.subheader("Histórico de Gastos")
        
        # Obter histórico de gastos
        gastos_mensais = obter_historico_gastos_mensais()
        
        if gastos_mensais:
            # Preparar dados para o gráfico
            df_historico = pd.DataFrame(gastos_mensais)
            df_historico['Mês/Ano'] = df_historico.apply(
                lambda x: f"{list(mes_options.keys())[x['mes']-1]}/{x['ano']}",
                axis=1
            )
            
            # Gráfico de linha
            fig = go.Figure()
            
            # Linha de gastos totais
            fig.add_trace(go.Scatter(
                x=df_historico['Mês/Ano'],
                y=df_historico['total'],
                mode='lines+markers',
                name='Gasto Total',
                line=dict(color='#4B0082', width=3),
                marker=dict(size=8)
            ))
            
            # Adicionar linha de gastos fixos
            if gastos_fixos:
                total_fixos = calcular_total_gastos_fixos()
                fig.add_trace(go.Scatter(
                    x=df_historico['Mês/Ano'],
                    y=[total_fixos] * len(df_historico),
                    mode='lines',
                    name='Gastos Fixos',
                    line=dict(color='#E5E5E5', width=2, dash='dash')
                ))
            
            fig.update_layout(
                title='Evolução dos Gastos Mensais',
                xaxis_title='Período',
                yaxis_title='Valor Total (R$)',
                height=500,
                showlegend=True,
                yaxis=dict(range=[4000, 10000]),
                legend=dict(
                    yanchor="bottom",
                    y=0.01,
                    xanchor="left",
                    x=0.01
                )
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela com os valores
            st.subheader("Detalhamento por Mês")
            df_display = df_historico[['Mês/Ano', 'total']].copy()
            df_display.columns = ['Período', 'Total Gasto']
            df_display['Total Gasto'] = df_display['Total Gasto'].apply(formatar_valor)
            
            st.dataframe(
                df_display,
                hide_index=True,
                column_config={
                    "Total Gasto": st.column_config.TextColumn(
                        "Total Gasto",
                        width="medium"
                    )
                }
            )
        else:
            st.info("Ainda não há histórico de gastos registrado.") 