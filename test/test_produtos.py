import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from databricks import sql


# ==========================================================
# CONECTOR
# ==========================================================
class DatabricksConnector:

    def conexao_databricks(self):
        connection = sql.connect(
            server_hostname="dbc-60646d9c-c02c.cloud.databricks.com",
            http_path="/sql/1.0/warehouses/5fa82bee3829f650",
            access_token="dapi32afc189d54cfaed3b3deed885507e3b",
        )
        self.cursor = connection.cursor()
        return connection

    def consultar_dataframe(self, query):
        conn = self.conexao_databricks()
        try:
            self.cursor.execute(query)
            colunas = [column[0] for column in self.cursor.description]
            dados = self.cursor.fetchall()
            return pd.DataFrame(dados, columns=colunas)
        finally:
            self.cursor.close()
            conn.close()


# ==========================================================
# CONFIG - COLUNAS
# ==========================================================
QUERY = "SELECT * FROM gold.mv_bi_produtos_v4_gerencial"

COL_DATA = "ANO_MES_DIGITACAO"          # coluna de data (mês/ano)
COL_PRODUTO = "PRODUTO"
COL_CONVENIO = "CORBAN"
COL_COMERCIAL = "COMERCIAL"
COL_FLUXO = "FLUXO"
COL_CORBAN = "GR_MACRO_CONVENIO"
COL_STATUS = "STATUS"              # ANALISE / APROVADO / CANCELADO / REPROVADO
COL_CANAL = "COMERCIAL"    # AUTO_CONTRATACAO / VENDA_EXTERNA / VENDA_INTERNA
COL_TIPO_FLUXO = "FLUXO"      # AUTOMATICO / MANUAL
COL_TIPO_CLIENTE = "TIPO_CLIENTE"  # NOVO / RECORRENTE
COL_VALOR_PRODUCAO = "TOT_FIN"
COL_CONTRATO_ID = "CODOPERACAO"
COL_CLIENTE_ID = "CPFCNPJ"
COL_PARCELA_VALOR = "VL_PMT"

FILTROS = {
    "Data Digitação": COL_DATA,
    "Produto": COL_PRODUTO,
    "Convênio": COL_CONVENIO,
    "Comercial": COL_COMERCIAL,
    "Fluxo": COL_FLUXO,
    "Corban": COL_CORBAN,
}

PALETTE = ["#4c7ea8", "#e0a94e", "#7d93a8", "#8fb3d9", "#c96b6b", "#6bbf8f"]


# ==========================================================
# CONFIGURAÇÃO DA PÁGINA + TEMA ESCURO
# ==========================================================
st.set_page_config(page_title="Produtos", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.stApp { background-color: #0d1321; }
h1, h2, h3, p, span, label, div { color: #e8ecf1; }
.kpi-container {
    background-color: #141b2d;
    border: 1px solid #232c42;
    border-radius: 10px;
    padding: 6px 20px;
}
.kpi-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 0;
    border-bottom: 1px dotted #3a4358;
}
.kpi-row:last-child { border-bottom: none; }
.kpi-label { color: #f2a488; font-size: 15px; font-weight: 700; }
.kpi-value { color: #ffffff; font-size: 21px; font-weight: 600; }
.chart-card {
    background-color: #141b2d;
    border: 1px solid #232c42;
    border-radius: 10px;
    padding: 8px 12px 0px 12px;
    margin-bottom: 14px;
}
div[data-testid="stHorizontalBlock"] { gap: 14px; }
</style>
""", unsafe_allow_html=True)


# ==========================================================
# CACHE DE DADOS
# ==========================================================
@st.cache_data(ttl=600, show_spinner="Consultando Databricks...")
def carregar_dados(query: str) -> pd.DataFrame:
    db = DatabricksConnector()
    return db.consultar_dataframe(query)


df = carregar_dados(QUERY)

st.title("Produtos")

if df.empty:
    st.warning("A consulta não retornou dados.")
    st.stop()


# ==========================================================
# FILTROS - LINHA SUPERIOR
# ==========================================================
filtro_container = st.columns(len(FILTROS))
df_filtrado = df.copy()

for (label, coluna), col_widget in zip(FILTROS.items(), filtro_container):
    if coluna not in df.columns:
        continue
    with col_widget:
        valores = sorted(df[coluna].dropna().unique().tolist())
        selecionados = st.multiselect(label, valores, default=[], key=f"filtro_{coluna}")
        if selecionados:
            df_filtrado = df_filtrado[df_filtrado[coluna].isin(selecionados)]


# ==========================================================
# HELPERS DE GRÁFICOS (ECHARTS)
# ==========================================================

def render_echarts_card(option_dict, chart_id, height=300):
    """Auxiliar para injetar o HTML/JS do ECharts no Streamlit."""
    option_json = json.dumps(option_dict, ensure_ascii=False)
    html = f"""
    <div id="{chart_id}" style="width:100%;height:{height}px;"></div>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
    <script>
        var chartDom = document.getElementById('{chart_id}');
        var myChart = echarts.init(chartDom);
        myChart.setOption({option_json});
        new ResizeObserver(function() {{ myChart.resize(); }}).observe(chartDom);
    </script>
    """
    with st.container():
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        components.html(html, height=height + 10, scrolling=False)
        st.markdown('</div>', unsafe_allow_html=True)


def grafico_linhas_echarts(df_, col_tempo, col_categoria, titulo, chart_id, height=300):
    """1. Somente Linhas com Porcentagem (%) de Contratos por mês."""
    if col_tempo not in df_.columns or col_categoria not in df_.columns or COL_CONTRATO_ID not in df_.columns:
        return

    # Contagem de contratos únicos por período e categoria
    tabela = df_.groupby([col_tempo, col_categoria])[COL_CONTRATO_ID].nunique().reset_index(name="qtd")
    pivot = tabela.pivot(index=col_tempo, columns=col_categoria, values="qtd").fillna(0).sort_index()
    
    total_por_tempo = pivot.sum(axis=1).replace(0, 1)
    categorias = pivot.columns.tolist()
    eixo_tempo = [str(v) for v in pivot.index.tolist()]

    series = []
    for i, cat in enumerate(categorias):
        pct = (pivot[cat] / total_por_tempo * 100).round(2)
        
        series.append({
            "name": f"%{cat}",
            "type": "line",
            "smooth": True,
            "symbolSize": 6,
            "data": pct.tolist(),
            "itemStyle": {"color": PALETTE[i % len(PALETTE)]},
            "lineStyle": {"width": 2},
            "label": {
                "show": True,
                "position": "top",
                "formatter": "{c}%",
                "color": "#e8ecf1",
                "fontSize": 10,
                "fontWeight": "bold"
            },
        })

    option = {
        "backgroundColor": "transparent",
        "title": {"text": titulo, "textStyle": {"color": "#e8ecf1", "fontSize": 14}},
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0, "textStyle": {"color": "#9aa5b1"}, "type": "scroll"},
        "grid": {"containLabel": True, "top": 40, "bottom": 50, "left": 10, "right": 10},
        "xAxis": {
            "type": "category",
            "data": eixo_tempo,
            "axisLine": {"lineStyle": {"color": "#3a4358"}},
            "axisLabel": {"color": "#9aa5b1"},
        },
        "yAxis": {"type": "value", "show": False, "min": 0},
        "series": series,
    }
    render_echarts_card(option, chart_id, height)


def grafico_barras_empilhadas_echarts(df_, col_tempo, col_categoria, titulo, chart_id, height=300):
    """2. Somente Colunas/Barras Empilhadas (Quantidade de Contratos Únicos)."""
    if col_tempo not in df_.columns or col_categoria not in df_.columns or COL_CONTRATO_ID not in df_.columns:
        return

    # Contagem de contratos únicos
    tabela = df_.groupby([col_tempo, col_categoria])[COL_CONTRATO_ID].nunique().reset_index(name="qtd")
    pivot = tabela.pivot(index=col_tempo, columns=col_categoria, values="qtd").fillna(0).sort_index()
    categorias = pivot.columns.tolist()
    eixo_tempo = [str(v) for v in pivot.index.tolist()]

    series = []
    for i, cat in enumerate(categorias):
        series.append({
            "name": str(cat),
            "type": "bar",
            "stack": "total",
            "data": pivot[cat].round(0).tolist(),
            "itemStyle": {"color": PALETTE[i % len(PALETTE)]},
            "label": {
                "show": True,
                "position": "inside",
                "formatter": "{c}",
                "color": "#fff",
                "fontSize": 10,
            },
        })

    option = {
        "backgroundColor": "transparent",
        "title": {"text": titulo, "textStyle": {"color": "#e8ecf1", "fontSize": 14}},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"bottom": 0, "textStyle": {"color": "#9aa5b1"}, "type": "scroll"},
        "grid": {"containLabel": True, "top": 40, "bottom": 50, "left": 10, "right": 10},
        "xAxis": {
            "type": "category",
            "data": eixo_tempo,
            "axisLine": {"lineStyle": {"color": "#3a4358"}},
            "axisLabel": {"color": "#9aa5b1"},
        },
        "yAxis": {"type": "value", "show": False},
        "series": series,
    }
    render_echarts_card(option, chart_id, height)


def grafico_combo_echarts(df_, col_tempo, col_categoria, titulo, chart_id, height=300):
    """3. Combo (Barras empilhadas com Qtd Única de COL_CONTRATO_ID + Linha de % dos Contratos)."""
    if col_tempo not in df_.columns or col_categoria not in df_.columns or COL_CONTRATO_ID not in df_.columns:
        return

    # Contagem exata de contratos únicos (COL_CONTRATO_ID)
    tabela = df_.groupby([col_tempo, col_categoria])[COL_CONTRATO_ID].nunique().reset_index(name="qtd")
    pivot = tabela.pivot(index=col_tempo, columns=col_categoria, values="qtd").fillna(0).sort_index()
    categorias = pivot.columns.tolist()
    eixo_tempo = [str(v) for v in pivot.index.tolist()]
    total_por_tempo = pivot.sum(axis=1)

    series = []
    # 1. Barras Empilhadas -> Quantidade única de ID_CONTRATO
    for i, cat in enumerate(categorias):
        series.append({
            "name": str(cat),
            "type": "bar",
            "stack": "total",
            "data": pivot[cat].round(0).tolist(),
            "itemStyle": {"color": PALETTE[i % len(PALETTE)]},
            "label": {
                "show": True,
                "position": "inside",
                "formatter": "{c}",
                "color": "#fff",
                "fontSize": 10,
            },
        })

    # 2. Linhas -> Percentual daquele tipo de contrato sobre o total do mês
    for i, cat in enumerate(categorias):
        pct = (pivot[cat] / total_por_tempo.replace(0, 1) * 100).round(2)
        series.append({
            "name": f"% {cat}",
            "type": "line",
            "yAxisIndex": 1,
            "data": pct.tolist(),
            "smooth": True,
            "symbolSize": 6,
            "lineStyle": {"width": 2},
            "label": {"show": True, "formatter": "{c}%", "color": "#e8ecf1", "fontSize": 10},
        })

    option = {
        "backgroundColor": "transparent",
        "title": {"text": titulo, "textStyle": {"color": "#e8ecf1", "fontSize": 14}},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"bottom": 0, "textStyle": {"color": "#9aa5b1"}, "type": "scroll"},
        "grid": {"containLabel": True, "top": 40, "bottom": 50, "left": 10, "right": 10},
        "xAxis": {
            "type": "category",
            "data": eixo_tempo,
            "axisLine": {"lineStyle": {"color": "#3a4358"}},
            "axisLabel": {"color": "#9aa5b1"},
        },
        "yAxis": [
            {"type": "value", "show": False},
            {"type": "value", "show": False, "min": 0, "max": 100},
        ],
        "series": series,
    }
    render_echarts_card(option, chart_id, height)


def render_kpi_panel(itens):
    linhas = "".join(
        f'<div class="kpi-row"><span class="kpi-label">{label}</span>'
        f'<span class="kpi-value">{valor}</span></div>'
        for label, valor in itens
    )
    st.markdown(f'<div class="kpi-container">{linhas}</div>', unsafe_allow_html=True)


# ==========================================================
# LAYOUT PRINCIPAL - KPIs + GRÁFICOS
# ==========================================================
col_kpi, col_chart1, col_chart2 = st.columns([1, 2, 2])

with col_kpi:
    itens_kpi = []
    if COL_VALOR_PRODUCAO in df_filtrado.columns:
        itens_kpi.append(("Produção", f"R$ {df_filtrado[COL_VALOR_PRODUCAO].sum():,.2f}"))
    if COL_CONTRATO_ID in df_filtrado.columns:
        itens_kpi.append(("Contratos", f"{df_filtrado[COL_CONTRATO_ID].nunique():,}"))
    if COL_CLIENTE_ID in df_filtrado.columns:
        itens_kpi.append(("Clientes", f"{df_filtrado[COL_CLIENTE_ID].nunique():,}"))
    if COL_VALOR_PRODUCAO in df_filtrado.columns and COL_CONTRATO_ID in df_filtrado.columns:
        n_contratos = max(df_filtrado[COL_CONTRATO_ID].nunique(), 1)
        itens_kpi.append(("TKM Contratos", f"R$ {df_filtrado[COL_VALOR_PRODUCAO].sum() / n_contratos:,.2f}"))
    if COL_PARCELA_VALOR in df_filtrado.columns:
        itens_kpi.append(("TKM Parcela", f"R$ {df_filtrado[COL_PARCELA_VALOR].mean():,.2f}"))

    render_kpi_panel(itens_kpi)

with col_chart1:
    # GRÁFICO 1: Apenas porcentagens (%) de Contratos em linhas
    grafico_linhas_echarts(
        df_filtrado, COL_DATA, COL_STATUS, "Status dos Contratos - Quantidade", "chart_status_linhas"
    )

with col_chart2:
    # GRÁFICO 2: Apenas barras empilhadas de quantidade de Contratos
    grafico_barras_empilhadas_echarts(
        df_filtrado, COL_DATA, COL_STATUS, "Status dos Contratos - Quantidade", "chart_status_barras"
    )

col_c3, col_c4, col_c5 = st.columns(3)

with col_c3:
    grafico_combo_echarts(df_filtrado, COL_DATA, COL_CANAL, "Canal de Contratação", "chart_canal", height=280)

with col_c4:
    grafico_combo_echarts(df_filtrado, COL_DATA, COL_TIPO_FLUXO, "Fluxo de Contratação", "chart_fluxo", height=280)

with col_c5:
    grafico_combo_echarts(df_filtrado, COL_DATA, COL_TIPO_CLIENTE, "Clientes Novos x Recorrentes", "chart_cliente", height=280)


# ==========================================================
# TABELA DE DADOS
# ==========================================================
with st.expander("Ver dados detalhados"):
    st.dataframe(df_filtrado, use_container_width=True)
    st.download_button(
        "Baixar CSV filtrado",
        data=df_filtrado.to_csv(index=False).encode("utf-8"),
        file_name="produtos_filtrado.csv",
        mime="text/csv",
    )