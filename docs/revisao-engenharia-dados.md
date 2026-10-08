# Revisão de Engenharia de Dados — 01-s3-data-lake

**Data:** 2026-10-08
**Escopo:** `01-s3-data-lake/` — `src/lake/` (generator, validate, lake, pipeline, run), `src/de_common/`, `tests/` (5 arquivos), `iam/s3-data-engineering.json`, `.github/workflows/ci.yml`, `scripts/run_local.sh`, README, `.env.example`. Análise estática; nada foi executado contra AWS ou LocalStack.
**Maturidade assumida:** Estágio 1 — portfólio/estudo executável local ("primeiro valor com poucas peças"); o próprio README do portfólio marca este projeto como lab, não produção.

## Veredito

É um lab de estágio 1 bem construído: medallion raw→bronze→silver→gold funcional, idempotente por construção, com validação fail-fast, CI com lint+format+mypy strict+gitleaks e zero over-engineering (pandas + S3, sem Spark/Kafka). Para o propósito declarado, está pronto. Mas há **um número potencialmente errado chegando ao consumidor** (o gold soma reembolsos como receita), o teste que deveria pegá-lo **espelha o bug e nem roda no CI**, e há uma **contradição de design** entre validar e dedupar. Esses três itens são o que mais importa agora.

## Mapa do ciclo de vida

| Etapa do ciclo | Onde está no repo | Tecnologia | Observação |
|---|---|---|---|
| Geração (fontes) | `src/lake/generator.py` | Gerador sintético determinístico por seed | Fonte é o próprio pipeline; sem contrato/schema evolution real; `ts` sem timezone |
| Armazenamento | `src/lake/lake.py`, layout `camada/date=.../` | S3 (LocalStack local / AWS real) | 4 camadas, raw preservado; tudo em CSV; sem lifecycle/versionamento como código |
| Ingestão | `pipeline.py:seed_raw`, `raw_to_bronze` | Batch por data lógica (`--date`), pandas via S3 | Reescrita determinística (idempotente); tudo-ou-nada, sem retry/quarentena |
| Transformação | `validate.py`, `bronze_to_silver`, `silver_to_gold` | pandas | Dedupe + agregação diária por país; sem SQL |
| Disponibilização | `gold/date=.../daily-revenue.csv` + metadata S3 | CSV no S3, IAM por prefixo | Sem catálogo, dicionário de KPI, frescor visível ou BI conectado |

## Scorecard

| Dimensão | Nota (0–3) | Esperado no estágio | Resumo em uma linha |
|---|---|---|---|
| Geração | 2 | 1–2 | Determinística e reproduzível; `ts` naive é o único senão |
| Armazenamento | 2 | 1–2 | Camadas + Hive + raw preservado; CSV-only e sem lifecycle codificado |
| Ingestão | 2 | 1–2 | Idempotente e parametrizada por data; sem retry/quarentena |
| Transformação | 1 | 2 | Funciona, mas gold ignora `status` (receita errada) e dedupe é inalcançável |
| Disponibilização | 1 | 1 | Gold existe com metadata; sem contrato, frescor ou dicionário |
| Segurança/privacidade | 2 | 2 | Sem segredos, IAM escopado, gitleaks; `DeleteObject` amplo |
| Gerenciamento | 1 | 1 | Metadata no objeto como linhagem mínima; sem catálogo (ok aqui) |
| DataOps | 2 | 1–2 | CI forte; sem monitoramento de produção (ok aqui) |
| Arquitetura | 2 | 1–2 | Bem dimensionada, decisões documentadas; sem IaC/RTO |
| Orquestração | 1 | 1 | CLI + shell, sem agendador (correto adiar; ver projeto 11) |
| Eng. de software | 2 | 2 | Modular, tipado strict, testado; sem lockfile, sem histórico git |

## Pontos fortes verificados

- **Idempotência real, não prometida:** reescrita determinística em todas as camadas (`pipeline.py:1-5`, `:42`, `:56`, `:76`) + teste de rerun idêntico (`test_pipeline_e2e.py:50-53`).
- **Validação coleta todos os erros antes de falhar** (`validate.py:53-54`) — debug em um ciclo.
- **CI acima do esperado no estágio 1:** ruff lint + format + mypy strict + pytest + gitleaks (`ci.yml:20-33`).
- **Higiene de segredos:** `.env` gitignored, `.env.example` só com `test/test`, nada no código (`config.py`, `aws.py:20-27`).
- **IAM least-privilege por prefixo** `data-engineer-lab-*` (`iam/s3-data-engineering.json:11-25`).
- **Sem over-engineering:** pandas + S3 para 2k linhas/demo; Parquet, Glue e streaming explicitamente adiados com dono (projetos 03/05).

## Achados

### GOLD-01 Gold soma reembolsos como receita — Alta · Esforço P
- **Local:** `src/lake/pipeline.py:66-75` (agregação) + `src/lake/validate.py:12` (`refunded` é status válido)
- **Status:** verificado
- **Evidência:** `silver_to_gold` agrupa por `(day, country)` somando `amount` sem olhar `status`. O gerador emite ~25% de `refunded` (`generator.py:45`), todos válidos na bronze, todos somados como receita positiva no gold. "Receita" inclui reembolsos — número errado silencioso no artefato que alimenta BI/ML.
- **Por que importa:** erro silencioso que chega ao consumidor (o livro prioriza exatamente esse tipo: pipeline que roda e entrega número errado).
- **Como corrigir:** decidir a regra (ex.: só `approved`, ou colunas `gross_revenue`/`refunds`/`net_revenue`) e adicionar teste com valores fixos contendo `refunded`.
- **Correção aplicada (2026-10-08):** `silver_to_gold` agora separa `revenue` (só `approved`), `refunds`/`refunded_amount` e `net_revenue = revenue - refunded_amount`; `pipeline.VERSION` 1 → 2; trava em `tests/test_gold_revenue.py`.

### E2E-01 Teste de reconciliação não pegaria o GOLD-01 e nem roda no CI — Alta · Esforço P
- **Local:** `tests/test_pipeline_e2e.py:37-49` + `.github/workflows/ci.yml:29-30`
- **Status:** verificado
- **Evidência:** o `expected` era recomputado com o *mesmo* `groupby` da implementação — o teste espelhava o bug em vez de especificar o correto. Além disso, o teste pula sem LocalStack (`:24`) e o CI não sobe LocalStack, então no CI ele é sempre *skip* silencioso: a pipeline e2e nunca é verificada no gate.
- **Por que importa:** transformações centrais ficam efetivamente sem teste no CI (critério de severidade Alta do livro).
- **Como corrigir:** (1) teste do gold com fixture de valores conhecidos e asserção literal (ex.: 2 approved + 1 refunded → receita X); (2) rodar o e2e em moto no CI ou subir LocalStack como serviço no workflow.
- **Correção aplicada (2026-10-08):** novo `tests/test_gold_revenue.py` (moto, sem LocalStack, roda no CI) com silver artesanal e esperado literal; `test_pipeline_e2e.py` atualizado para a nova regra do gold e com comentário marcando o teste literal como especificação.

### SILVER-01 Dedupe da silver é inalcançável: validate rejeita dupes antes — Média · Esforço P
- **Local:** `src/lake/validate.py:32-34` vs `src/lake/pipeline.py:52-55`
- **Status:** verificado
- **Evidência:** `validate_transactions` falha o lote inteiro se houver qualquer `transaction_id` duplicado — inclusive entre múltiplos arquivos raw concatenados (`pipeline.py:40-41`). Logo a bronze nunca contém dupes e o `drop_duplicates` da silver nunca remove nada. As duas etapas contradizem-se: ou duplicata é erro fatal (e o dedupe é código morto) ou é esperada (e a validação não deveria derrubar o lote).
- **Por que importa:** rigidez + lógica morta que sugere uma garantia que não existe; com fonte real, 1 duplicata derruba o dia inteiro.
- **Como corrigir:** decidir e documentar: (a) manter fail-fast e remover o dedupe, ou (b) mover dupes para quarentena (`bronze/quarantine/date=.../`) e deixar a silver dedupar. Para estágio 1, (a) + documentar é suficiente.
- **Correção aplicada (2026-10-08):** opção (a) — `bronze_to_silver` virou pass-through determinístico (sem `drop_duplicates`), metadata `dedupe: enforced-in-bronze-validation`; contrato travado em `tests/test_silver_contract.py` (dupe entre 2 arquivos reprova o lote; silver byte-idêntica à bronze). Quarentena segue adiada para o estágio 2.

### RETRY-01 `is_retryable` existe mas nunca é usado; S3 sem retry/timeout — Média · Esforço P
- **Local:** `src/de_common/aws.py:34-46` (definido, zero chamadas) + `src/lake/lake.py:45-48,66-69` (chamadas diretas)
- **Status:** verificado
- **Evidência:** helper de classificação de erro transitório implementado e testado por ninguém/chamado por ninguém; `put/get/list` vão crus. Um throttle ou timeout derruba o run sem retentativa.
- **Por que importa:** ingestão sem retry nem alerta é o caso clássico de "fluxo sem resiliência" (Alta seria se alimentasse decisão em produção; aqui é lab → Média).
- **Como corrigir:** `boto3 Config(retries={'max_attempts': 5})` no `client()` ou decorar com backoff usando o próprio `is_retryable`; logar tentativa.

### TIME-01 `ts` sem timezone; `day` derivado sem UTC — Média · Esforço P
- **Local:** `src/lake/generator.py:44` (`f"{date}T{HH:MM}:00"`, naive) + `src/lake/pipeline.py:68` (`pd.to_datetime(df["ts"])`)
- **Status:** verificado (benigno hoje porque gerador e consumidor usam a mesma convenção implícita)
- **Evidência:** logs usam `datetime.now(UTC)` (`pipeline.py:97`, `logging.py:15`), mas o dado usa timestamp naive. Com fonte real em outro fuso, a agregação por `day` desloca receita de dia silenciosamente. É o "fuso implícito" da lista de sinais de alerta.
- **Por que importa:** quebra silenciosa de grão diário na primeira fonte real.
- **Como corrigir:** gerar `ts` com offset (`+00:00` ou `America/Sao_Paulo` explícito) e `pd.to_datetime(..., utc=True)` no gold; documentar "todo ts é UTC".

### MONEY-01 Dinheiro somado em float — Média · Esforço P
- **Local:** `src/lake/pipeline.py:70-72` (`.agg(revenue=("amount","sum")).round(2)`)
- **Status:** verificado
- **Evidência:** `amount` viaja como float do pandas; a soma acumula erro binário e o `round(2)` só mascara na apresentação. Em milhares de linhas o centavo pode divergir.
- **Por que importa:** dinheiro em float é o tipo errado para o domínio; barato de corrigir agora.
- **Como corrigir:** somar em centavos inteiros (ou `Decimal`) e converter só na borda; teste com valores que expõem o erro binário (ex.: 0.1 + 0.2).

### SCHEMA-01 Validação checa antes de normalizar e permite colunas extras — Baixa · Esforço P
- **Local:** `src/lake/validate.py:18-28,42-44,56-57`
- **Status:** verificado
- **Evidência:** (1) `country`/`currency` são comparados contra listas conhecidas *antes* do `.str.upper()` (`:56`) — um `"br"` legítimo seria rejeitado em vez de normalizado. (2) colunas extras além de `COLUMNS` passam silenciosamente (só `missing` é checado) — schema drift invisível.
- **Por que importa:** rigidez onde deveria normalizar, permissividade onde deveria alertar.
- **Como corrigir:** normalizar (strip/upper) antes de validar; rejeitar ou logar colunas inesperadas.

### DEPS-01 Dependências sem pin/lockfile — Baixa · Esforço P
- **Local:** `requirements.txt:1-7` (`boto3>=1.34`, `pandas>=2.0`, sem lock)
- **Status:** verificado
- **Evidência:** ranges abertos → builds não reproduzíveis (o `pip install` de hoje pode não ser o de amanhã).
- **Como corrigir:** `pip freeze`/`pip-compile` para `requirements.lock` usado no CI; manter o `.txt` legível como está.

### OBS-01 Sem `_SUCCESS`/manifesto nem frescor visível ao consumidor — Baixa · Esforço M
- **Local:** ausente no repositório (inferido); metadata `rows/sources` existe por objeto (`pipeline.py:43-47`)
- **Status:** inferido
- **Evidência:** consumidor precisa listar prefixos e ler metadata para saber se a partição está completa e quando chegou; sem manifesto por partição, sem métricas/alarmas (README cita CloudWatch Logs, mas não há métrica, alarme ou runbook no repo).
- **Por que importa:** dado sem sinal de frescor/completude erode confiança; no estágio 1, um `_SUCCESS` + `manifest.json` por data resolve 80%.
- **Como corrigir:** escrever `_SUCCESS` + `manifest.json` (rows por camada, `pipeline-version`, `ingested_at`) ao fim do `run()`; adiar métricas/alarmas para o projeto 12.

### LIFECYCLE-01 Retenção/versionamento citados mas não codificados — Info · Esforço M
- **Local:** `README.md:64-66` ("lifecycle para IA/Glacier", "`delete_prefix` manual")
- **Status:** verificado (menção sem código correspondente)
- **Evidência:** sem policy de lifecycle, sem versionamento de bucket, sem IaC no repo. Para lab com dados sintéticos, risco baixo.
- **Como corrigir (quando virar produção):** versionamento + regra de lifecycle + `Block Public Access` como código; por ora, deliberadamente adiado.

## Roadmap

1. **Agora** (horas, ordem sugerida): GOLD-01 → E2E-01 (teste com valores fixos que trava a regra de `refunded`) → SILVER-01 (decidir fail-fast vs quarentena) → TIME-01 + MONEY-01 + SCHEMA-01 (mesmo PR de robustez da borda) → RETRY-01 → DEPS-01.
2. **Em seguida** (dias, rumo ao estágio 2): OBS-01 (`_SUCCESS` + manifesto), quarentena/dead-letter real, lifecycle como código, agendador (projeto 11/Step Functions) com retry/SLA, dicionário do gold (`revenue` = ?).
3. **Deliberadamente adiado** (over-engineering neste estágio): Glue Catalog, Parquet (dono: projeto 03), streaming/Kafka (dono: 05), Spark/EMR, data mesh/catálogo corporativo — o volume (2k linhas/demo) e o estágio não justificam.

## O que esta análise não cobriu

Produção e volumes reais, custos efetivos, permissões reais na conta AWS, qualidade dos dados reais (a fonte é sintética), e o que vive fora do repositório (console AWS, dashboards, outros 14 projetos — vistos só pelo README do portfólio). Também não executei a pipeline contra LocalStack/AWS (sem `.venv`/LocalStack nesta máquina na hora da análise; o teste de fumaça do `validate` passou, o suite completo rodou no venv do autor, não aqui).

## Perguntas em aberto

1. `revenue` deve incluir `refunded` (bruta) ou só `approved` (líquida)? — **Respondida na correção:** `revenue` = só `approved`; `refunded_amount` separado; `net_revenue = revenue - refunded_amount`. Se preferir outra semântica, o teste literal documenta onde trocar.
2. Quem consome o gold e com que SLA de frescor? — define se OBS-01 vira prioridade.
3. Há conta AWS real como alvo, ou o deploy segue como exercício? — define se IAM/LIFECYCLE-01 endurecem.
4. Frequência pretendida (diária?) e política de backfill — confirma que `--date` basta como orquestração por ora.
