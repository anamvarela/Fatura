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
CATEGORIAS_PADRAO = ["Alimentação", "Transporte", "Entretenimento", "Self Care", "Compras"]

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
            'yogoberry': 'Alimentação'
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

def editar_categoria_transacao(fatura_mes, fatura_ano, descricao, valor, nova_categoria):
    """
    Edita a categoria de uma transação e salva a nova classificação para uso futuro.
    """
    dados = carregar_dados()
    faturas = dados.get('faturas', [])
    
    for fatura in faturas:
        if fatura['mes'] == fatura_mes and fatura['ano'] == fatura_ano:
            for transacao in fatura['transacoes']:
                if transacao['descricao'] == descricao and abs(transacao['valor'] - valor) < 0.01:
                    # Se a nova categoria for ENTRADA, mover para entradas
                    if nova_categoria == "ENTRADA":
                        entradas = dados.get('entradas', [])
                        entrada = {
                            'descricao': transacao['descricao'],
                            'valor': transacao['valor'],
                            'mes': fatura_mes,
                            'ano': fatura_ano
                        }
                        entradas.append(entrada)
                        dados['entradas'] = entradas
                        # Remover da lista de transações
                        fatura['transacoes'].remove(transacao)
                    else:
                        transacao['categoria'] = nova_categoria
                        # Salvar a classificação para uso futuro
                        atualizar_classificacao_salva(descricao, nova_categoria)
                    break
    
    salvar_dados(dados)

def classificar_transacao(descricao):
    """
    Classifica automaticamente uma transação com base em sua descrição.
    Primeiro verifica nas classificações salvas, depois usa as regras automáticas.
    """
    descricao = descricao.lower().strip()
    
    # Primeiro verifica se já existe uma classificação salva
    classificacoes_salvas = carregar_classificacoes_salvas()
    if descricao in classificacoes_salvas:
        return classificacoes_salvas[descricao]

    # Verificar se é uma entrada
    palavras_entrada = ['reembolso', 'estorno', 'cashback', 'rendimento', 'pagamento recebido', 'transferencia recebida']
    if any(palavra in descricao for palavra in palavras_entrada):
        return "ENTRADA"

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
            'peixaria', 'supernosso', 'verdemar', 'epa', 'super', 'mart'
        ],
        'Transporte': [
            # Apps de transporte
            'uber', '99 taxi', '99taxi', '99 pop', '99pop', '99*', '99 *', 
            'cabify', 'taxi', 'táxi', 'transfer', 'shuttle', 'buser',
            # Combustível
            'posto', 'shell', 'ipiranga', 'petrobras', 'br posto', 'ale',
            'combustivel', 'gasolina', 'etanol', 'diesel', 'br mania',
            # Transporte público
            'metro', 'metrô', 'trem', 'onibus', 'ônibus', 'brt', 'vlt',
            'bilhete unico', 'bilhete único', 'cartao riocard', 'supervia',
            'cartão riocard', 'bom', 'bem', 'metrocard',
            # Estacionamento
            'estacionamento', 'parking', 'zona azul', 'parquimetro',
            'estapar', 'multipark', 'autopark'
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
        'Compras': [
            # Lojas de departamento e vestuário
            'renner', 'cea', 'c&a', 'riachuelo', 'marisa', 'hering',
            'zara', 'forever 21', 'leader', 'h&m', 'shop', 'store', 'loja',
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

    return "Outros"

def adicionar_fatura(fatura):
    """Adiciona uma nova fatura ao histórico"""
    dados = carregar_dados()
    faturas = dados.get('faturas', [])
    
    # Classificar transações e tratar descontos/estornos
    for transacao in fatura['transacoes']:
        if 'categoria' not in transacao:
            transacao['categoria'] = classificar_transacao(transacao['descricao'])
        
        # Se for desconto/estorno, mover para entradas
        if transacao['categoria'] == "ENTRADA":
            entradas = dados.get('entradas', [])
            entrada = {
                'descricao': transacao['descricao'],
                'valor': transacao['valor'],
                'mes': fatura['mes'],
                'ano': fatura['ano']
            }
            entradas.append(entrada)
            dados['entradas'] = entradas
            # Remover da lista de transações
            fatura['transacoes'].remove(transacao)
    
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
        
        # Alimentação
        if any(palavra in descricao for palavra in [
            'ifood', 'rappi', 'uber eats', 'restaurante', 'padaria', 'mercado',
            'supermercado', 'hortifruti', 'açougue', 'acougue', 'cafeteria',
            'cafe', 'café', 'bar', 'lanchonete', 'food', 'burger'
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
        
        # Compras (incluindo o que antes era "Outros")
        return "Compras"

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

    # Criar tabs
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
                            st.success(f"Fatura de {mes_selecionado}/{ano_selecionado} salva com sucesso!")
                        except Exception as e:
                            st.error(f"Erro ao salvar fatura: {str(e)}")
                else:
                    st.warning("Por favor, faça upload de uma fatura primeiro.")
        
        with col2:
            if st.button("🗑️ Limpar Dados do Mês", use_container_width=True):
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

    # Na aba de Análise
    with tab_analise:
        # Inicializar session_state para categoria aberta
        if 'categoria_aberta' not in st.session_state:
            st.session_state.categoria_aberta = None

        # Carregar categorias do arquivo
        categorias = carregar_categorias()

        # Botão para adicionar nova classificação no topo
        with st.expander("➕ Criar Nova Classificação"):
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

        # Calcular total geral
        total_atual = totais_categoria.sum()

        # Mostrar transações por categoria
        for categoria, total in totais_categoria.items():
            # Usar o estado para controlar se o expander está aberto
            is_open = st.session_state.categoria_aberta == categoria
            with st.expander(
                f"📁 {categoria} - {formatar_valor(total)} ({(total/total_atual*100):.1f}%) - {len(df[df['categoria'] == categoria])} transações",
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
                                nova_categoria = st.selectbox(
                                    "Categoria",
                                    options=categorias,  # Usar categorias do arquivo
                                    key=f"cat_{idx}",
                                    index=categorias.index(transacao['categoria'])
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
                                            # Manter a categoria aberta após salvar
                                            st.session_state.categoria_aberta = categoria
                                            st.success("✓ Alterações salvas!")
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
                # Procurar padrões de parcelas (ex: 1/12, 01/12, 1 de 12, etc)
                padrao_parcela = re.search(r'(\d{1,2})[^\d]+(\d{1,2})', descricao)
                if padrao_parcela:
                    parcela_atual = int(padrao_parcela.group(1))
                    total_parcelas = int(padrao_parcela.group(2))
                    
                    # Criar chave única para a compra
                    chave = re.sub(r'\d{1,2}[^\d]+\d{1,2}', '', descricao).strip()
                    
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
            st.metric("Total do Mês", formatar_valor(total_mes))
            
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
            novo_gasto = {
                'descricao': descricao,
                'valor': valor,
                'categoria': categoria,
                'data_adicao': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            dados['gastos_fixos'].append(novo_gasto)
            salvar_dados(dados)
            st.success("✓ Gasto fixo adicionado com sucesso!")
        
        # Mostrar gastos fixos existentes
        if gastos_fixos:
            st.subheader("Gastos Fixos Cadastrados")
            total_fixo = sum(g['valor'] for g in gastos_fixos)
            st.metric("Total Mensal", formatar_valor(total_fixo))
            
            for idx, gasto in enumerate(gastos_fixos):
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                with col1:
                    st.write(gasto['descricao'])
                with col2:
                    st.write(formatar_valor(gasto['valor']))
                with col3:
                    st.write(gasto['categoria'])
                with col4:
                    if st.button("🗑️", key=f"del_fixo_{idx}"):
                        dados['gastos_fixos'].remove(gasto)
                        salvar_dados(dados)
                        st.rerun()
                st.markdown("---")
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
            mes_ano = f"{list(mes_options.keys())[int(fatura['mes'])-1]}/{fatura['ano']}"
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

    # Estilo para tabelas mais finas
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
</style>
""", unsafe_allow_html=True) 