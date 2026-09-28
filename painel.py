"""
Painel de indicadores de saneamento (SNIS + SNISA)
====================================================

Este app corrige os seguintes problemas encontrados no script original:

1. SyntaxError: `municipios.drop_duplicates()zzzzz` -> `municipios.drop_duplicates()`.
2. Bug de lógica em `consulta_snis`, `consulta_snisa` e `uniao_registros`: essas
   funções usavam as variáveis globais fixas `indicador_snis` / `indicador_snisa`
   (definidas uma única vez no topo do script original) em vez do parâmetro
   `indicador` recebido pela própria função. Isso fazia com que, não importa
   qual indicador o usuário pedisse, o "indicador equivalente" calculado fosse
   sempre o mesmo (IN055 / IAG0001). Neste app, todo o cálculo de equivalência
   usa o parâmetro `indicador` da chamada atual.
3. Inconsistência em `obter_municipios`: para esgoto o código usava
   `df_snisa_esgoto["UF"]` (o dataframe inteiro) em vez da coluna local já
   filtrada/renomeada `municipios_snis_esgoto["UF"]`. Corrigido para manter o
   mesmo padrão usado em água.
4. Dependência de variáveis globais não declaradas dentro das funções
   (`df_consulta`, `indicadores_snis`, `indicadores_snisa`). Neste app elas são
   sempre passadas como parâmetro/calculadas via `st.cache_data`, então não há
   risco de `NameError` por esquecer de rodar uma célula antes de outra.

Como rodar:
    streamlit run painel_saneamento.py

Requisitos:
    pip install streamlit pandas plotly

Os arquivos CSV são esperados na pasta "Data_v2", com os mesmos nomes usados
no script original. Ajuste a constante DATA_DIR abaixo se necessário.
"""

import re
import unicodedata

import pandas as pd
import plotly.express as px
import streamlit as st

# ---------------------------------------------------------------------------
# Configuração geral
# ---------------------------------------------------------------------------

DATA_DIR = "Data_v2"
DATA_SUFFIX = "20260927"

UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}

st.set_page_config(page_title="Painel de Saneamento (SNIS/SNISA)", layout="wide")


# ---------------------------------------------------------------------------
# Carregamento de dados (cacheado)
# ---------------------------------------------------------------------------

def _normalizar_nome(texto: str) -> str:
    """Remove acentos, espaços, underscores e caixa para comparar nomes de coluna."""
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-z0-9]+", "", texto)
    return texto


def _padronizar_colunas(df: pd.DataFrame, nomes_esperados: list, nome_arquivo: str):
    """Renomeia colunas do df para os nomes esperados, tolerando diferenças de
    acento/caixa/espaço/underscore no cabeçalho original. Retorna (df, faltando)."""
    mapa_normalizado = {_normalizar_nome(c): c for c in df.columns}
    renomear = {}
    faltando = []
    for esperado in nomes_esperados:
        chave = _normalizar_nome(esperado)
        if chave in mapa_normalizado:
            coluna_real = mapa_normalizado[chave]
            if coluna_real != esperado:
                renomear[coluna_real] = esperado
        else:
            faltando.append(esperado)
    if renomear:
        df = df.rename(columns=renomear)
    return df, faltando


@st.cache_resource(show_spinner="Carregando bases de dados...")
def carregar_dados():
    df_snisa_agua = pd.read_csv(f"{DATA_DIR}/SNISA_tratado_agua_{DATA_SUFFIX}.csv", low_memory=False)
    df_snisa_esgoto = pd.read_csv(f"{DATA_DIR}/SNISA_tratado_esgoto_{DATA_SUFFIX}.csv", low_memory=False)
    df_snis = pd.read_parquet(f"{DATA_DIR}/snis_completo_20260928.parquet")    
    df_relacao_esgoto = pd.read_csv(f"{DATA_DIR}/relacao_esgoto_{DATA_SUFFIX}.csv", low_memory=False)
    df_relacao_agua = pd.read_csv(f"{DATA_DIR}/relacao_agua_{DATA_SUFFIX}.csv", low_memory=False)

    avisos = []

    df_relacao_agua, faltando = _padronizar_colunas(
        df_relacao_agua, ["CÓDIGO", "View Codigo", "INDICADOR EQUIVALENTE"], "relacao_agua.csv"
    )
    if faltando:
        avisos.append((faltando, list(df_relacao_agua.columns), "relacao_agua.csv"))

    df_relacao_esgoto, faltando = _padronizar_colunas(
        df_relacao_esgoto, ["CÓDIGO", "View Codigo", "INDICADOR EQUIVALENTE"], "relacao_esgoto.csv"
    )
    if faltando:
        avisos.append((faltando, list(df_relacao_esgoto.columns), "relacao_esgoto.csv"))

    df_snisa_agua, faltando = _padronizar_colunas(
        df_snisa_agua, ["Município", "UF", "CAD0006"], "SNISA_tratado_agua"
    )
    if faltando:
        avisos.append((faltando, list(df_snisa_agua.columns), "SNISA_tratado_agua"))

    df_snisa_esgoto, faltando = _padronizar_colunas(
        df_snisa_esgoto, ["Município", "UF", "CAD0006"], "SNISA_tratado_esgoto"
    )
    if faltando:
        avisos.append((faltando, list(df_snisa_esgoto.columns), "SNISA_tratado_esgoto"))

    df_snis, faltando = _padronizar_colunas(
        df_snis,
        ["Município", "Estado", "Sigla do Prestador", "Natureza jurídica"],
        "snis_completo",
    )
    if faltando:
        avisos.append((faltando, list(df_snis.columns), "snis_completo"))

    return df_snis, df_snisa_agua, df_snisa_esgoto, df_relacao_agua, df_relacao_esgoto, avisos


@st.cache_data(show_spinner=False)
def criar_df_consulta(_df_snis, _df_snisa_agua, _df_snisa_esgoto):
    df_snis, df_snisa_agua, df_snisa_esgoto = _df_snis, _df_snisa_agua, _df_snisa_esgoto
    df_snis_consulta = df_snis[["Município", "Estado", "Sigla do Prestador"]].copy()
    df_snisa_agua_consulta = df_snisa_agua[["Município", "UF", "CAD0006"]].copy()
    df_snisa_esgoto_consulta = df_snisa_esgoto[["Município", "UF", "CAD0006"]].copy()

    df_snisa_agua_consulta["Estado"] = df_snisa_agua_consulta["UF"]
    df_snisa_esgoto_consulta["Estado"] = df_snisa_esgoto_consulta["UF"]

    df_snisa_agua_consulta["Sigla do Prestador"] = df_snisa_agua_consulta["CAD0006"]
    df_snisa_esgoto_consulta["Sigla do Prestador"] = df_snisa_esgoto_consulta["CAD0006"]

    df_snisa_agua_consulta = df_snisa_agua_consulta.drop(columns=["CAD0006", "UF"])
    df_snisa_esgoto_consulta = df_snisa_esgoto_consulta.drop(columns=["CAD0006", "UF"])

    df_consulta = pd.concat(
        [df_snis_consulta, df_snisa_agua_consulta, df_snisa_esgoto_consulta]
    )

    mask = df_consulta["Sigla do Prestador"].str.contains(r"\|", na=False)
    df_consulta.loc[mask, "Sigla do Prestador"] = "Múltiplos"

    df_consulta = df_consulta.drop_duplicates()

    return df_consulta


@st.cache_data(show_spinner=False)
def obter_estados(_df_consulta):
    df_consulta = _df_consulta
    estados = sorted(e for e in df_consulta["Estado"].dropna().unique() if e in UFS_VALIDAS)
    return estados


@st.cache_data(show_spinner="Carregando municípios do estado...")
def obter_municipios(_df_snis, _df_snisa_agua, _df_snisa_esgoto, estado):
    df_snis, df_snisa_agua, df_snisa_esgoto = _df_snis, _df_snisa_agua, _df_snisa_esgoto
    municipios_snis = df_snis[["Município", "Estado"]].drop_duplicates()

    municipios_snis_agua = df_snisa_agua[["Município", "UF"]].drop_duplicates().copy()
    municipios_snis_esgoto = df_snisa_esgoto[["Município", "UF"]].drop_duplicates().copy()

    municipios_snis_agua["Estado"] = municipios_snis_agua["UF"]
    # Correção: usar a coluna local já filtrada, e não o dataframe inteiro de esgoto.
    municipios_snis_esgoto["Estado"] = municipios_snis_esgoto["UF"]

    municipios_snis_agua = municipios_snis_agua.drop(columns=["UF"])
    municipios_snis_esgoto = municipios_snis_esgoto.drop(columns=["UF"])

    municipios = pd.concat([municipios_snis, municipios_snis_agua, municipios_snis_esgoto])
    # Correção: removido o "zzzzz" que causava SyntaxError.
    municipios = municipios.drop_duplicates()

    municipios_do_uf = municipios[municipios["Estado"] == estado]["Município"]
    lista_municipios = sorted(municipios_do_uf.dropna().unique().tolist())
    return lista_municipios


@st.cache_data(show_spinner="Carregando prestadores do município...")
def obter_prestadores(_df_consulta, estado, municipio):
    df_consulta = _df_consulta
    df_consulta_filtrado = df_consulta.query("Estado == @estado & `Município` == @municipio")
    lista_prestadores = sorted(
        df_consulta_filtrado["Sigla do Prestador"].dropna().unique().tolist()
    )
    return lista_prestadores


@st.cache_data(show_spinner="Carregando indicadores disponíveis...")
def obter_indicadores(_df_snis, _df_snisa_agua, _df_snisa_esgoto,
                       _df_relacao_agua, _df_relacao_esgoto,
                       estado, cidade, prestador):
    df_snis, df_snisa_agua, df_snisa_esgoto = _df_snis, _df_snisa_agua, _df_snisa_esgoto
    df_relacao_agua, df_relacao_esgoto = _df_relacao_agua, _df_relacao_esgoto

    def obter_indicadores_snisa(df_snisa, eh_agua, estado, cidade, prestador):
        df_snisa_temp = df_snisa.query(
            "UF == @estado & `Município` == @cidade & `CAD0006` == @prestador"
        )
        if df_snisa_temp.empty:
            return []

        colunas_para_remover = [
            c for c in ["Ano", "Quantidade_Prestadores", "CAD0006_Detalhe",
                        "Multiplos_Prestadores", "chave"]
            if c in df_snisa_temp.columns
        ]
        df_snisa_temp = df_snisa_temp.drop(columns=colunas_para_remover)

        idx = df_snisa_temp.columns.get_loc("CAD0006")
        indicadores_snisa_cols = df_snisa_temp.columns[idx + 1:].tolist()

        view_codes = []
        for indicador in indicadores_snisa_cols:
            try:
                df_relacao = df_relacao_agua if eh_agua else df_relacao_esgoto
                view_code = df_relacao.query("`CÓDIGO` == @indicador")["View Codigo"].values[0]
                view_codes.append(view_code)
            except IndexError:
                continue
        return view_codes

    def obter_indicadores_snis(estado, cidade, prestador):
        df_snis_temp = df_snis.query(
            "Estado == @estado & `Município` == @cidade & `Sigla do Prestador` == @prestador"
        )
        if df_snis_temp.empty:
            return []

        colunas_para_remover = [
            c for c in ["Eh_Agua", "Eh_Esgoto", "Qtd_Prestadores_Agua",
                        "Qtd_Prestadores_Esgoto", "Multiplos_Prestadores_Agua",
                        "Multiplos_Prestadores_Esgoto"]
            if c in df_snis_temp.columns
        ]
        df_snis_temp = df_snis_temp.drop(columns=colunas_para_remover)

        idx = df_snis_temp.columns.get_loc("Natureza jurídica")
        indicadores_snis_cols = df_snis_temp.columns[idx + 1:].tolist()
        return indicadores_snis_cols

    indicadores_snis = obter_indicadores_snis(estado, cidade, prestador)
    indicadores_snisa_agua = obter_indicadores_snisa(df_snisa_agua, True, estado, cidade, prestador)
    indicadores_snisa_esgoto = obter_indicadores_snisa(df_snisa_esgoto, False, estado, cidade, prestador)

    indicadores_snisa = list(set(indicadores_snisa_esgoto + indicadores_snisa_agua))

    return indicadores_snis, indicadores_snisa


# ---------------------------------------------------------------------------
# Consultas (bugs de "indicador" corrigidos: sempre usa o parâmetro recebido)
# ---------------------------------------------------------------------------

def consulta_snis(df_snis, df_relacao_agua, df_relacao_esgoto,
                   indicadores_snis, indicadores_snisa,
                   estado, cidade, prestador, indicador):

    if indicador in indicadores_snis:
        df_snis_temp = df_snis.query(
            "Estado == @estado & `Município` == @cidade & `Sigla do Prestador` == @prestador"
        )
        try:
            df_snis_temp = df_snis_temp[
                ["Estado", "Município", "Sigla do Prestador", "Ano de Referência", indicador]
            ]
        except KeyError:
            df_snis_temp = df_snis_temp[
                ["Estado", "Município", "Sigla do Prestador", "Ano", indicador]
            ]
        return df_snis_temp

    if indicador in indicadores_snisa:
        try:
            indicador_equivalente = df_relacao_agua[
                df_relacao_agua["View Codigo"] == indicador
            ]["INDICADOR EQUIVALENTE"].values[0]
        except IndexError:
            indicador_equivalente = df_relacao_esgoto[
                df_relacao_esgoto["View Codigo"] == indicador
            ]["INDICADOR EQUIVALENTE"].values[0]

        indicador_equivalente_full_name = None
        for ind in indicadores_snis:
            if indicador_equivalente in ind:
                indicador_equivalente_full_name = ind
                break
        if indicador_equivalente_full_name is None:
            return pd.DataFrame()

        df_snis_temp = df_snis.query(
            "Estado == @estado & `Município` == @cidade & `Sigla do Prestador` == @prestador"
        )
        try:
            df_snis_temp = df_snis_temp[
                ["Estado", "Município", "Sigla do Prestador", "Ano de Referência",
                 indicador_equivalente_full_name]
            ]
        except KeyError:
            df_snis_temp = df_snis_temp[
                ["Estado", "Município", "Sigla do Prestador", "Ano",
                 indicador_equivalente_full_name]
            ]
        return df_snis_temp

    return pd.DataFrame()


def consulta_snisa(df_snisa_agua, df_snisa_esgoto, df_relacao_agua, df_relacao_esgoto,
                    indicadores_snis, indicadores_snisa,
                    estado, cidade, prestador, indicador):

    if indicador in indicadores_snisa:
        codigo_snisa = indicador.split(" - ")[0]

        if codigo_snisa in df_snisa_esgoto.columns.tolist():
            df_snisa_temp = df_snisa_esgoto.query(
                "UF == @estado & `Município` == @cidade & `CAD0006` == @prestador"
            )
            return df_snisa_temp[["UF", "Município", "CAD0006", "Ano", codigo_snisa]]
        elif codigo_snisa in df_snisa_agua.columns.tolist():
            df_snisa_temp = df_snisa_agua.query(
                "UF == @estado & `Município` == @cidade & `CAD0006` == @prestador"
            )
            return df_snisa_temp[["UF", "Município", "CAD0006", "Ano", codigo_snisa]]
        else:
            return pd.DataFrame()

    if indicador in indicadores_snis:
        # Correção: usar o indicador recebido como parâmetro, não a constante global.
        codigo_indicador_snis = indicador.split(" - ")[0]

        serie_agua = df_relacao_agua.loc[
            df_relacao_agua["INDICADOR EQUIVALENTE"] == codigo_indicador_snis, "CÓDIGO"
        ]
        serie_esgoto = df_relacao_esgoto.loc[
            df_relacao_esgoto["INDICADOR EQUIVALENTE"] == codigo_indicador_snis, "CÓDIGO"
        ]

        for serie, df_snisa_base in ((serie_agua, df_snisa_agua), (serie_esgoto, df_snisa_esgoto)):
            if not serie.empty:
                codigo_equivalente = serie.values[0]
                if codigo_equivalente in df_snisa_base.columns:
                    df_snisa_temp = df_snisa_base.query(
                        "UF == @estado & `Município` == @cidade & `CAD0006` == @prestador"
                    )
                    return df_snisa_temp[["UF", "Município", "CAD0006", "Ano", codigo_equivalente]]

        # Não existe (ou não está mais disponível) equivalente no SNISA para
        # este indicador do SNIS. Retorna vazio em vez de estourar IndexError.
        return pd.DataFrame()

    return pd.DataFrame()


def uniao_registros(df_snis, df_snisa_agua, df_snisa_esgoto, df_relacao_agua, df_relacao_esgoto,
                     indicadores_snis, indicadores_snisa,
                     estado, cidade, prestador, indicador):
    """Retorna (df_final, aviso).

    `aviso` é None quando SNIS e SNISA foram unidos normalmente, ou uma
    mensagem explicando por que apenas uma das duas bases está disponível
    para este indicador (ex.: indicador do SNIS sem equivalente no SNISA)."""

    df_snisa_res = consulta_snisa(
        df_snisa_agua, df_snisa_esgoto, df_relacao_agua, df_relacao_esgoto,
        indicadores_snis, indicadores_snisa, estado, cidade, prestador, indicador,
    )
    df_snis_res = consulta_snis(
        df_snis, df_relacao_agua, df_relacao_esgoto,
        indicadores_snis, indicadores_snisa, estado, cidade, prestador, indicador,
    )

    if df_snisa_res.empty or df_snis_res.empty:
        # Sem par equivalente em uma das duas bases: devolve o que existir.
        if not df_snis_res.empty and df_snisa_res.empty:
            resultado = df_snis_res
            aviso = "Indicador descontinuado no SNISA. Dados disponíveis até 2022 (apenas SNIS)."
        elif not df_snisa_res.empty and df_snis_res.empty:
            resultado = df_snisa_res
            aviso = "Indicador exclusivo do SNISA. Não há série histórica equivalente no SNIS."
        else:
            resultado = pd.DataFrame()
            aviso = "Não foram encontrados dados para esse indicador nesta combinação de filtros."

        if not resultado.empty:
            resultado = resultado.rename(columns={
                "UF": "Estado", "CAD0006": "Sigla do Prestador", "Ano de Referência": "Ano",
            })
            col_indicador = [c for c in resultado.columns
                             if c not in ("Estado", "Município", "Sigla do Prestador", "Ano")]
            if col_indicador:
                resultado = resultado.rename(columns={col_indicador[0]: indicador})
                # Garante que o valor vira numérico mesmo vindo só do SNIS
                # (que usa vírgula decimal) ou só do SNISA.
                resultado[indicador] = (
                    resultado[indicador].astype(str).str.replace(",", ".", regex=False)
                )
                resultado[indicador] = pd.to_numeric(resultado[indicador], errors="coerce")

        return resultado, aviso

    df_snisa_res = df_snisa_res.rename(columns={"UF": "Estado", "CAD0006": "Sigla do Prestador"})
    df_snis_res = df_snis_res.rename(columns={"Ano de Referência": "Ano"})

    if indicador in indicadores_snis:
        # Correção: usar o parâmetro `indicador`, não a constante global `indicador_snis`.
        codigo_indicador_snis = indicador.split(" - ")[0]

        serie_agua = df_relacao_agua.loc[
            df_relacao_agua["INDICADOR EQUIVALENTE"] == codigo_indicador_snis, "CÓDIGO"
        ]
        serie_esgoto = df_relacao_esgoto.loc[
            df_relacao_esgoto["INDICADOR EQUIVALENTE"] == codigo_indicador_snis, "CÓDIGO"
        ]

        if not serie_agua.empty:
            indicador_snisa_equivalente = serie_agua.values[0]
        elif not serie_esgoto.empty:
            indicador_snisa_equivalente = serie_esgoto.values[0]
        else:
            # Segurança extra: não deveria chegar aqui, já que df_snisa_res não
            # estava vazio, mas evita IndexError em qualquer cenário inesperado.
            return df_snis_res, "Indicador descontinuado no SNISA. Dados disponíveis até 2022 (apenas SNIS)."

        df_snisa_res = df_snisa_res.rename(columns={indicador_snisa_equivalente: indicador})
        df_snisa_res[indicador] = pd.to_numeric(df_snisa_res[indicador], errors="coerce")

        df_snis_res[indicador] = (
            df_snis_res[indicador].astype(str).str.replace(",", ".", regex=False)
        )
        df_snis_res[indicador] = pd.to_numeric(df_snis_res[indicador], errors="coerce")

        df_final = pd.concat([df_snis_res, df_snisa_res])
        df_final = df_final.sort_values(by="Ano", ascending=True)
        return df_final, None

    else:
        codigo_snisa = indicador.split(" - ")[0]

        serie_esgoto_eq = df_relacao_esgoto.loc[
            df_relacao_esgoto["CÓDIGO"] == codigo_snisa, "INDICADOR EQUIVALENTE"
        ]
        serie_agua_eq = df_relacao_agua.loc[
            df_relacao_agua["CÓDIGO"] == codigo_snisa, "INDICADOR EQUIVALENTE"
        ]

        if not serie_esgoto_eq.empty:
            codigo_snis_equivalente = serie_esgoto_eq.values[0]
        elif not serie_agua_eq.empty:
            codigo_snis_equivalente = serie_agua_eq.values[0]
        else:
            df_snisa_res[codigo_snisa] = pd.to_numeric(df_snisa_res[codigo_snisa], errors="coerce")
            df_snisa_res = df_snisa_res.rename(columns={codigo_snisa: indicador})
            aviso = "Indicador exclusivo do SNISA. Não há série histórica equivalente no SNIS."
            return df_snisa_res.sort_values(by="Ano", ascending=True), aviso

        indicador_snis_equivalente = None
        for cod in indicadores_snis:
            if codigo_snis_equivalente in cod:
                indicador_snis_equivalente = cod
                break
        if indicador_snis_equivalente is None:
            df_snisa_res[codigo_snisa] = pd.to_numeric(df_snisa_res[codigo_snisa], errors="coerce")
            df_snisa_res = df_snisa_res.rename(columns={codigo_snisa: indicador})
            aviso = "Indicador exclusivo do SNISA. Não há série histórica equivalente no SNIS."
            return df_snisa_res.sort_values(by="Ano", ascending=True), aviso

        df_snisa_res[codigo_snisa] = pd.to_numeric(df_snisa_res[codigo_snisa], errors="coerce")

        df_snis_res[indicador_snis_equivalente] = (
            df_snis_res[indicador_snis_equivalente].astype(str).str.replace(",", ".", regex=False)
        )
        df_snis_res[indicador_snis_equivalente] = pd.to_numeric(
            df_snis_res[indicador_snis_equivalente], errors="coerce"
        )

        df_snis_res = df_snis_res.rename(columns={indicador_snis_equivalente: codigo_snisa})

        df_final = pd.concat([df_snis_res, df_snisa_res])
        # Correção: padroniza o nome da coluna do indicador para o rótulo
        # completo escolhido pelo usuário (antes ficava com o código curto do
        # SNISA, o que não batia com o nome usado na interface).
        df_final = df_final.rename(columns={codigo_snisa: indicador})
        df_final = df_final.sort_values(by="Ano", ascending=True)
        return df_final, None


# ---------------------------------------------------------------------------
# Interface Streamlit
# ---------------------------------------------------------------------------

def _buscar_valor_normalizado(linha: pd.Series, candidatos: list):
    """Procura, numa linha (Series), o primeiro valor não vazio cujo nome de
    coluna normalizado bata com algum dos candidatos (tolerante a acento,
    caixa, espaço e underscore)."""
    normalizados = {_normalizar_nome(col): col for col in linha.index}
    for candidato in candidatos:
        chave = _normalizar_nome(candidato)
        if chave in normalizados:
            valor = linha[normalizados[chave]]
            if pd.notna(valor) and str(valor).strip() != "":
                return str(valor).strip()
    return None


def obter_metadados_indicador(indicador, indicadores_snis, indicadores_snisa,
                               df_relacao_agua, df_relacao_esgoto):
    """Busca metadados (grupo, palavra-chave, unidade, informação) do
    indicador nas tabelas de relação água/esgoto."""
    linha = None

    if indicador in indicadores_snisa:
        for df_rel in (df_relacao_agua, df_relacao_esgoto):
            correspondencia = df_rel[df_rel["View Codigo"] == indicador]
            if not correspondencia.empty:
                linha = correspondencia.iloc[0]
                break
    elif indicador in indicadores_snis:
        codigo = indicador.split(" - ")[0]
        for df_rel in (df_relacao_agua, df_relacao_esgoto):
            correspondencia = df_rel[df_rel["INDICADOR EQUIVALENTE"] == codigo]
            if not correspondencia.empty:
                linha = correspondencia.iloc[0]
                break

    if linha is None:
        return None

    return {
        "Grupo": _buscar_valor_normalizado(
            linha, ["Grupo", "Categoria", "Tema", "Grupo Indicador", "Grupo do Indicador"]
        ),
        "Palavra-chave": _buscar_valor_normalizado(
            linha, ["Palavra-chave", "Palavra Chave", "Palavras-chave", "Keyword", "Tag"]
        ),
        "Unidade": _buscar_valor_normalizado(
            linha, ["Unidade", "Unidade de Medida", "Unit", "Und"]
        ),
        "Informação": _buscar_valor_normalizado(
            linha, ["Informação", "Descrição", "Observação", "Info", "Detalhes", "Nota", "Comentário"]
        ),
    }


st.title("📊 Painel de Indicadores de Saneamento (SNIS + SNISA)")

try:
    (df_snis, df_snisa_agua, df_snisa_esgoto, df_relacao_agua,
     df_relacao_esgoto, avisos_colunas) = carregar_dados()
except FileNotFoundError as e:
    st.error(
        "Não foi possível encontrar os arquivos de dados. Verifique se a pasta "
        f"'{DATA_DIR}' está no mesmo diretório do app e contém os CSVs esperados.\n\n"
        f"Detalhe: {e}"
    )
    st.stop()

if avisos_colunas:
    with st.expander("⚠️ Colunas não encontradas nos arquivos de origem", expanded=True):
        for faltando, colunas_disponiveis, nome_arquivo in avisos_colunas:
            st.warning(
                f"Em **{nome_arquivo}** não encontrei: {faltando}.\n\n"
                f"Colunas disponíveis no arquivo: {colunas_disponiveis}"
            )
        st.caption(
            "O app tenta casar nomes de coluna ignorando acento, maiúscula/minúscula e "
            "espaços/underscores. Se uma coluna aparece aqui, o nome real é bem diferente "
            "do esperado e talvez seja necessário ajustar manualmente o CSV ou o código."
        )

df_consulta = criar_df_consulta(df_snis, df_snisa_agua, df_snisa_esgoto)

with st.sidebar:
    st.header("Filtros")

    lista_estados = obter_estados(df_consulta)
    estado_sel = st.selectbox("Estado", lista_estados, index=None, placeholder="Selecione um estado")

    if estado_sel:
        with st.spinner("Filtrando municípios..."):
            lista_municipios = obter_municipios(df_snis, df_snisa_agua, df_snisa_esgoto, estado_sel)
    else:
        lista_municipios = []
    municipio_sel = st.selectbox(
        "Município", lista_municipios, index=None, placeholder="Selecione um município",
        disabled=not estado_sel,
    )

    if estado_sel and municipio_sel:
        with st.spinner("Filtrando prestadores..."):
            lista_prestadores = obter_prestadores(df_consulta, estado_sel, municipio_sel)
    else:
        lista_prestadores = []
    prestador_sel = st.selectbox(
        "Prestador", lista_prestadores, index=None, placeholder="Selecione um prestador",
        disabled=not municipio_sel,
    )

    if estado_sel and municipio_sel and prestador_sel:
        with st.spinner("Filtrando indicadores disponíveis..."):
            indicadores_snis, indicadores_snisa = obter_indicadores(
                df_snis, df_snisa_agua, df_snisa_esgoto, df_relacao_agua, df_relacao_esgoto,
                estado_sel, municipio_sel, prestador_sel,
            )
        lista_indicadores = sorted(set(indicadores_snis) | set(indicadores_snisa))
    else:
        indicadores_snis, indicadores_snisa = [], []
        lista_indicadores = []

    indicador_sel = st.selectbox(
        "Indicador", lista_indicadores, index=None, placeholder="Selecione um indicador",
        disabled=not prestador_sel,
    )

    obter_dados_clicado = st.button(
        "Obter dados", type="primary", width="stretch",
        disabled=not indicador_sel,
    )

if obter_dados_clicado:
    with st.spinner("Buscando e consolidando os dados do indicador selecionado..."):
        df_resultado, aviso_uniao = uniao_registros(
            df_snis, df_snisa_agua, df_snisa_esgoto, df_relacao_agua, df_relacao_esgoto,
            indicadores_snis, indicadores_snisa,
            estado_sel, municipio_sel, prestador_sel, indicador_sel,
        )
    st.session_state["df_resultado"] = df_resultado
    st.session_state["aviso_uniao"] = aviso_uniao
    st.session_state["indicador_atual"] = indicador_sel
    st.session_state["contexto_atual"] = (estado_sel, municipio_sel, prestador_sel)
    st.session_state["indicadores_snis_atual"] = indicadores_snis
    st.session_state["indicadores_snisa_atual"] = indicadores_snisa

if "df_resultado" in st.session_state:
    df_resultado = st.session_state["df_resultado"]
    indicador_atual = st.session_state["indicador_atual"]
    estado_ctx, municipio_ctx, prestador_ctx = st.session_state["contexto_atual"]
    aviso_uniao = st.session_state.get("aviso_uniao")

    if aviso_uniao:
        st.warning(f"⚠️ {aviso_uniao}")

    if df_resultado is None or df_resultado.empty:
        st.warning("Nenhum dado encontrado para essa combinação de filtros.")
    else:
        df_resultado = df_resultado.dropna(subset=[indicador_atual])

        st.subheader(f"{indicador_atual}")
        st.caption(f"{municipio_ctx} / {estado_ctx} — Prestador: {prestador_ctx}")

        metadados = obter_metadados_indicador(
            indicador_atual,
            st.session_state.get("indicadores_snis_atual", []),
            st.session_state.get("indicadores_snisa_atual", []),
            df_relacao_agua, df_relacao_esgoto,
        )

        with st.container(border=True):
            st.markdown("**ℹ️ Sobre o indicador**")
            if metadados and any(metadados.values()):
                col_grupo, col_palavra, col_unidade = st.columns(3)
                col_grupo.markdown(f"**Grupo**  \n{metadados['Grupo'] or '—'}")
                col_palavra.markdown(f"**Palavra-chave**  \n{metadados['Palavra-chave'] or '—'}")
                col_unidade.markdown(f"**Unidade**  \n{metadados['Unidade'] or '—'}")
                if metadados["Informação"]:
                    st.markdown(f"**Informações**  \n{metadados['Informação']}")
            else:
                st.caption(
                    "Metadados não encontrados para este indicador nas tabelas "
                    "`relacao_agua.csv` / `relacao_esgoto.csv`."
                )

        fig = px.line(
            df_resultado, x="Ano", y=indicador_atual, markers=True,
        )
        fig.update_layout(height=550, xaxis_title="Ano", yaxis_title=indicador_atual)
        st.plotly_chart(fig, width="stretch")

        st.subheader("Dados detalhados")
        colunas_tabela = ["Município", "Estado", "Ano", indicador_atual]
        colunas_tabela = [c for c in colunas_tabela if c in df_resultado.columns]
        st.dataframe(
            df_resultado[colunas_tabela].sort_values(by="Ano", ascending=False),
            width="stretch", hide_index=True,
        )
else:
    st.info("Selecione Estado, Município, Prestador e Indicador na barra lateral e clique em **Obter dados**.")