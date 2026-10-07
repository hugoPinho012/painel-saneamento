import re
import unicodedata

import pandas as pd
import plotly.express as px
import streamlit as st

# General configuration
# ---------------------------------------------------------------------------

DATA_DIR = "Data_v2"
DATA_SUFFIX = "20260927"

UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}

st.set_page_config(page_title="Painel de Saneamento (SNIS/SINISA)", layout="wide")


# Data loading (cached)
# ---------------------------------------------------------------------------

def _normalizar_nome(texto: str) -> str:
    """Strips accents, spaces, underscores and casing so column names can be compared."""
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-z0-9]+", "", texto)
    return texto


def _padronizar_colunas(df: pd.DataFrame, nomes_esperados: list, nome_arquivo: str):
    """Renames the df's columns to the expected names, tolerating differences in
    accent/case/space/underscore in the original header. Returns (df, missing)."""
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
    df_sinisa_agua = pd.read_csv(f"{DATA_DIR}/SINISA_tratado_agua_{DATA_SUFFIX}.csv", low_memory=False)
    df_sinisa_esgoto = pd.read_csv(f"{DATA_DIR}/SINISA_tratado_esgoto_{DATA_SUFFIX}.csv", low_memory=False)
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

    df_sinisa_agua, faltando = _padronizar_colunas(
        df_sinisa_agua, ["Município", "UF", "CAD0006"], "SINISA_tratado_agua"
    )
    if faltando:
        avisos.append((faltando, list(df_sinisa_agua.columns), "SINISA_tratado_agua"))

    df_sinisa_esgoto, faltando = _padronizar_colunas(
        df_sinisa_esgoto, ["Município", "UF", "CAD0006"], "SINISA_tratado_esgoto"
    )
    if faltando:
        avisos.append((faltando, list(df_sinisa_esgoto.columns), "SINISA_tratado_esgoto"))

    df_snis, faltando = _padronizar_colunas(
        df_snis,
        ["Município", "Estado", "Sigla do Prestador", "Natureza jurídica"],
        "snis_completo",
    )
    if faltando:
        avisos.append((faltando, list(df_snis.columns), "snis_completo"))

    return df_snis, df_sinisa_agua, df_sinisa_esgoto, df_relacao_agua, df_relacao_esgoto, avisos


@st.cache_data(show_spinner=False)
def criar_df_consulta(_df_snis, _df_sinisa_agua, _df_sinisa_esgoto):
    df_snis, df_sinisa_agua, df_sinisa_esgoto = _df_snis, _df_sinisa_agua, _df_sinisa_esgoto
    df_snis_consulta = df_snis[["Município", "Estado", "Sigla do Prestador"]].copy()
    df_sinisa_agua_consulta = df_sinisa_agua[["Município", "UF", "CAD0006"]].copy()
    df_sinisa_esgoto_consulta = df_sinisa_esgoto[["Município", "UF", "CAD0006"]].copy()

    df_sinisa_agua_consulta["Estado"] = df_sinisa_agua_consulta["UF"]
    df_sinisa_esgoto_consulta["Estado"] = df_sinisa_esgoto_consulta["UF"]

    df_sinisa_agua_consulta["Sigla do Prestador"] = df_sinisa_agua_consulta["CAD0006"]
    df_sinisa_esgoto_consulta["Sigla do Prestador"] = df_sinisa_esgoto_consulta["CAD0006"]

    df_sinisa_agua_consulta = df_sinisa_agua_consulta.drop(columns=["CAD0006", "UF"])
    df_sinisa_esgoto_consulta = df_sinisa_esgoto_consulta.drop(columns=["CAD0006", "UF"])

    df_consulta = pd.concat(
        [df_snis_consulta, df_sinisa_agua_consulta, df_sinisa_esgoto_consulta]
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
def obter_municipios(_df_snis, _df_sinisa_agua, _df_sinisa_esgoto, estado):
    df_snis, df_sinisa_agua, df_sinisa_esgoto = _df_snis, _df_sinisa_agua, _df_sinisa_esgoto
    municipios_snis = df_snis[["Município", "Estado"]].drop_duplicates()

    municipios_snis_agua = df_sinisa_agua[["Município", "UF"]].drop_duplicates().copy()
    municipios_snis_esgoto = df_sinisa_esgoto[["Município", "UF"]].drop_duplicates().copy()

    municipios_snis_agua["Estado"] = municipios_snis_agua["UF"]
    municipios_snis_esgoto["Estado"] = municipios_snis_esgoto["UF"]

    municipios_snis_agua = municipios_snis_agua.drop(columns=["UF"])
    municipios_snis_esgoto = municipios_snis_esgoto.drop(columns=["UF"])

    # Combines municipalities present in any of the three source tables, since
    # not every municipality appears in all of them.
    municipios = pd.concat([municipios_snis, municipios_snis_agua, municipios_snis_esgoto])
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
def obter_indicadores(_df_snis, _df_sinisa_agua, _df_sinisa_esgoto,
                       _df_relacao_agua, _df_relacao_esgoto,
                       estado, cidade, prestador):
    df_snis, df_sinisa_agua, df_sinisa_esgoto = _df_snis, _df_sinisa_agua, _df_sinisa_esgoto
    df_relacao_agua, df_relacao_esgoto = _df_relacao_agua, _df_relacao_esgoto

    def obter_indicadores_sinisa(df_sinisa, eh_agua, estado, cidade, prestador):
        df_sinisa_temp = df_sinisa.query(
            "UF == @estado & `Município` == @cidade & `CAD0006` == @prestador"
        )
        if df_sinisa_temp.empty:
            return []

        colunas_para_remover = [
            c for c in ["Ano", "Quantidade_Prestadores", "CAD0006_Detalhe",
                        "Multiplos_Prestadores", "chave"]
            if c in df_sinisa_temp.columns
        ]
        df_sinisa_temp = df_sinisa_temp.drop(columns=colunas_para_remover)

        idx = df_sinisa_temp.columns.get_loc("CAD0006")
        indicadores_sinisa_cols = df_sinisa_temp.columns[idx + 1:].tolist()

        view_codes = []
        for indicador in indicadores_sinisa_cols:
            try:
                df_relacao = df_relacao_agua if eh_agua else df_relacao_esgoto
                view_code = df_relacao.query("`CÓDIGO` == @indicador")["View Codigo"].values[0]
                view_codes.append(view_code)
            except IndexError:
                # SINISA column with no matching entry in the relation table —
                # indicator skipped because it has no mapped View Codigo.
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
    indicadores_sinisa_agua = obter_indicadores_sinisa(df_sinisa_agua, True, estado, cidade, prestador)
    indicadores_sinisa_esgoto = obter_indicadores_sinisa(df_sinisa_esgoto, False, estado, cidade, prestador)

    indicadores_sinisa = list(set(indicadores_sinisa_esgoto + indicadores_sinisa_agua))

    return indicadores_snis, indicadores_sinisa


# Queries
# ---------------------------------------------------------------------------

def consulta_snis(df_snis, df_relacao_agua, df_relacao_esgoto,
                   indicadores_snis, indicadores_sinisa,
                   estado, cidade, prestador, indicador):

    if indicador in indicadores_snis:
        df_snis_temp = df_snis.query(
            "Estado == @estado & `Município` == @cidade & `Sigla do Prestador` == @prestador"
        )
        try:
            # Column name used in the more recent SNIS editions.
            df_snis_temp = df_snis_temp[
                ["Estado", "Município", "Sigla do Prestador", "Ano de Referência", indicador]
            ]
        except KeyError:
            # Older editions only have "Ano" instead of "Ano de Referência".
            df_snis_temp = df_snis_temp[
                ["Estado", "Município", "Sigla do Prestador", "Ano", indicador]
            ]
        return df_snis_temp

    if indicador in indicadores_sinisa:
        try:
            # Try the water relation table first...
            indicador_equivalente = df_relacao_agua[
                df_relacao_agua["View Codigo"] == indicador
            ]["INDICADOR EQUIVALENTE"].values[0]
        except IndexError:
            # ...and fall back to the sewage one if not found in water.
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
            # Column name used in the more recent SNIS editions.
            df_snis_temp = df_snis_temp[
                ["Estado", "Município", "Sigla do Prestador", "Ano de Referência",
                 indicador_equivalente_full_name]
            ]
        except KeyError:
            # Older editions only have "Ano" instead of "Ano de Referência".
            df_snis_temp = df_snis_temp[
                ["Estado", "Município", "Sigla do Prestador", "Ano",
                 indicador_equivalente_full_name]
            ]
        return df_snis_temp

    return pd.DataFrame()


def consulta_sinisa(df_sinisa_agua, df_sinisa_esgoto, df_relacao_agua, df_relacao_esgoto,
                    indicadores_snis, indicadores_sinisa,
                    estado, cidade, prestador, indicador):

    if indicador in indicadores_sinisa:
        codigo_sinisa = indicador.split(" - ")[0]

        if codigo_sinisa in df_sinisa_esgoto.columns.tolist():
            df_sinisa_temp = df_sinisa_esgoto.query(
                "UF == @estado & `Município` == @cidade & `CAD0006` == @prestador"
            )
            return df_sinisa_temp[["UF", "Município", "CAD0006", "Ano", codigo_sinisa]]
        elif codigo_sinisa in df_sinisa_agua.columns.tolist():
            df_sinisa_temp = df_sinisa_agua.query(
                "UF == @estado & `Município` == @cidade & `CAD0006` == @prestador"
            )
            return df_sinisa_temp[["UF", "Município", "CAD0006", "Ano", codigo_sinisa]]
        else:
            return pd.DataFrame()

    if indicador in indicadores_snis:
        codigo_indicador_snis = indicador.split(" - ")[0]

        serie_agua = df_relacao_agua.loc[
            df_relacao_agua["INDICADOR EQUIVALENTE"] == codigo_indicador_snis, "CÓDIGO"
        ]
        serie_esgoto = df_relacao_esgoto.loc[
            df_relacao_esgoto["INDICADOR EQUIVALENTE"] == codigo_indicador_snis, "CÓDIGO"
        ]

        for serie, df_sinisa_base in ((serie_agua, df_sinisa_agua), (serie_esgoto, df_sinisa_esgoto)):
            if not serie.empty:
                codigo_equivalente = serie.values[0]
                if codigo_equivalente in df_sinisa_base.columns:
                    df_sinisa_temp = df_sinisa_base.query(
                        "UF == @estado & `Município` == @cidade & `CAD0006` == @prestador"
                    )
                    return df_sinisa_temp[["UF", "Município", "CAD0006", "Ano", codigo_equivalente]]

        # No SINISA equivalent exists (or is no longer available) for this
        # SNIS indicator. Returns empty instead of raising IndexError.
        return pd.DataFrame()

    return pd.DataFrame()


def uniao_registros(df_snis, df_sinisa_agua, df_sinisa_esgoto, df_relacao_agua, df_relacao_esgoto,
                     indicadores_snis, indicadores_sinisa,
                     estado, cidade, prestador, indicador):
    """Returns (df_final, warning).

    `warning` is None when SNIS and SINISA were merged normally, or a message
    explaining why only one of the two sources is available for this
    indicator (e.g. a SNIS indicator with no SINISA equivalent)."""

    df_sinisa_res = consulta_sinisa(
        df_sinisa_agua, df_sinisa_esgoto, df_relacao_agua, df_relacao_esgoto,
        indicadores_snis, indicadores_sinisa, estado, cidade, prestador, indicador,
    )
    df_snis_res = consulta_snis(
        df_snis, df_relacao_agua, df_relacao_esgoto,
        indicadores_snis, indicadores_sinisa, estado, cidade, prestador, indicador,
    )

    if df_sinisa_res.empty or df_snis_res.empty:
        # No matching pair in one of the two sources: return whichever exists.
        if not df_snis_res.empty and df_sinisa_res.empty:
            resultado = df_snis_res
            aviso = "Indicador descontinuado no SINISA. Dados disponíveis até 2022 (apenas SNIS)."
        elif not df_sinisa_res.empty and df_snis_res.empty:
            resultado = df_sinisa_res
            aviso = "Indicador exclusivo do SINISA. Não há série histórica equivalente no SNIS."
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
                # Ensures the value becomes numeric whether it came only from
                # SNIS (which uses a decimal comma) or only from SINISA.
                resultado[indicador] = (
                    resultado[indicador].astype(str).str.replace(",", ".", regex=False)
                )
                resultado[indicador] = pd.to_numeric(resultado[indicador], errors="coerce")

        return resultado, aviso

    df_sinisa_res = df_sinisa_res.rename(columns={"UF": "Estado", "CAD0006": "Sigla do Prestador"})
    df_snis_res = df_snis_res.rename(columns={"Ano de Referência": "Ano"})

    if indicador in indicadores_snis:
        codigo_indicador_snis = indicador.split(" - ")[0]

        serie_agua = df_relacao_agua.loc[
            df_relacao_agua["INDICADOR EQUIVALENTE"] == codigo_indicador_snis, "CÓDIGO"
        ]
        serie_esgoto = df_relacao_esgoto.loc[
            df_relacao_esgoto["INDICADOR EQUIVALENTE"] == codigo_indicador_snis, "CÓDIGO"
        ]

        if not serie_agua.empty:
            indicador_sinisa_equivalente = serie_agua.values[0]
        elif not serie_esgoto.empty:
            indicador_sinisa_equivalente = serie_esgoto.values[0]
        else:
            # Extra safety net: shouldn't be reached since df_sinisa_res wasn't
            # empty, but avoids an IndexError in any unexpected scenario.
            return df_snis_res, "Indicador descontinuado no SINISA. Dados disponíveis até 2022 (apenas SNIS)."

        df_sinisa_res = df_sinisa_res.rename(columns={indicador_sinisa_equivalente: indicador})
        df_sinisa_res[indicador] = pd.to_numeric(df_sinisa_res[indicador], errors="coerce")

        df_snis_res[indicador] = (
            df_snis_res[indicador].astype(str).str.replace(",", ".", regex=False)
        )
        df_snis_res[indicador] = pd.to_numeric(df_snis_res[indicador], errors="coerce")

        df_final = pd.concat([df_snis_res, df_sinisa_res])
        df_final = df_final.sort_values(by="Ano", ascending=True)
        return df_final, None

    else:
        codigo_sinisa = indicador.split(" - ")[0]

        serie_esgoto_eq = df_relacao_esgoto.loc[
            df_relacao_esgoto["CÓDIGO"] == codigo_sinisa, "INDICADOR EQUIVALENTE"
        ]
        serie_agua_eq = df_relacao_agua.loc[
            df_relacao_agua["CÓDIGO"] == codigo_sinisa, "INDICADOR EQUIVALENTE"
        ]

        if not serie_esgoto_eq.empty:
            codigo_snis_equivalente = serie_esgoto_eq.values[0]
        elif not serie_agua_eq.empty:
            codigo_snis_equivalente = serie_agua_eq.values[0]
        else:
            df_sinisa_res[codigo_sinisa] = pd.to_numeric(df_sinisa_res[codigo_sinisa], errors="coerce")
            df_sinisa_res = df_sinisa_res.rename(columns={codigo_sinisa: indicador})
            aviso = "Indicador exclusivo do SINISA. Não há série histórica equivalente no SNIS."
            return df_sinisa_res.sort_values(by="Ano", ascending=True), aviso

        indicador_snis_equivalente = None
        for cod in indicadores_snis:
            if codigo_snis_equivalente in cod:
                indicador_snis_equivalente = cod
                break
        if indicador_snis_equivalente is None:
            df_sinisa_res[codigo_sinisa] = pd.to_numeric(df_sinisa_res[codigo_sinisa], errors="coerce")
            df_sinisa_res = df_sinisa_res.rename(columns={codigo_sinisa: indicador})
            aviso = "Indicador exclusivo do SINISA. Não há série histórica equivalente no SNIS."
            return df_sinisa_res.sort_values(by="Ano", ascending=True), aviso

        df_sinisa_res[codigo_sinisa] = pd.to_numeric(df_sinisa_res[codigo_sinisa], errors="coerce")

        df_snis_res[indicador_snis_equivalente] = (
            df_snis_res[indicador_snis_equivalente].astype(str).str.replace(",", ".", regex=False)
        )
        df_snis_res[indicador_snis_equivalente] = pd.to_numeric(
            df_snis_res[indicador_snis_equivalente], errors="coerce"
        )

        df_snis_res = df_snis_res.rename(columns={indicador_snis_equivalente: codigo_sinisa})

        df_final = pd.concat([df_snis_res, df_sinisa_res])
        # Standardizes the indicator column name to the full label chosen by
        # the user, since the column arrived with the short SINISA code, which
        # doesn't match the name used in the interface.
        df_final = df_final.rename(columns={codigo_sinisa: indicador})
        df_final = df_final.sort_values(by="Ano", ascending=True)
        return df_final, None


# Streamlit interface
# ---------------------------------------------------------------------------

def _buscar_valor_normalizado(linha: pd.Series, candidatos: list):
    """Looks through a row (Series) for the first non-empty value whose
    normalized column name matches one of the candidates (tolerant to
    accent, case, space and underscore)."""
    normalizados = {_normalizar_nome(col): col for col in linha.index}
    for candidato in candidatos:
        chave = _normalizar_nome(candidato)
        if chave in normalizados:
            valor = linha[normalizados[chave]]
            if pd.notna(valor) and str(valor).strip() != "":
                return str(valor).strip()
    return None


def obter_metadados_indicador(indicador, indicadores_snis, indicadores_sinisa,
                               df_relacao_agua, df_relacao_esgoto):
    """Looks up metadata (group, keyword, unit, info) for the indicator
    in the water/sewage relation tables."""
    linha = None

    if indicador in indicadores_sinisa:
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


st.title("Painel de Indicadores de Saneamento (SNIS + SINISA)")

try:
    (df_snis, df_sinisa_agua, df_sinisa_esgoto, df_relacao_agua,
     df_relacao_esgoto, avisos_colunas) = carregar_dados()
except FileNotFoundError as e:
    st.error(
        "Não foi possível encontrar os arquivos de dados. Verifique se a pasta "
        f"'{DATA_DIR}' está no mesmo diretório do app e contém os CSVs esperados.\n\n"
        f"Detalhe: {e}"
    )
    st.stop()

if avisos_colunas:
    with st.expander("Colunas não encontradas nos arquivos de origem", expanded=True):
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

df_consulta = criar_df_consulta(df_snis, df_sinisa_agua, df_sinisa_esgoto)

with st.sidebar:
    st.header("Filtros")

    lista_estados = obter_estados(df_consulta)
    estado_sel = st.selectbox("Estado", lista_estados, index=None, placeholder="Selecione um estado")

    if estado_sel:
        with st.spinner("Filtrando municípios..."):
            lista_municipios = obter_municipios(df_snis, df_sinisa_agua, df_sinisa_esgoto, estado_sel)
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
            indicadores_snis, indicadores_sinisa = obter_indicadores(
                df_snis, df_sinisa_agua, df_sinisa_esgoto, df_relacao_agua, df_relacao_esgoto,
                estado_sel, municipio_sel, prestador_sel,
            )
        lista_indicadores = sorted(set(indicadores_snis) | set(indicadores_sinisa))
    else:
        indicadores_snis, indicadores_sinisa = [], []
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
            df_snis, df_sinisa_agua, df_sinisa_esgoto, df_relacao_agua, df_relacao_esgoto,
            indicadores_snis, indicadores_sinisa,
            estado_sel, municipio_sel, prestador_sel, indicador_sel,
        )
    st.session_state["df_resultado"] = df_resultado
    st.session_state["aviso_uniao"] = aviso_uniao
    st.session_state["indicador_atual"] = indicador_sel
    st.session_state["contexto_atual"] = (estado_sel, municipio_sel, prestador_sel)
    st.session_state["indicadores_snis_atual"] = indicadores_snis
    st.session_state["indicadores_sinisa_atual"] = indicadores_sinisa

if "df_resultado" in st.session_state:
    df_resultado = st.session_state["df_resultado"]
    indicador_atual = st.session_state["indicador_atual"]
    estado_ctx, municipio_ctx, prestador_ctx = st.session_state["contexto_atual"]
    aviso_uniao = st.session_state.get("aviso_uniao")

    if aviso_uniao:
        st.warning(f"{aviso_uniao}")

    if df_resultado is None or df_resultado.empty:
        st.warning("Nenhum dado encontrado para essa combinação de filtros.")
    else:
        df_resultado = df_resultado.dropna(subset=[indicador_atual])

        st.subheader(f"{indicador_atual}")
        st.caption(f"{municipio_ctx} / {estado_ctx} — Prestador: {prestador_ctx}")

        metadados = obter_metadados_indicador(
            indicador_atual,
            st.session_state.get("indicadores_snis_atual", []),
            st.session_state.get("indicadores_sinisa_atual", []),
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