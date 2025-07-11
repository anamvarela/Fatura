import json
import os
import streamlit as st
from pathlib import Path
from datetime import datetime, timedelta
import calendar
import pandas as pd

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
        return {'faturas': [], 'gastos_fixos': [], 'entradas': [], 'parcelas': []}
    
    with open(arquivo) as f:
        dados = json.load(f)
        if 'entradas' not in dados:
            dados['entradas'] = []
        if 'parcelas' not in dados:
            dados['parcelas'] = []
        return dados

def salvar_dados(dados):
    """Salva os dados no arquivo JSON do usuário"""
    arquivo = get_user_data_file()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    
    with open(arquivo, 'w') as f:
        json.dump(dados, f, indent=4)

def adicionar_parcela(descricao, valor_total, num_parcelas, data_inicio):
    """Adiciona uma nova compra parcelada"""
    dados = carregar_dados()
    if 'parcelas' not in dados:
        dados['parcelas'] = []
    
    # Converter data_inicio para objetos datetime
    if isinstance(data_inicio, str):
        data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d')
    
    valor_parcela = valor_total / num_parcelas
    parcelas = []
    
    for i in range(num_parcelas):
        data_parcela = data_inicio + timedelta(days=30 * i)
        parcelas.append({
            'numero': i + 1,
            'valor': valor_parcela,
            'data': data_parcela.strftime('%Y-%m-%d'),
            'paga': False
        })
    
    compra_parcelada = {
        'descricao': descricao,
        'valor_total': valor_total,
        'num_parcelas': num_parcelas,
        'valor_parcela': valor_parcela,
        'data_inicio': data_inicio.strftime('%Y-%m-%d'),
        'parcelas': parcelas
    }
    
    dados['parcelas'].append(compra_parcelada)
    salvar_dados(dados)

def remover_parcela(descricao, valor_total, data_inicio):
    """Remove uma compra parcelada"""
    dados = carregar_dados()
    dados['parcelas'] = [p for p in dados['parcelas'] 
                        if not (p['descricao'] == descricao and 
                               abs(float(p['valor_total']) - valor_total) < 0.01 and
                               p['data_inicio'] == data_inicio)]
    salvar_dados(dados)

def marcar_parcela_paga(descricao, numero_parcela):
    """Marca uma parcela específica como paga"""
    dados = carregar_dados()
    for compra in dados['parcelas']:
        if compra['descricao'] == descricao:
            for parcela in compra['parcelas']:
                if parcela['numero'] == numero_parcela:
                    parcela['paga'] = True
                    break
    salvar_dados(dados)

def obter_parcelas_mes(mes, ano):
    """Retorna todas as parcelas de um mês específico"""
    dados = carregar_dados()
    parcelas_mes = []
    
    data_alvo = datetime(ano, mes, 1)
    primeiro_dia = data_alvo.replace(day=1)
    ultimo_dia = data_alvo.replace(day=calendar.monthrange(ano, mes)[1])
    
    for compra in dados.get('parcelas', []):
        for parcela in compra['parcelas']:
            data_parcela = datetime.strptime(parcela['data'], '%Y-%m-%d')
            if primeiro_dia <= data_parcela <= ultimo_dia:
                parcelas_mes.append({
                    'descricao': compra['descricao'],
                    'valor_parcela': parcela['valor'],
                    'numero': parcela['numero'],
                    'total_parcelas': compra['num_parcelas'],
                    'paga': parcela.get('paga', False)
                })
    
    return parcelas_mes

def calcular_total_parcelas_futuras(mes_atual=None, ano_atual=None):
    """Calcula o total de parcelas futuras a partir de um mês específico"""
    if mes_atual is None:
        mes_atual = datetime.now().month
    if ano_atual is None:
        ano_atual = datetime.now().year
    
    dados = carregar_dados()
    total = 0
    data_referencia = datetime(ano_atual, mes_atual, 1)
    
    for compra in dados.get('parcelas', []):
        for parcela in compra['parcelas']:
            data_parcela = datetime.strptime(parcela['data'], '%Y-%m-%d')
            if data_parcela >= data_referencia and not parcela.get('paga', False):
                total += parcela['valor']
    
    return total

def obter_parcelas_futuras(mes_atual=None, ano_atual=None):
    """Retorna todas as parcelas futuras organizadas por mês"""
    if mes_atual is None:
        mes_atual = datetime.now().month
    if ano_atual is None:
        ano_atual = datetime.now().year
    
    dados = carregar_dados()
    parcelas_futuras = {}
    data_referencia = datetime(ano_atual, mes_atual, 1)
    
    for compra in dados.get('parcelas', []):
        for parcela in compra['parcelas']:
            data_parcela = datetime.strptime(parcela['data'], '%Y-%m-%d')
            if data_parcela >= data_referencia and not parcela.get('paga', False):
                mes_ano = data_parcela.strftime('%Y-%m')
                if mes_ano not in parcelas_futuras:
                    parcelas_futuras[mes_ano] = []
                
                parcelas_futuras[mes_ano].append({
                    'descricao': compra['descricao'],
                    'valor': parcela['valor'],
                    'numero': parcela['numero'],
                    'total_parcelas': compra['num_parcelas']
                })
    
    return parcelas_futuras

def adicionar_fatura(df=None, mes=None, ano=None, fatura=None):
    """
    Adiciona uma nova fatura ao histórico.
    Pode receber um DataFrame com as transações + mês e ano,
    ou um dicionário de fatura já formatado.
    """
    dados = carregar_dados()
    
    if fatura is not None:
        # Se recebeu uma fatura já formatada
        nova_fatura = fatura
    else:
        # Se recebeu um DataFrame, formata a fatura
        if df is None or mes is None or ano is None:
            raise ValueError("É necessário fornecer df, mes e ano ou uma fatura formatada")
            
        # Formatar as transações
        transacoes = []
        for _, row in df.iterrows():
            transacao = {
                'data': row['data'],
                'descricao': row['descricao'],
                'valor': float(row['valor']),
                'categoria': classificar_transacao(row['descricao'])
            }
            transacoes.append(transacao)
        
        # Criar a nova fatura
        nova_fatura = {
            'mes': mes,
            'ano': ano,
            'transacoes': transacoes
        }
    
    # Verificar se já existe uma fatura para este mês/ano
    for i, f in enumerate(dados['faturas']):
        if f['mes'] == nova_fatura['mes'] and f['ano'] == nova_fatura['ano']:
            # Atualizar fatura existente
            dados['faturas'][i] = nova_fatura
            salvar_dados(dados)
            return dados
    
    # Adicionar nova fatura
    dados['faturas'].append(nova_fatura)
    salvar_dados(dados)
    return dados

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
    """Limpa todo o histórico de faturas, entradas, gastos fixos e parcelas"""
    salvar_dados({'faturas': [], 'gastos_fixos': [], 'entradas': [], 'parcelas': []})

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

def adicionar_entrada(mes, ano, valor, descricao, tipo):
    """Adiciona uma nova entrada ao mês"""
    dados = carregar_dados()
    entrada = {
        'mes': mes,
        'ano': ano,
        'valor': valor,
        'descricao': descricao,
        'tipo': tipo
    }
    dados['entradas'].append(entrada)
    salvar_dados(dados)

def remover_entrada(mes, ano, valor, descricao, tipo):
    """Remove uma entrada específica"""
    dados = carregar_dados()
    dados['entradas'] = [e for e in dados['entradas'] 
                        if not (e['mes'] == mes and 
                               e['ano'] == ano and 
                               abs(float(e['valor']) - valor) < 0.01 and
                               e['descricao'] == descricao and
                               e.get('tipo', 'Outros') == tipo)]
    salvar_dados(dados)

def obter_entradas(mes, ano):
    """Retorna todas as entradas de um mês específico"""
    dados = carregar_dados()
    return [e for e in dados['entradas'] 
            if e['mes'] == mes and e['ano'] == ano] 

def obter_historico_gastos_mensais():
    """Retorna o histórico de gastos mensais"""
    dados = carregar_dados()
    historico = {}
    
    for fatura in dados.get('faturas', []):
        mes = fatura['mes']
        ano = fatura['ano']
        chave = f"{ano}-{mes:02d}"
        
        # Calcular total de gastos
        total_gastos = sum(t['valor'] for t in fatura['transacoes'])
        
        # Calcular gastos por categoria
        df = pd.DataFrame(fatura['transacoes'])
        if not df.empty:
            df['categoria'] = df['descricao'].apply(classificar_transacao)
            gastos_categoria = df.groupby('categoria')['valor'].sum().to_dict()
        else:
            gastos_categoria = {}
        
        # Obter entradas do mês
        entradas_mes = [e for e in dados.get('entradas', []) 
                       if e['mes'] == mes and e['ano'] == ano]
        total_entradas = sum(e['valor'] for e in entradas_mes)
        
        # Obter parcelas do mês
        parcelas_mes = obter_parcelas_mes(mes, ano)
        total_parcelas = sum(p['valor_parcela'] for p in parcelas_mes)
        
        historico[chave] = {
            'mes': mes,
            'ano': ano,
            'total_gastos': total_gastos,
            'total_entradas': total_entradas,
            'total_parcelas': total_parcelas,
            'gastos_categoria': gastos_categoria
        }
    
    return historico

def obter_historico_categorias():
    """Retorna o histórico de gastos por categoria"""
    dados = carregar_dados()
    historico = {}
    
    for fatura in dados.get('faturas', []):
        mes = fatura['mes']
        ano = fatura['ano']
        chave = f"{ano}-{mes:02d}"
        
        df = pd.DataFrame(fatura['transacoes'])
        if not df.empty:
            df['categoria'] = df['descricao'].apply(classificar_transacao)
            historico[chave] = df.groupby('categoria')['valor'].sum().to_dict()
        else:
            historico[chave] = {}
    
    return historico

def obter_media_gastos_categoria():
    """Calcula a média de gastos por categoria"""
    historico = obter_historico_categorias()
    if not historico:
        return {}
    
    # Inicializar dicionário para somar gastos
    soma_categorias = {}
    contagem_categorias = {}
    
    # Somar gastos por categoria
    for mes_dados in historico.values():
        for categoria, valor in mes_dados.items():
            soma_categorias[categoria] = soma_categorias.get(categoria, 0) + valor
            contagem_categorias[categoria] = contagem_categorias.get(categoria, 0) + 1
    
    # Calcular médias
    medias = {
        categoria: soma_categorias[categoria] / contagem_categorias[categoria]
        for categoria in soma_categorias
    }
    
    return medias

def obter_evolucao_gastos():
    """Retorna a evolução dos gastos totais ao longo do tempo"""
    historico = obter_historico_gastos_mensais()
    evolucao = []
    
    for chave in sorted(historico.keys()):
        dados = historico[chave]
        evolucao.append({
            'mes': dados['mes'],
            'ano': dados['ano'],
            'total': dados['total_gastos']
        })
    
    return evolucao

def carregar_regras_classificacao():
    """Carrega as regras de classificação do arquivo"""
    try:
        with open('regras_classificacao.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def aplicar_regras_classificacao(descricao):
    """Aplica as regras de classificação definidas pelo usuário"""
    regras = carregar_regras_classificacao()
    descricao_lower = descricao.lower()
    
    for regra in regras:
        if regra['palavra_chave'] in descricao_lower:
            return regra['categoria']
    
    return None

def classificar_transacao(descricao):
    """
    Classifica automaticamente uma transação com base em sua descrição.
    """
    descricao_original = descricao
    descricao = descricao.lower().strip()
    
    # APLICAR REGRAS DO USUÁRIO (palavras-chave definidas pelo usuário)
    categoria_regra = aplicar_regras_classificacao(descricao)
    if categoria_regra:
        return categoria_regra
    
    # VERIFICAÇÕES ESPECIAIS HARDCODED
    # 99APP - Regra especial para transporte
    if '99app' in descricao or ('99' in descricao and 'app' in descricao) or '99 app' in descricao:
        return 'Transporte'
    
    # Mercado Livre - Regra especial para roupas
    if 'mercado livre' in descricao or 'mercadolivre' in descricao:
        return 'Roupas'
    
    # Zig* - Regra especial para entretenimento
    if descricao.startswith('zig'):
        return 'Entretenimento'

    # Dicionário de estabelecimentos por categoria - VERSÃO COMPLETA
    categorias = {
        'Alimentação': [
            # Delivery e apps
            'ifood', 'rappi', 'uber eats', 'james delivery', 'aiqfome', 'zomato', 'loggi',
            # Restaurantes genéricos
            'restaurante', 'rest.', 'rest ', 'churrascaria', 'pizzaria', 'pizza',
            'hamburger', 'burger', 'lanchonete', 'bar', 'boteco', 'cantina',
            'galeto', 'padaria', 'confeitaria', 'doceria', 'cafeteria', 'café',
            'bistro', 'buffet', 'grill', 'espeto', 'pastelaria', 'pastel',
            'rotisserie', 'sushi', 'japanese', 'china in box', 'chinesa', 'thai',
            'mexicano', 'árabe', 'arabe', 'ferro e farinha', 'lancheria',
            # Redes grandes
            'outback', 'mcdonalds', 'mc donalds', 'burger king', 'bk', 'subway',
            'habibs', 'spoleto', 'giraffas', 'madero', 'dominos', 'pizza hut',
            'starbucks', 'kopenhagen', 'cacau show', 'bob beef', 'bobs',
            'kfc', 'popeyes', 'subway', 'dairy queen',
            # Mercados e supermercados
            'carrefour', 'extra', 'pao de acucar', 'pão de açúcar', 'assai', 'atacadao', 'atacadão',
            'mundial', 'guanabara', 'zona sul', 'hortifruti', 'supermarket', 'mercado',
            'supermercado', 'sacolao', 'feira', 'mercearia', 'atacado', 'dia',
            'sams club', 'makro', 'tenda', 'quitanda', 'adega', 'emporio', 'empório',
            'armazem', 'armazém', 'minimercado', 'mercadinho', 'acougue', 'açougue',
            'peixaria', 'supernosso', 'verdemar', 'epa', 'super', 'mart',
            'big box', 'walmart', 'central', 'prezunic', 'carioca',
            # Restaurantes específicos do RJ
            'bendita chica', 'bendita', 'chica', 'amen gavea', 'amen',
            'art food', 'abbraccio', 'braseiro', 'gavea', 'nama',
            'nanquim', 'posi mozza', 'posi', 'mozza', 'smoov', 'sucos',
            'katzsu', 'katzsu bar', 'eleninha', 'buddario', 'dri',
            'jobi', 'scarpi', 'tintin', 'choperiakaraoke', 'chopp',
            'casa do alemao', 'alemao', 'tabacaria', 'cafeteria',
            'woods wine', 'woods', 'wine', 'reserva 11', 'beach club',
            'sheesh', 'downtown', 'rainha', 'leblon', 'natural delli',
            'absurda', 'confeitaria', 'bacio di latte', 'yogoberry',
            'galeto leblon', 'galeto rainha', 'pavilhao', 'sardinha',
            'la guapa', 'lena park', 'pasta basta', 'stuzzi',
            # Palavras-chave gerais
            'food', 'caza', 'lagoa', 'buffet', 'lanches', 'refeicao', 'refeição',
            'comida', 'bebida', 'alimentacao', 'alimentação'
        ],
        'Transporte': [
            # Apps de transporte (99app já tratado separadamente)
            'uber', 'uber*', 'uber x', 'uber eats', '99 pop', '99pop', 'cabify', 
            'taxi', 'táxi', 'transfer', 'shuttle', 'buser', 'blablacar',
            # Combustível e postos
            'posto', 'shell', 'ipiranga', 'petrobras', 'br posto', 'ale',
            'combustivel', 'combustível', 'gasolina', 'etanol', 'diesel', 
            'alcool', 'álcool', 'br mania', 'texaco', 'esso',
            # Transporte público
            'metro', 'metrô', 'trem', 'onibus', 'ônibus', 'brt', 'vlt',
            'bilhete unico', 'bilhete único', 'cartao riocard', 'supervia',
            'cartão riocard', 'metrocard', 'ricard',
            # Estacionamento
            'estacionamento', 'parking', 'zona azul', 'parquimetro',
            'estapar', 'multipark', 'autopark', 'valet',
            # Outros transportes
            'aviacao', 'aviação', 'gol', 'tam', 'azul', 'latam',
            'rodoviaria', 'rodoviária', 'viacao', 'viação'
        ],
        'Entretenimento': [
            # Streaming e música
            'netflix', 'spotify', 'amazon prime', 'disney+', 'disney plus',
            'hbo max', 'youtube premium', 'deezer', 'apple music', 'tidal',
            'paramount+', 'globoplay', 'crunchyroll', 'twitch', 'prime video',
            # Jogos
            'steam', 'playstation', 'psn', 'xbox', 'nintendo',
            'epic games', 'battle.net', 'origin', 'uplay', 'gog',
            # Cinema e eventos
            'cinema', 'cinemark', 'kinoplex', 'teatro', 'show', 'evento', 
            'ingresso', 'tickets', 'sympla', 'eventbrite', 'ticket360', 
            'ingressorapido', 'livepass', 'ticketmaster',
            # Bares e entretenimento noturno - apenas os que começam com ZIG
            'zig'  # Esta palavra já é tratada separadamente na verificação especial
        ],
        'Self Care': [
            # Farmácias e saúde
            'farmacia', 'farmácia', 'drogaria', 'droga', 'pacheco', 'raia', 
            'drogasil', 'remedios', 'remédios', 'medicamentos', 'medicina',
            # Consultas e exames
            'consulta', 'medico', 'médico', 'dentista', 'psicólogo', 'psicologo',
            'terapeuta', 'fisioterapeuta', 'nutricionista', 'exame',
            'laboratorio', 'laboratório', 'clinica', 'clínica', 'hospital',
            'plano de saude', 'plano de saúde', 'unimed', 'amil', 'bradesco saude',
            # Beleza e estética
            'salao', 'salão', 'cabelereiro', 'cabeleireiro', 'manicure',
            'pedicure', 'spa', 'massagem', 'estetica', 'estética',
            'barbearia', 'barber', 'depilacao', 'depilação', 'beauty',
            'nail', 'designer', 'sobrancelha',
            # Academia e fitness
            'academia', 'gym', 'crossfit', 'pilates', 'yoga', 'personal',
            'trainer', 'box', 'fitness', 'smart fit', 'bodytech', 'selfit',
            'bio ritmo', 'competition', 'runner'
        ],
        'Roupas': [
            # Lojas de departamento
            'renner', 'cea', 'c&a', 'riachuelo', 'marisa', 'hering',
            'zara', 'forever 21', 'leader', 'h&m', 'uniqlo', 'gap',
            # Lojas de esporte e streetwear
            'centauro', 'decathlon', 'netshoes', 'nike', 'adidas', 'puma',
            'olympikus', 'mizuno', 'fila', 'under armour', 'track field',
            'garage', 'garage rio', 'osklen', 'farm', 'ellus', 'colcci',
            # Calçados e acessórios
            'arezzo', 'schutz', 'melissa', 'havaianas', 'grendha', 'ipanema',
            'via marte', 'santa lolla', 'loucos e santos', 'carmen steffens',
            'arezzo&co', 'anacapri', 'vizzano', 'beira rio', 'usaflex',
            'sk acessorios', 'vivara', 'pandora', 'swarovski', 'rommanel',
            'life', 'folheados', 'acessorios', 'joias', 'relogios', 'relógios',
            # Moda feminina e masculina
            'voah', 'amaro', 'dafiti', 'kanui', 'tricae', 'posthaus',
            'youcom', 'linho fino', 'shoulder', 'animale', 'mixed',
            'forum', 'cavalera', 'john john', 'damyller', 'richards',
            'polo wear', 'dudalina', 'aramis', 'vr', 'individual',
            # E-commerce e marketplace
            'amazon', 'americanas', 'submarino', 'magalu', 'magazine luiza',
            'shopee', 'aliexpress', 'shein', 'mercado livre', 'mercadolivre',
            'kabum', 'extra.com', 'casasbahia.com', 'netshoes', 'dafiti',
            # Lojas físicas e departamento
            'casas bahia', 'ponto frio', 'fastshop', 'leroy merlin',
            'telhanorte', 'c&c', 'tok&stok', 'etna', 'camicado', 'mobly',
            'ricardo eletro', 'magazine', 'carrefour',
            # Moda íntima e praia
            'hope', 'lupo', 'trifil', 'demillus', 'duloren', 'cia maritima',
            'salinas', 'lenny niemeyer', 'blue man', 'agua de coco',
            # Palavras genéricas de moda
            'loja', 'shopping', 'moda', 'vestuario', 'vestuário', 'boutique',
            'fashion', 'wear', 'brand', 'store', 'outlet', 'multimarcas',
            'roupas', 'calcados', 'calçados', 'sapatos', 'tenis', 'tênis',
            'bolsas', 'carteiras', 'cintos', 'bijuterias', 'semijoias'
        ]
    }

    # Procurar por correspondências nas categorias
    for categoria, palavras_chave in categorias.items():
        if any(palavra in descricao for palavra in palavras_chave):
            return categoria

    return "Roupas" 