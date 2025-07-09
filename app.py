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
    obter_gastos_fixos, carregar_dados, salvar_dados
)
import json
import yaml
import streamlit_authenticator as stauth
from pathlib import Path

# Configuração da página
st.set_page_config(
    page_title="Análise Faturas Nubank",
    page_icon="📊",
    layout="wide",
)

# Carregar configurações de autenticação
with open('config.yaml') as file:
    config = yaml.load(file, Loader=yaml.SafeLoader)

# Criar o autenticador
authenticator = stauth.Authenticate(
    credentials=config['credentials'],
    cookie_name=config['cookie']['name'],
    key=config['cookie']['key'],
    cookie_expiry_days=config['cookie']['expiry_days']
)

# Adicionar login
name, authentication_status, username = authenticator.login("Login")

if authentication_status == False:
    st.error('Username/password is incorrect')
elif authentication_status == None:
    st.warning('Please enter your username and password')
else:
    # Criar diretório do usuário se não existir
    user_dir = Path(f"data/{username}")
    user_dir.mkdir(parents=True, exist_ok=True)
    
    # Configurar caminhos específicos do usuário
    st.session_state['user_data_dir'] = str(user_dir)
    
    # Adicionar logout na sidebar
    with st.sidebar:
        authenticator.logout("Logout")
    
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

    # Aba de Entradas
    with tab_entradas:
        st.subheader("Registrar Entradas do Mês")
        
        # Carregar entradas existentes
        mes_num = mes_options[mes_selecionado]
        entradas_existentes = obter_entradas(mes_num, ano_selecionado)
        
        # Lista para armazenar as entradas
        if 'entradas_temp' not in st.session_state:
            if entradas_existentes:
                # Migrar do formato antigo se necessário
                if 'entradas' in entradas_existentes:
                    st.session_state.entradas_temp = entradas_existentes['entradas']
                else:
                    # Converter formato antigo para novo
                    st.session_state.entradas_temp = [
                        {
                            'valor': float(entradas_existentes.get('salario_fixo', 0)),
                            'descricao': 'Salário Fixo',
                            'tipo': 'fixo'
                        }
                    ]
                    if entradas_existentes.get('renda_extra', 0) > 0:
                        st.session_state.entradas_temp.append({
                            'valor': float(entradas_existentes.get('renda_extra', 0)),
                            'descricao': 'Renda Extra',
                            'tipo': 'extra'
                        })
            else:
                st.session_state.entradas_temp = []
        
        # Função para adicionar nova entrada
        def adicionar_entrada(valor, descricao, tipo):
            if valor > 0 and descricao.strip():
                st.session_state.entradas_temp.append({
                    'valor': valor,
                    'descricao': descricao.strip(),
                    'tipo': tipo
                })
                return True
            return False
        
        # Função para remover entrada
        def remover_entrada(idx):
            del st.session_state.entradas_temp[idx]
        
        # Formulário para nova entrada
        st.subheader("Nova Entrada")
        with st.form("nova_entrada", clear_on_submit=True):
            col1, col2, col3 = st.columns([2, 2, 1])
            
            with col1:
                valor = st.number_input(
                    "Valor",
                    min_value=0.0,
                    value=0.0,
                    format="%.2f",
                    help="Use ponto como separador decimal"
                )
                # Mostrar valor formatado abaixo do input
                if valor > 0:
                    st.caption(f"Valor formatado: {formatar_valor(valor)}")
            
            with col2:
                descricao = st.text_input(
                    "Descrição",
                    value="",
                    placeholder="Ex: Salário, Freelance, Bônus..."
                )
            
            with col3:
                tipo = st.selectbox(
                    "Tipo",
                    options=["fixo", "extra"],
                    help="Fixo: recebimentos regulares como salário\nExtra: recebimentos ocasionais"
                )
            
            if st.form_submit_button("➕ Adicionar Entrada", use_container_width=True):
                if adicionar_entrada(valor, descricao, tipo):
                    st.success("Entrada adicionada!")
                    st.experimental_rerun()
                else:
                    st.error("Por favor, preencha o valor e a descrição.")
        
        # Mostrar lista de entradas
        if st.session_state.entradas_temp:
            st.subheader("Entradas Registradas")
            
            # Calcular totais
            total_fixo = sum(e['valor'] for e in st.session_state.entradas_temp if e['tipo'] == 'fixo')
            total_extra = sum(e['valor'] for e in st.session_state.entradas_temp if e['tipo'] == 'extra')
            total_geral = total_fixo + total_extra
            
            # Mostrar totais
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Fixo", formatar_valor(total_fixo))
            with col2:
                st.metric("Total Extra", formatar_valor(total_extra))
            with col3:
                st.metric("Total Geral", formatar_valor(total_geral))
            
            # Estilo da tabela de entradas
            st.markdown("""
            <style>
            .income-container {
                padding: 0;
                margin: 0;
                font-size: 0.9em;
            }
            .income-header {
                font-weight: bold;
                color: #4B0082;
                border-bottom: 1px solid #4B0082;
                padding-bottom: 0.25rem;
                margin-bottom: 0.25rem;
                font-size: 0.9em;
            }
            .income-row {
                padding: 0.2rem 0;
                border-bottom: 1px solid #eee;
                transition: background-color 0.2s;
                line-height: 1;
                margin: 0;
            }
            .income-row:last-child {
                border-bottom: 1px solid #eee;
            }
            .income-row:hover {
                background-color: #f8f8f8;
            }
            .income-row div[data-testid="column"] {
                padding-top: 0 !important;
                padding-bottom: 0 !important;
            }
            .income-row div[data-testid="column"] p {
                margin: 0 !important;
                padding: 0 !important;
                line-height: 1.2 !important;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # Container principal
            st.markdown('<div class="income-container">', unsafe_allow_html=True)
            
            # Cabeçalho
            col1, col2, col3, col4 = st.columns([1.5, 2, 1, 0.5])
            with col1:
                st.markdown('<div class="income-header">Valor</div>', unsafe_allow_html=True)
            with col2:
                st.markdown('<div class="income-header">Descrição</div>', unsafe_allow_html=True)
            with col3:
                st.markdown('<div class="income-header">Tipo</div>', unsafe_allow_html=True)
            
            # Mostrar entradas
            for idx, entrada in enumerate(st.session_state.entradas_temp):
                st.markdown('<div class="income-row">', unsafe_allow_html=True)
                col1, col2, col3, col4 = st.columns([1.5, 2, 1, 0.5])
                with col1:
                    st.write(formatar_valor(entrada['valor']))
                with col2:
                    st.write(entrada['descricao'])
                with col3:
                    st.write("🔄 Fixo" if entrada['tipo'] == 'fixo' else "💫 Extra")
                with col4:
                    if st.button("🗑️", key=f"del_{idx}", help="Excluir entrada"):
                        remover_entrada(idx)
                        st.experimental_rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Nenhuma entrada registrada para este mês.")
        
        # Botões de ação
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💾 Salvar Entradas", use_container_width=True):
                try:
                    historico = adicionar_entradas(
                        mes_num,
                        ano_selecionado,
                        st.session_state.entradas_temp
                    )
                    st.success(f"Entradas de {mes_selecionado}/{ano_selecionado} salvas com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao salvar entradas: {str(e)}")
        
        with col2:
            if st.button("🗑️ Limpar Entradas", use_container_width=True):
                st.session_state.entradas_temp = []
                limpar_entradas(mes_num, ano_selecionado)
                st.success(f"Entradas de {mes_selecionado}/{ano_selecionado} removidas!")

    # Aba de Análise
    with tab_analise:
        # Carregar dados históricos
        historico = carregar_historico()
        mes_num = mes_options[mes_selecionado]
        periodo = f"{ano_selecionado}-{mes_num:02d}"
        
        if periodo in historico['faturas']:
            dados_mes = historico['faturas'][periodo]
            df_mes = pd.DataFrame(dados_mes['transacoes'])
            total_gasto = dados_mes['total_gasto']
            
            # Métricas principais em linha
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    "Total Gasto no Mês",
                    formatar_valor(total_gasto)
                )
            
            with col2:
                entradas = obter_entradas(mes_num, ano_selecionado)
                if entradas:
                    renda_total = entradas['total']
                    percentual = (total_gasto / renda_total) * 100
                    st.metric(
                        "% da Renda Utilizada",
                        f"{percentual:.1f}%"
                    )
            
            with col3:
                fatura_anterior = obter_fatura_anterior(mes_num, ano_selecionado)
                if fatura_anterior:
                    valor_anterior = fatura_anterior['total_gasto']
                    variacao = calcular_variacao(total_gasto, valor_anterior)
                    var_formatted = formatar_variacao(variacao)
                    st.metric(
                        "Variação em Relação ao Mês Anterior",
                        var_formatted,
                        delta=formatar_valor(valor_anterior)
                    )
            
            # Tabela de categorias expansível
            st.subheader("Resumo por Categoria")
            
            # Preparar dados para a tabela
            resumo_categorias = df_mes.groupby('Categoria').agg({
                'Valor': ['sum', 'count']
            }).round(2)
            
            resumo_categorias.columns = ['Total (R$)', 'Quantidade']
            resumo_categorias = resumo_categorias.sort_values('Total (R$)', ascending=False)
            resumo_categorias['% do Total'] = (resumo_categorias['Total (R$)'] / total_gasto * 100).round(2)
            
            # Adicionar comparação com mês anterior se disponível
            if fatura_anterior:
                categorias_anterior = pd.Series(fatura_anterior['gastos_por_categoria'])
                variacoes = []
                for categoria in resumo_categorias.index:
                    valor_atual = resumo_categorias.loc[categoria, 'Total (R$)']
                    valor_ant = categorias_anterior.get(categoria, 0)
                    variacao = calcular_variacao(valor_atual, valor_ant)
                    variacoes.append(formatar_variacao(variacao))
                resumo_categorias['Variação'] = variacoes
            
            # Exibir tabela com linhas expansíveis
            for idx, (categoria, row) in enumerate(resumo_categorias.iterrows()):
                with st.expander(
                    f"📁 {categoria} - {formatar_valor(row['Total (R$)'])} ({row['% do Total']}%) - {row['Quantidade']} transações"
                    + (f" | {row['Variação']}" if 'Variação' in resumo_categorias.columns else "")
                ):
                    transacoes = df_mes[df_mes['Categoria'] == categoria].sort_values('Valor', ascending=False)
                    
                    # Para cada transação
                    for _, transacao in transacoes.iterrows():
                        with st.container():
                            col1, col2, col3, col4, col5, col6 = st.columns([0.8, 1.5, 0.8, 1.2, 0.5, 0.5])
                            with col1:
                                st.write(transacao['Data'])
                            with col2:
                                st.write(transacao['Descrição'])
                            with col3:
                                st.write(formatar_valor(transacao['Valor']))
                            
                            # Se o botão de editar foi clicado para esta transação
                            edit_key = f"edit_{transacao['Data']}_{transacao['Valor']}_{transacao['Descrição']}"
                            if edit_key not in st.session_state:
                                st.session_state[edit_key] = False
                            
                            with col4:
                                if st.session_state[edit_key]:
                                    # Mostrar seleção de categoria
                                    nova_categoria = st.selectbox(
                                        "",
                                        options=['Alimentação', 'Transporte', 'Entretenimento', 'Self Care', 'Compras', 'Outros'],
                                        index=['Alimentação', 'Transporte', 'Entretenimento', 'Self Care', 'Compras', 'Outros'].index(categoria),
                                        key=f"cat_{transacao['Data']}_{transacao['Valor']}_{transacao['Descrição']}"
                                    )
                                else:
                                    st.write(categoria)
                            
                            with col5:
                                # Verificar se já é um gasto fixo
                                gastos_fixos = obter_gastos_fixos()
                                is_gasto_fixo = False
                                for gasto in gastos_fixos:
                                    # Normalizar as strings para comparação
                                    desc_gasto = gasto['descricao'].lower().strip()
                                    desc_transacao = transacao['Descrição'].lower().strip()
                                    
                                    # Verificar se uma descrição contém a outra
                                    if (desc_gasto in desc_transacao or desc_transacao in desc_gasto) and \
                                       abs(gasto['valor'] - float(transacao['Valor'])) < 0.01:  # Comparação com tolerância para float
                                        is_gasto_fixo = True
                                        break

                                if st.session_state[edit_key]:
                                    # Checkbox para marcar como gasto fixo
                                    is_fixo = st.checkbox(
                                        "Fixo",
                                        value=is_gasto_fixo,
                                        key=f"fix_{transacao['Data']}_{transacao['Valor']}_{transacao['Descrição']}"
                                    )
                                    
                                    # Se o estado do checkbox mudou
                                    checkbox_key = f"fix_{transacao['Data']}_{transacao['Valor']}_{transacao['Descrição']}"
                                    if checkbox_key not in st.session_state.checkbox_states:
                                        st.session_state.checkbox_states[checkbox_key] = is_gasto_fixo
                                    
                                    if is_fixo != st.session_state.checkbox_states[checkbox_key]:
                                        # Atualizar estado do checkbox
                                        st.session_state.checkbox_states[checkbox_key] = is_fixo
                                        
                                        if is_fixo:
                                            # Adicionar aos gastos fixos
                                            adicionar_gasto_fixo({
                                                'descricao': transacao['Descrição'],
                                                'valor': float(transacao['Valor']),
                                                'categoria': nova_categoria if st.session_state[edit_key] else categoria
                                            })
                                            st.success('✅ Gasto adicionado aos gastos fixos!')
                                            st.experimental_rerun()
                                        else:
                                            # Remover dos gastos fixos
                                            remover_gasto_fixo(transacao['Descrição'], float(transacao['Valor']))
                                            st.success('ℹ️ Gasto removido dos gastos fixos')
                                            st.experimental_rerun()
                                else:
                                    # Mostrar ícone se for gasto fixo
                                    if is_gasto_fixo:
                                        st.markdown("📌")
                                    else:
                                        st.write("")

                            with col6:
                                if not st.session_state[edit_key]:
                                    # Mostrar botão de editar
                                    if st.button("✏️", key=f"btn_{transacao['Data']}_{transacao['Valor']}_{transacao['Descrição']}"):
                                        st.session_state[edit_key] = True
                                        st.experimental_rerun()
                                else:
                                    # Botão de salvar
                                    if st.button("💾", key=f"save_{transacao['Data']}_{transacao['Valor']}_{transacao['Descrição']}"):
                                        # Atualizar categoria no DataFrame
                                        idx = df_mes[
                                            (df_mes['Data'] == transacao['Data']) & 
                                            (df_mes['Descrição'] == transacao['Descrição']) & 
                                            (df_mes['Valor'] == transacao['Valor'])
                                        ].index[0]
                                        df_mes.at[idx, 'Categoria'] = nova_categoria

                                        # Atualizar gastos fixos
                                        if is_fixo:
                                            # Adicionar/atualizar nos gastos fixos
                                            if not is_gasto_fixo:
                                                adicionar_gasto_fixo({
                                                    'descricao': transacao['Descrição'],
                                                    'valor': float(transacao['Valor']),  # Garantir que é float
                                                    'categoria': nova_categoria
                                                })
                                                st.success('✅ Gasto adicionado aos gastos fixos!')
                                        else:
                                            # Se não é mais fixo e era antes, remover
                                            if is_gasto_fixo:
                                                remover_gasto_fixo(transacao['Descrição'], float(transacao['Valor']))  # Garantir que é float
                                                st.success('ℹ️ Gasto removido dos gastos fixos')
                                        
                                        # Salvar alterações
                                        dados_mes['transacoes'] = df_mes.to_dict('records')
                                        historico['faturas'][periodo] = dados_mes
                                        
                                        # Recalcular totais por categoria
                                        gastos_por_categoria = df_mes.groupby('Categoria')['Valor'].sum().round(2).to_dict()
                                        dados_mes['gastos_por_categoria'] = gastos_por_categoria
                                        
                                        # Salvar no arquivo
                                        with open('dados_historico.json', 'w', encoding='utf-8') as f:
                                            json.dump(historico, f, ensure_ascii=False, indent=4)
                                        
                                        # Limpar estado de edição
                                        st.session_state[edit_key] = False
                                        st.success('✅ Alterações salvas com sucesso!')
                                        st.experimental_rerun()
                
            # Gráficos
            st.subheader("Visualizações")
            col1, col2 = st.columns(2)
            
            with col1:
                # Gráfico de pizza por categoria
                fig_pie = px.pie(
                    df_mes,
                    values='Valor',
                    names='Categoria',
                    title='Distribuição dos Gastos por Categoria'
                )
                fig_pie.update_layout(
                    legend=dict(
                        yanchor="bottom",
                        y=0.01,
                        xanchor="left",
                        x=0.01
                    )
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with col2:
                # Gráfico de comparação com mês anterior
                if fatura_anterior:
                    categorias_atual = df_mes.groupby('Categoria')['Valor'].sum()
                    categorias_anterior = pd.Series(fatura_anterior['gastos_por_categoria'])
                    
                    df_comp = pd.DataFrame({
                        'Atual': categorias_atual,
                        'Anterior': categorias_anterior
                    }).fillna(0)
                    
                    fig_comp = go.Figure()
                    fig_comp.add_trace(go.Bar(
                        name='Mês Atual',
                        x=df_comp.index,
                        y=df_comp['Atual'],
                        marker_color='#4B0082'
                    ))
                    fig_comp.add_trace(go.Bar(
                        name='Mês Anterior',
                        x=df_comp.index,
                        y=df_comp['Anterior'],
                        marker_color='#E5E5E5'
                    ))
                    
                    fig_comp.update_layout(
                        title='Comparação com Mês Anterior',
                        barmode='group',
                        height=400,
                        legend=dict(
                            yanchor="top",
                            y=1.0,
                            xanchor="right",
                            x=1.0
                        )
                    )
                    st.plotly_chart(fig_comp, use_container_width=True)
        else:
            st.info("Selecione um mês e insira uma fatura para ver a análise.")

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