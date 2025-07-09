import streamlit as st
import pandas as pd
import pdfplumber
import plotly.express as px
import re

# Configuração da página
st.set_page_config(
    page_title="Análise de Fatura Nubank",
    page_icon="💳",
    layout="wide"
)

# Título da aplicação
st.title("📊 Analisador de Faturas Nubank")

def processar_pdf(arquivo_pdf):
    """Processa o arquivo PDF da fatura do Nubank"""
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
                data = re.search(r'\d{2} [A-Z]{3}', linha).group()
                valor = re.search(r'R\$ \d+[.,]\d{2}', linha)
                if valor:
                    valor = float(valor.group().replace('R$ ', '').replace('.', '').replace(',', '.'))
                    descricao = re.sub(r'\d{2} [A-Z]{3}|R\$ \d+[.,]\d{2}', '', linha).strip()
                    transacoes.append({
                        'Data': data,
                        'Descrição': descricao,
                        'Valor': valor
                    })
            except:
                continue
    
    return pd.DataFrame(transacoes)

def classificar_transacao(descricao):
    """Classifica a transação em categorias"""
    descricao = descricao.lower()
    categorias = {
        'Alimentação': [
            'restaurante', 'ifood', 'food', 'mercado', 'supermercado', 'padaria',
            'confeitaria', 'bar', 'galeto', 'havaianas', 'absurda', 'katzsu',
            'garota do', 'abbraccio', 'leblon resta', 'rainha'
        ],
        'Transporte': [
            'uber', '99', 'taxi', 'combustível', 'posto', 'estacionamento',
            'transfer', 'voah', 'track field'
        ],
        'Entretenimento': [
            'netflix', 'spotify', 'cinema', 'teatro', 'show', 'bar',
            'field', 'track'
        ],
        'Saúde': [
            'farmácia', 'hospital', 'médico', 'consulta', 'clínica',
            'laboratório', 'exame'
        ],
        'Compras': [
            'shopping', 'loja', 'magazine', 'americanas', 'amazon',
            'vipeconceito', 'havaianas'
        ],
        'Serviços': [
            'energia', 'água', 'internet', 'telefone', 'celular',
            'parcela', 'pagamento'
        ],
    }
    
    for categoria, palavras_chave in categorias.items():
        if any(palavra in descricao for palavra in palavras_chave):
            if 'track field' in descricao.lower():
                return 'Compras'
            if 'absurda confeitaria' in descricao.lower():
                return 'Alimentação'
            return categoria
    return 'Outros'

# Upload do arquivo
arquivo = st.file_uploader("Faça upload da sua fatura (PDF ou CSV)", type=['pdf', 'csv'])

if arquivo is not None:
    try:
        if arquivo.name.endswith('.pdf'):
            df = processar_pdf(arquivo)
            df['Categoria'] = df['Descrição'].apply(classificar_transacao)
            
            # Calcular o total gasto
            total_gasto = df['Valor'].sum()
            
            # Criar resumo por categoria
            resumo = df.groupby('Categoria')['Valor'].sum().round(2)
            
            # Calcular percentual do total
            resumo_df = pd.DataFrame({
                'Total (R$)': resumo,
                '% do Total': (resumo / total_gasto * 100).round(2)
            })
            
            # Ordenar por valor total (maior para menor)
            resumo_df = resumo_df.sort_values('Total (R$)', ascending=False)
            
            # Adicionar total geral
            resumo_df.loc['TOTAL'] = [total_gasto, 100.00]
            
            # Exibir tabela principal com categorias expansíveis
            st.subheader("💰 Gastos por Categoria")
            
            # Para cada categoria (exceto TOTAL)
            for categoria in resumo_df.index[:-1]:  # Excluir a última linha (TOTAL)
                with st.expander(
                    f"📁 {categoria} - R$ {resumo_df.loc[categoria, 'Total (R$)']:.2f} ({resumo_df.loc[categoria, '% do Total']:.1f}%)"
                ):
                    # Filtrar e ordenar transações da categoria
                    transacoes_categoria = df[df['Categoria'] == categoria].sort_values('Valor', ascending=False)
                    
                    # Mostrar transações em formato de tabela
                    st.dataframe(
                        transacoes_categoria[['Data', 'Descrição', 'Valor']],
                        column_config={
                            "Valor": st.column_config.NumberColumn(
                                "Valor",
                                format="R$ %.2f"
                            )
                        },
                        hide_index=True
                    )
            
            # Mostrar total geral
            st.markdown(f"**TOTAL: R$ {total_gasto:.2f}**")
            
        else:
            st.error("Por favor, faça upload de um arquivo PDF da fatura do Nubank")
            
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar o arquivo: {str(e)}")
else:
    st.info("👆 Faça o upload da sua fatura para começar a análise!") 