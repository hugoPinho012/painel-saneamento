# Painel de Indicadores de Saneamento (SNIS + SNISA)

Painel interativo construído em **Python + Streamlit** para consulta e visualização de séries históricas de indicadores de saneamento básico no Brasil, combinando dados do **SNIS** (Sistema Nacional de Informações sobre Saneamento) e do **SNISA** (Sistema Nacional de Informações de Saneamento).

🔗 **Acesse o painel publicado:** https://painel-saneamento-2026.streamlit.app/

## O que o painel faz

- Filtra indicadores por **Estado → Município → Prestador → Indicador**.
- Une automaticamente dados do SNIS e do SNISA quando existe um indicador equivalente entre as duas bases, construindo uma série histórica mais longa e contínua.
- Quando um indicador existe em apenas uma das duas bases (por exemplo, descontinuado no SNISA ou exclusivo dele), o painel exibe um aviso explicando a limitação em vez de simplesmente omitir o dado.
- Mostra metadados do indicador (grupo, palavra-chave, unidade de medida) quando disponíveis nas tabelas de relação.
- Exibe a série histórica em gráfico de linha (Plotly) e em tabela detalhada, ano a ano.
- Tolera variações de nomenclatura nos arquivos de origem (acentos, maiúsculas/minúsculas, espaços/underscores), avisando na interface quando uma coluna esperada não é encontrada.

## Por que SNIS + SNISA?

O SNIS é a base histórica consolidada do setor, mas com a migração para o SNISA, a tem metodologia e nomenclatura dos indicadores mudaram. Isso cria lacunas: alguns indicadores somem de um sistema e aparecem (com outro nome) no outro. Este painel faz esse "de-para" automaticamente, usando tabelas de relação entre os códigos das duas bases, para entregar uma visão histórica única por indicador sempre que possível.

## Estrutura do projeto

```
.
├── painel.py              # aplicação Streamlit
├── requirements.txt       # dependências Python
├── Data_v2/                # dados de entrada (não versionados — ver abaixo)
│   ├── SNISA_tratado_agua_AAAAMMDD.csv
│   ├── SNISA_tratado_esgoto_AAAAMMDD.csv
│   ├── snis_completo_AAAAMMDD.parquet
│   ├── relacao_agua_AAAAMMDD.csv
│   └── relacao_esgoto_AAAAMMDD.csv
└── README.md
```

> Os scritos de tratamento e consolidação dos arquivos (`Data_v2/`) não fazem parte deste repositório. Detalhes desse processo de serão publicados em um outro repositório.

## Como rodar localmente

**1. Clone o repositório e instale as dependências:**

```bash
git clone https://github.com/hugoPinho012/painel-saneamento
cd painel-saneamento
pip install -r requirements.txt
```

**2. Obtenha os dados.**

Coloque os cinco arquivos tratados dentro de uma pasta `Data_v2/` na raiz do projeto, seguindo o padrão de nome `*_AAAAMMDD` usado no código. Se os nomes dos seus arquivos tiverem uma data diferente, ajuste as constantes no topo de `painel.py`:

```python
DATA_DIR = "Data_v2"
DATA_SUFFIX = "20260927"  # ajuste para a data dos seus arquivos
```

> Note que `snis_completo` usa uma data própria, fixada diretamente no código (`snis_completo_20260928.parquet`) — se o nome do seu arquivo for diferente, essa linha também precisa ser ajustada manualmente.

**3. Rode o app:**

```bash
streamlit run painel.py
```

O painel abrirá em `http://localhost:8501`.

## Requisitos

- Python 3.10+
- pandas
- plotly
- streamlit

(ver `requirements.txt` para as versões exatas)

## Limitações conhecidas

- A correspondência entre indicadores do SNIS e do SNISA depende inteiramente das tabelas de relação (`relacao_agua` / `relacao_esgoto`). Indicadores novos de qualquer um dos dois sistemas que ainda não tenham sido mapeados nessas tabelas não serão unidos automaticamente.
- O nome do arquivo `snis_completo` tem a data fixada no código (ver seção acima), diferente dos demais arquivos, que usam a constante `DATA_SUFFIX`.
- O app não atualiza os dados automaticamente — atualizar para uma nova rodada do SNIS/SNISA exige substituir os arquivos em `Data_v2/` e ajustar as constantes de data.

## Contato

Dúvidas, sugestões ou achou um dado inconsistente? Abra uma *issue* neste repositório ou me chame no [LinkedIn] (linkedin.com/in/hugo-pinho-2a7769235).
