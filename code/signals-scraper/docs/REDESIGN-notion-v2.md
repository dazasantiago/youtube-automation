# Plan de reconstrucción v2 — Pipeline → Notion

> **Audiencia:** una sesión de Claude Code (Sonnet) que ejecutará este plan fase por fase.
> **Regla de oro:** este documento es la fuente de verdad. **No queda nada a tu criterio.** Si algo parece ambiguo, vuelve a leer la sección correspondiente. Si encuentras una contradicción real con el código, **detente y reporta** en la descripción del PR — no improvises.
> **Invariante sagrada (sigue vigente):** el pipeline de Python **nunca llama a un LLM** (ni Anthropic, ni OpenAI, ni embeddings remotos). La API de Notion **no es un LLM** y por tanto su uso es válido. Los embeddings siguen siendo locales (`sentence-transformers`).

---

## 0. Resumen del cambio (qué y por qué)

El pipeline actual construye una base SQLite, encola trabajo para dos *Claude Routines* (que etiquetan, minan comentarios y generan resúmenes), y envía alertas por Telegram. **Eso se elimina.**

El pipeline v2 se reduce a: **scrapear → clusterizar → etiquetar (heurística, sin LLM) → scorear → empujar los mejores temas a una base de datos de Notion.** Notion pasa a ser la superficie de decisión: el dueño ve ideas rankeadas con scores, fuentes, videos y evolución temporal, y decide manualmente qué grabar. La inteligencia editorial y el guionaje serán una skill manual de Claude aparte (fuera del alcance de este plan).

### Qué se ELIMINA
- Telegram (módulo `alerts.py`, alertas hot-topic, notificación de fallo en el workflow).
- Las dos Claude Routines y sus prompts (`prompts/daily_routine.md`, `prompts/weekly_routine.md`).
- La cola bidireccional (`data/queue/`, módulo `pipeline/queue.py`).
- Comment mining (`needs_mining`, `_fetch_comments_blob`, `ingest_mining_done`).
- Resúmenes y digests (`data/summaries/`, `data/digests/`).
- El eje **Fit** del scoring (dependía del categorizador LLM).

### Qué se AGREGA / CAMBIA
- **Etiquetado heurístico en Python** (titular medoide + keywords c-TF-IDF) — reemplaza el labeling del LLM.
- **Modelo de "importancia" para el eje Demanda** — reemplaza el conteo plano de señales. Cada fuente aporta importancia con su lógica y tope propios, agregada con rendimientos decrecientes.
- **Captura de estrellas de GitHub** (hoy se descartan).
- **Validación como bono, nunca penalización** (los breakouts sin cubrir ya no se hunden).
- **Sink de Notion** (`sinks/notion.py`) — escribe los temas a una base de datos de Notion vía la API oficial.
- **Migración de DB** — columnas `topics.keywords`, `topics.notion_page_id`, `topics.notion_synced_at`.

### Qué se MANTIENE intacto
- Todos los source adapters (HN, Reddit, RSS, HF, GitHub, Product Hunt, X/Apify, Trends) — **excepto** GitHub (se le agrega captura de estrellas).
- El escaneo de YouTube y detección de outliers (`sources/youtube.py`, `pipeline/outliers.py`).
- Los ejes **Saturación** y **Validación** (YouTube sigue siendo medidor de saturación y validador; **no** entra al modelo de importancia).
- El clustering por embeddings + DBSCAN (`_cluster_impl.py`) — se modifica solo para etiquetar y dejar de encolar.
- `channels_final.py` (NO se toca).
- La DB sigue commiteándose al repo (`data/intel.db`), sigue siendo la **única fuente de verdad**. El pipeline **nunca lee de Notion**.

---

## 1. Convenciones de ejecución

- Python 3.12, `uv` para paquetes, `ruff` para lint, `mypy --strict` para tipos.
- **Una fase = un commit** con el prefijo indicado. Ejecuta el comando de verificación de la fase antes de pasar a la siguiente.
- Después de cada fase: `uv run ruff check .` y `uv run mypy --strict src/` deben pasar. `uv run pytest -q` debe pasar al final de cada fase que toque tests.
- Todos los timestamps en UTC en la DB.
- No borres `data/intel.db`. Las migraciones son aditivas (ver Fase 1).

---

## FASE 0 — Dependencias y limpieza de Telegram

**Commit:** `chore: add notion-client, remove telegram alerting`

### 0.1 `pyproject.toml`
Agrega a `dependencies` (después de `sqlite-utils`):
```toml
    "notion-client>=2.2,<3.0",
```
Agrega al override de mypy (`[[tool.mypy.overrides]]`, lista `module`):
```toml
    "notion_client.*",
```
(Queda: `module = ["googleapiclient.*", "feedparser.*", "sentence_transformers.*", "pytrends.*", "notion_client.*"]`)

### 0.2 Eliminar `alerts.py`
- Borra `src/content_intel/alerts.py`.
- Borra cualquier test que lo importe (busca `from content_intel.alerts` y `import alerts`).

### 0.3 Regenerar lock
Ejecuta `uv sync --extra ml` para regenerar `uv.lock` con `notion-client`.

**Verificación:** `uv run python -c "import notion_client; print(notion_client.__name__)"` imprime `notion_client`. `grep -r "alerts" src/` no devuelve nada.

---

## FASE 1 — Migración de DB (columnas Notion + keywords)

**Commit:** `feat: db migration for notion sync and heuristic keywords`

SQLite no soporta `ADD COLUMN IF NOT EXISTS`, y `data/intel.db` ya existe commiteada, así que **no** basta con editar `_SCHEMA`. Hay que migrar con `PRAGMA table_info`.

### 1.1 En `src/content_intel/db.py`

Agrega al final del archivo:

```python
def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def migrate_db(path: Path = DB_PATH) -> None:
    """Apply additive migrations idempotently. Safe to run on every init."""
    conn = get_db(path)
    try:
        migrations: list[tuple[str, str, str]] = [
            ("topics", "keywords", "ALTER TABLE topics ADD COLUMN keywords TEXT"),
            ("topics", "notion_page_id", "ALTER TABLE topics ADD COLUMN notion_page_id TEXT"),
            ("topics", "notion_synced_at", "ALTER TABLE topics ADD COLUMN notion_synced_at TIMESTAMP"),
        ]
        for table, column, ddl in migrations:
            if not _column_exists(conn, table, column):
                conn.execute(ddl)
        conn.commit()
    finally:
        conn.close()
```

Modifica `init_db` para llamar a la migración:
```python
def init_db(path: Path = DB_PATH) -> None:
    conn = get_db(path)
    try:
        conn.executescript(_SCHEMA)
    finally:
        conn.close()
    migrate_db(path)
```

También agrega las tres columnas nuevas al bloque `CREATE TABLE ... topics` dentro de `_SCHEMA` (para bases nuevas creadas desde cero). El bloque `topics` queda:
```sql
CREATE TABLE IF NOT EXISTS topics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  label TEXT,
  cluster_id TEXT UNIQUE,
  embedding BLOB,
  first_seen TIMESTAMP NOT NULL,
  last_seen TIMESTAMP NOT NULL,
  category TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  keywords TEXT,
  notion_page_id TEXT,
  notion_synced_at TIMESTAMP
);
```

> **Nota:** la columna `topic_scores.fit` se **conserva** (no se borra, para no hacer una migración destructiva sobre la DB binaria commiteada). Simplemente se escribirá `0.0` y nunca se leerá (ver Fase 5).

### 1.2 Test
En `tests/test_pipeline/test_db_migration.py` (créalo):
```python
from content_intel.db import init_db, migrate_db, get_db, _column_exists

def test_migration_adds_columns(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    conn = get_db(db)
    try:
        for col in ("keywords", "notion_page_id", "notion_synced_at"):
            assert _column_exists(conn, "topics", col)
    finally:
        conn.close()

def test_migration_idempotent(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    migrate_db(db)  # second run must not raise
    migrate_db(db)
```

**Verificación:** `uv run pytest tests/test_pipeline/test_db_migration.py -q` pasa.

---

## FASE 2 — Captura de estrellas de GitHub

**Commit:** `feat: capture GitHub star velocity in trending adapter`

El adapter actual descarta las estrellas (`raw_metrics={}`). El modelo de importancia las necesita.

### 2.1 `src/content_intel/sources/github_trending.py`

Amplía las URLs (agrega "all languages" para no perder repos explotando fuera de python/typescript):
```python
_TRENDING_URLS = [
    "https://github.com/trending?since=daily",
    "https://github.com/trending?since=weekly",
    "https://github.com/trending/python?since=daily",
    "https://github.com/trending/python?since=weekly",
    "https://github.com/trending/typescript?since=daily",
]
```

Agrega un helper de parseo de estrellas (arriba de la clase):
```python
import re

_STARS_RE = re.compile(r"([\d,]+)\s+stars?\s+(today|this week)", re.IGNORECASE)


def _parse_stars_recent(article: Any) -> int:
    """Parse 'N stars today' / 'N stars this week' from a trending row. 0 if absent."""
    span = article.find("span", class_="d-inline-block float-sm-right")
    if span is None:
        return 0
    m = _STARS_RE.search(span.get_text(" ", strip=True))
    if not m:
        return 0
    return int(m.group(1).replace(",", ""))


def _parse_stars_total(article: Any) -> int:
    """Parse total stargazers count. 0 if absent."""
    a = article.find("a", href=lambda h: bool(h) and h.endswith("/stargazers"))
    if a is None:
        return 0
    txt = a.get_text(strip=True).replace(",", "")
    try:
        return int(txt)
    except ValueError:
        return 0
```

Dentro del loop, justo antes de construir el `RawSignal`, calcula:
```python
stars_today = _parse_stars_recent(article)
stars_total = _parse_stars_total(article)
```
Y cambia `raw_metrics={}` por:
```python
raw_metrics={"stars_today": stars_today, "stars_total": stars_total},
```

> **Importante sobre "today" vs "this week":** las URLs `?since=weekly` reportan "stars this week". Guárdalo igual en `stars_today` (el campo es el "momentum reciente de estrellas", sea diario o semanal). La normalización por `ref` en el scoring lo absorbe. No crees un campo separado.

### 2.2 Test
Guarda un fixture HTML real de la página de trending en `tests/fixtures/github_trending.html` (descárgalo una vez con `httpx` o cúralo a mano con al menos 2 filas `article.Box-row`, una con "stars today" y una con "stars this week"). Test en `tests/test_sources/test_github_trending.py`:
```python
# Monkeypatch httpx.Client.get para devolver el fixture, llama fetch(),
# y asserta que al menos una señal tiene raw_metrics["stars_today"] > 0.
```

**Verificación:** `uv run python -m content_intel.cli pull --sources github_trending --dry-run` corre sin error e imprime un conteo de señales de `github_trending`.

---

## FASE 3 — Etiquetado heurístico (reemplazo del LLM)

**Commit:** `feat: heuristic topic labeling (medoid title + c-TF-IDF keywords)`

Hoy los clusters nacen con `label=NULL, status='unlabeled'` esperando al LLM. Ahora se etiquetan en Python al crearse y nacen `status='active'`.

### 3.1 Nuevo módulo `src/content_intel/pipeline/labeling.py`

```python
"""Heuristic topic labeling — no LLM. Medoid title + c-TF-IDF keywords."""
from __future__ import annotations

import re

_STOPWORDS = {
    # EN
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on", "for",
    "and", "or", "but", "with", "this", "that", "it", "as", "at", "by", "from",
    "how", "what", "why", "new", "your", "you", "we", "i", "my", "be", "has",
    "have", "will", "can", "now", "just", "all", "more", "vs",
    # ES
    "el", "la", "los", "las", "un", "una", "de", "en", "que", "es", "con", "por",
    "para", "como", "este", "esta", "del", "se", "su", "lo", "al", "y", "o", "mi",
    "nuevo", "nueva", "muy", "ya", "hace",
}
_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9][a-zA-ZÀ-ÿ0-9.+#-]{1,}")


def pick_medoid_title(
    titles: list[str],
    embeddings: list[list[float]],
    centroid: list[float],
) -> str:
    """Return the title whose embedding is closest (cosine) to the centroid.

    `titles`, `embeddings` are aligned by index. Embeddings are L2-normalized,
    centroid is L2-normalized → cosine == dot product.
    """
    best_i = 0
    best_sim = -2.0
    for i, emb in enumerate(embeddings):
        sim = sum(x * y for x, y in zip(emb, centroid))
        if sim > best_sim:
            best_sim = sim
            best_i = i
    return titles[best_i]


def _tokenize(text: str) -> list[str]:
    return [
        t.lower()
        for t in _TOKEN_RE.findall(text)
        if len(t) >= 3 and t.lower() not in _STOPWORDS
    ]


def extract_keywords(cluster_texts: list[str], top_k: int = 5) -> list[str]:
    """Class-based TF-IDF keywords for a single cluster.

    Uses sklearn TfidfVectorizer fit over the cluster's documents (one doc per
    signal). Returns the top_k terms by summed TF-IDF weight. Falls back to raw
    frequency if sklearn is unavailable.
    """
    docs = [t for t in cluster_texts if t.strip()]
    if not docs:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer(
            tokenizer=_tokenize,
            preprocessor=lambda x: x,
            token_pattern=None,
            lowercase=False,
        )
        matrix = vec.fit_transform(docs)
        scores = matrix.sum(axis=0).A1  # type: ignore[union-attr]
        terms = vec.get_feature_names_out()
        ranked = sorted(zip(terms, scores), key=lambda kv: kv[1], reverse=True)
        return [t for t, _ in ranked[:top_k]]
    except Exception:
        from collections import Counter

        counter: Counter[str] = Counter()
        for d in docs:
            counter.update(_tokenize(d))
        return [t for t, _ in counter.most_common(top_k)]
```

### 3.2 Integrar en `_cluster_impl.py`

En `cluster_signals`, dentro del loop de creación de nuevos clusters (donde hoy se inserta el topic con `status='unlabeled'`):

1. Calcula el medoide y keywords **antes** del INSERT:
```python
from content_intel.pipeline.labeling import pick_medoid_title, extract_keywords
import json as _json

# cluster_titles y cluster_embs ya existen en el scope del loop
medoid_label = pick_medoid_title(cluster_titles, cluster_embs, centroid)
# textos completos (título + desc no está disponible aquí; usa títulos)
keywords = extract_keywords(cluster_titles, top_k=5)
```
2. Cambia el INSERT del topic para incluir `label`, `keywords` y `status='active'`:
```python
conn.execute(
    "INSERT INTO topics (label, keywords, cluster_id, embedding, first_seen, last_seen, status)"
    " VALUES (?, ?, ?, ?, ?, ?, 'active')",
    (
        medoid_label,
        _json.dumps(keywords),
        cluster_id,
        json.dumps(centroid).encode(),
        min_posted_at,
        max_posted_at,
    ),
)
```
> `cluster_embs` ya se define en el código actual como `cluster_embs = [orphan_embeddings[li] for li in local_indices]`. `centroid` también ya existe (`centroid = _centroid(cluster_embs)`). `cluster_titles` ya existe. No agregues nuevas consultas.

3. **Elimina** la llamada a `write_pending("needs_labeling", ...)` y el `queue_items.append(...)` y todo lo relacionado con `queue_items` / `queue_log` de labeling dentro de esta función.

4. **Elimina** la llamada a `ingest_done_files(conn, db_path)` al inicio de `cluster_signals` (ya no hay `.done.json`). Borra también la función `ingest_done_files` completa.

5. Borra el import `from content_intel.pipeline.queue import move_to_processed, read_done, write_pending`.

6. Mantén `mark_stale_topics(conn)` tal cual.

### 3.3 Test
`tests/test_pipeline/test_labeling.py`:
```python
from content_intel.pipeline.labeling import pick_medoid_title, extract_keywords

def test_medoid_picks_central_title():
    titles = ["A", "B", "C"]
    embs = [[1.0, 0.0], [0.0, 1.0], [0.9, 0.1]]
    centroid = [1.0, 0.0]
    assert pick_medoid_title(titles, embs, centroid) == "A"

def test_keywords_extracts_salient_terms():
    texts = ["Claude 4.7 release notes", "Claude 4.7 benchmarks", "Claude release impressions"]
    kws = extract_keywords(texts, top_k=3)
    assert "claude" in kws
```

**Verificación:** `uv run pytest tests/test_pipeline/test_labeling.py -q` pasa.

---

## FASE 4 — Modelo de importancia (eje Demanda)

**Commit:** `feat: source-weighted importance model for demand axis`

Reemplaza el cálculo de Demanda (conteo plano) por importancia agregada con topes por fuente.

### 4.1 `config/scoring.yml` (reescribir completo)

```yaml
# v2 scoring config
final:
  validation_max_bonus: 0.5   # validación 100 → +50%; validación 0 → +0% (nunca penaliza)

importance:
  # Modelo (todo en escala 0–100):
  #   signal_imp = cap * (1 - exp(-metric / ref)) * recency        [fuentes con métrica]
  #   signal_imp = constant_value * recency                        [fuente 'constant', p.ej. rss]
  #   contrib_S  = cap * (1 - Π_señales(1 - signal_imp/cap))       [OR dentro de la fuente]
  #   demand     = 100 * (1 - Π_fuentes(1 - contrib_S/100))        [OR entre fuentes]
  recency_halflife_days: 3
  sources:
    github_trending: { cap: 100, ref: 800,  metric: stars_today }
    hn:              { cap: 80,  ref: 300,  metric: points }
    hf:              { cap: 75,  ref: 200,  metric: hf_engagement }
    product_hunt:    { cap: 65,  ref: 500,  metric: votes }
    x_apify:         { cap: 60,  ref: 5000, metric: x_engagement }
    reddit:          { cap: 55,  ref: 1500, metric: reddit_engagement }
    rss:             { cap: 50,  ref: 0,    metric: constant, constant_value: 40 }
    gtrends:         { cap: 45,  ref: 5000, metric: value }

thresholds:
  notion_min_score: 55       # final_score mínimo para entrar a Notion
  min_demand: 40             # filtro duro: por debajo, se descarta
  min_saturation: 20         # filtro duro: por debajo (muy saturado en ES), se descarta
  stale_days: 10
  outlier_ratio: 3.0
  cluster_similarity: 0.78
  dbscan_eps: 0.22
  dbscan_min_samples: 3
  trend_up_delta: 2.0        # delta score vs ayer para marcar ↑
  trend_down_delta: -2.0     # delta score vs ayer para marcar ↓
  sparkline_window_days: 14
```

### 4.2 Nuevo módulo `src/content_intel/pipeline/importance.py`

```python
"""Source-weighted importance model — the Demand axis. No LLM."""
from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any


def _metric_value(source_key: str, raw: dict[str, Any], scfg: dict[str, Any]) -> float:
    """Derive a source's native magnitude metric from raw_metrics."""
    name = scfg["metric"]
    if name == "constant":
        return float(scfg.get("constant_value", 0))
    if name == "stars_today":
        return float(raw.get("stars_today", 0) or 0)
    if name == "points":
        return float(raw.get("points", 0) or 0)
    if name == "votes":
        return float(raw.get("votes", 0) or 0)
    if name == "value":
        return float(raw.get("value", 0) or 0)
    if name == "hf_engagement":
        return float(raw.get("likes", 0) or 0) + float(raw.get("downloads", 0) or 0) / 1000.0
    if name == "x_engagement":
        return float(raw.get("likes", 0) or 0) + 2.0 * float(raw.get("retweets", 0) or 0)
    if name == "reddit_engagement":
        ratio = float(raw.get("upvote_ratio", 0) or 0) or 1.0
        return float(raw.get("score", 0) or 0) * ratio
    return 0.0


def _recency_factor(posted_at: str, halflife_days: float) -> float:
    """0.5 ** (age_days / halflife). Clamped to [0, 1]."""
    try:
        dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    except ValueError:
        return 1.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    age_days = max(0.0, (datetime.now(UTC) - dt).total_seconds() / 86400.0)
    return float(0.5 ** (age_days / halflife_days))


def _signal_importance(metric: float, scfg: dict[str, Any], recency: float) -> float:
    cap = float(scfg["cap"])
    if scfg["metric"] == "constant":
        base = float(scfg.get("constant_value", 0))
    else:
        ref = float(scfg["ref"])
        base = cap * (1.0 - math.exp(-metric / ref)) if ref > 0 else 0.0
    return min(cap, base) * recency


def compute_demand(conn: sqlite3.Connection, topic_id: int, cfg: dict[str, Any]) -> float:
    """Aggregate per-source importance into a 0–100 demand score."""
    imp_cfg = cfg["importance"]
    sources_cfg: dict[str, Any] = imp_cfg["sources"]
    halflife = float(imp_cfg.get("recency_halflife_days", 3))

    rows = conn.execute(
        "SELECT source, raw_metrics, posted_at FROM signals WHERE topic_id=?",
        (topic_id,),
    ).fetchall()

    per_source: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        key = str(r["source"]).split(":")[0]  # 'reddit:LocalLLaMA' -> 'reddit'
        scfg = sources_cfg.get(key)
        if scfg is None:
            continue
        raw = json.loads(r["raw_metrics"] or "{}")
        metric = _metric_value(key, raw, scfg)
        recency = _recency_factor(str(r["posted_at"]), halflife)
        per_source[key].append(_signal_importance(metric, scfg, recency))

    # OR dentro de cada fuente (topado en cap), luego OR entre fuentes.
    cross_prod = 1.0
    for key, imps in per_source.items():
        cap = float(sources_cfg[key]["cap"])
        within_prod = 1.0
        for imp in imps:
            within_prod *= 1.0 - min(imp, cap) / cap
        contrib = cap * (1.0 - within_prod)
        cross_prod *= 1.0 - contrib / 100.0

    return 100.0 * (1.0 - cross_prod)
```

### 4.3 Test (incluye los ejemplos numéricos acordados)
`tests/test_pipeline/test_importance.py`:
```python
import json
from content_intel.db import get_db, init_db
from content_intel.pipeline.importance import compute_demand

_CFG = {
    "importance": {
        "recency_halflife_days": 36500,  # ~sin decaimiento para el test
        "sources": {
            "github_trending": {"cap": 100, "ref": 800, "metric": "stars_today"},
            "hn": {"cap": 80, "ref": 300, "metric": "points"},
            "reddit": {"cap": 55, "ref": 1500, "metric": "reddit_engagement"},
            "gtrends": {"cap": 45, "ref": 5000, "metric": "value"},
        },
    }
}

def _mk(tmp_path, signals):
    db = tmp_path / "t.db"
    init_db(db)
    conn = get_db(db)
    conn.execute("INSERT INTO topics (cluster_id, first_seen, last_seen, status) VALUES ('c', '2026-01-01', '2026-01-01', 'active')")
    tid = conn.execute("SELECT id FROM topics").fetchone()["id"]
    for src, raw in signals:
        conn.execute(
            "INSERT INTO signals (source, source_id, title, posted_at, raw_metrics, topic_id)"
            " VALUES (?, ?, 't', '2026-01-01T00:00:00+00:00', ?, ?)",
            (src, src + str(id(raw)), json.dumps(raw), tid),
        )
    conn.commit()
    return conn, tid

def test_exploding_repo_passes_alone(tmp_path):
    conn, tid = _mk(tmp_path, [("github_trending", {"stars_today": 9000})])
    assert compute_demand(conn, tid, _CFG) >= 95  # GH solo pasa

def test_reddit_alone_is_weak(tmp_path):
    conn, tid = _mk(tmp_path, [("reddit:LocalLLaMA", {"score": 100000, "upvote_ratio": 1.0})])
    assert compute_demand(conn, tid, _CFG) <= 55  # topado por cap, no pasa un umbral de 80

def test_reddit_plus_hn_corroborate(tmp_path):
    conn, tid = _mk(tmp_path, [
        ("reddit:LocalLLaMA", {"score": 100000, "upvote_ratio": 1.0}),
        ("hn", {"points": 100000}),
    ])
    assert compute_demand(conn, tid, _CFG) >= 80  # corroboración pasa
```

**Verificación:** `uv run pytest tests/test_pipeline/test_importance.py -q` pasa.

---

## FASE 5 — Reescribir el scoring (3 ejes, validación como bono)

**Commit:** `feat: rewrite scoring (importance demand, validation as bonus, drop fit/telegram)`

### 5.1 `src/content_intel/pipeline/score.py`

1. **Borra** los imports `from content_intel.alerts import send_message` y `from content_intel.pipeline.filters import is_banned` se mantiene.
2. **Borra** la función `_compute_demand` actual (la reemplaza `importance.compute_demand`).
3. **Borra** `_load_fit_weights` y todo uso de `fit_weights` / `fit_default` / `category` para fit.
4. Mantén `_compute_saturation` y `_compute_validation` **sin cambios**.
5. Reescribe `_score_topic`:
```python
from content_intel.pipeline.importance import compute_demand

def _score_topic(
    conn: sqlite3.Connection,
    topic_id: int,
    topic_row: sqlite3.Row,
    cfg: dict[str, Any],
) -> dict[str, Any] | None:
    label: str | None = topic_row["label"]
    if label and is_banned(label):
        return None

    thresholds = cfg.get("thresholds", {})
    min_demand = float(thresholds.get("min_demand", 40))
    min_saturation = float(thresholds.get("min_saturation", 20))
    max_bonus = float(cfg.get("final", {}).get("validation_max_bonus", 0.5))

    demand = compute_demand(conn, topic_id, cfg)
    if demand < min_demand:
        return None

    saturation = _compute_saturation(conn, topic_id)
    if saturation < min_saturation:
        return None

    validation, uncovered_breakout = _compute_validation(conn, topic_id)

    # Saturación descuenta (multiplicador); validación SOLO suma (bono), nunca penaliza.
    final = demand * (saturation / 100.0) * (1.0 + (validation / 100.0) * max_bonus)
    final = min(100.0, final)

    return {
        "demand": demand,
        "saturation": saturation,
        "validation": validation,
        "fit": 0.0,  # columna conservada por compatibilidad; sin uso
        "final": final,
        "uncovered_breakout": uncovered_breakout,
    }
```
6. Reescribe `run_score`:
   - Carga config con `_load_scoring_config()` (mantener) y pásala como `cfg`.
   - **Elimina** todo el bloque de "hot-topic crossings" y los `send_message(...)` (las alertas de Telegram se van).
   - Mantén el marcado de stale y el `INSERT OR REPLACE INTO topic_scores` (la firma del INSERT no cambia: sigue incluyendo `fit`, ahora con `0.0`).
   - El loop de topics: `WHERE status IN ('active','unlabeled')` → cámbialo a `WHERE status='active'` (ya no existe 'unlabeled' tras la Fase 3; los topics nacen 'active').

`run_score` queda aproximadamente:
```python
def run_score(db_path: Path = DB_PATH) -> None:
    cfg = _load_scoring_config()
    conn = get_db(db_path)
    today = date.today().isoformat()
    stale_cutoff = (datetime.now(UTC) - timedelta(days=10)).isoformat()

    topics = conn.execute(
        "SELECT id, label, category, status, first_seen, last_seen FROM topics WHERE status='active'"
    ).fetchall()

    scored_count = 0
    for topic_row in topics:
        topic_id = topic_row["id"]
        if topic_row["last_seen"] <= stale_cutoff:
            conn.execute("UPDATE topics SET status='stale' WHERE id=?", (topic_id,))
            continue
        scores = _score_topic(conn, topic_id, topic_row, cfg)
        if scores is None:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO topic_scores"
            " (topic_id, date, demand, saturation, validation, fit, final_score, uncovered_breakout)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (topic_id, today, scores["demand"], scores["saturation"], scores["validation"],
             scores["fit"], scores["final"], 1 if scores["uncovered_breakout"] else 0),
        )
        scored_count += 1

    conn.commit()
    conn.close()
    logger.info("Scoring complete: %d topics scored", scored_count)
```

### 5.2 Test
Actualiza/crea `tests/test_scoring.py`:
- Test: un topic con demanda alta, saturación 100, validación 0 (uncovered) NO se hunde → `final ≈ demand` y `uncovered_breakout = 1`.
- Test: validación alta sube el final por encima de `demand*sat/100`.
- Test: `demand < min_demand` → topic descartado (no se inserta en topic_scores).
- Elimina cualquier test de alertas Telegram / fit.

**Verificación:** `uv run pytest tests/test_scoring.py -q` pasa.

---

## FASE 6 — Limpiar validación (quitar comment mining, rankear por importancia)

**Commit:** `feat: trim validation to youtube search only, rank candidates by importance`

`validate.py` mantiene la búsqueda en YouTube (para los ejes Saturación y Validación) pero pierde el comment mining.

### 6.1 `src/content_intel/pipeline/validate.py`
1. **Borra** las funciones: `ingest_mining_done`, `_fetch_comments_blob`.
2. **Borra** el import `from content_intel.pipeline.queue import ...`.
3. En `run_validate`: **elimina** la llamada `ingest_mining_done(...)`, todo el bloque de `top5` / `mining_items` / `write_pending("needs_mining", ...)`. La función termina tras el loop de búsqueda y `conn.commit()`.
4. Mantén `_search_topic`, `_fetch_and_store_videos`, el cap de cuota, y `log_quota`.
5. Reescribe `_select_candidates` para rankear por **importancia** (no por el join de partial_score que no existe a esa hora):
```python
from content_intel.pipeline.importance import compute_demand
from content_intel.pipeline.score import _load_scoring_config

def _select_candidates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cfg = _load_scoring_config()
    rows = conn.execute(
        "SELECT id, label FROM topics WHERE status='active' AND label IS NOT NULL"
    ).fetchall()
    scored = []
    for row in rows:
        tid = row["id"]
        demand = compute_demand(conn, tid, cfg)
        lang_row = conn.execute(
            "SELECT language, COUNT(*) c FROM signals WHERE topic_id=?"
            " GROUP BY language ORDER BY c DESC LIMIT 1", (tid,),
        ).fetchone()
        language = "es" if lang_row and lang_row["language"] == "es" else "en"
        scored.append({"id": tid, "label": row["label"], "language": language, "demand": demand})
    scored.sort(key=lambda x: x["demand"], reverse=True)
    en = [c for c in scored if c["language"] == "en"][:MAX_SEARCH_EN]
    es = [c for c in scored if c["language"] == "es"][:MAX_SEARCH_ES]
    return (en + es)[:25]
```
6. `_fetch_and_store_videos`: mantén la lógica de outliers e inserción, pero **elimina** el tracking de `new_outliers` para mining si quieres (puedes dejar que retorne `[]`; ya no se usa). Mínimo cambio: deja la función pero ignora su retorno en `run_validate`.

> **No toques** `sources/youtube.py` ni `pipeline/outliers.py`.

### 6.2 Test
Actualiza `tests/test_pipeline/test_validate.py` (si existe): elimina asserts de mining; añade un test de `_select_candidates` que verifique orden por demanda (mockeando `compute_demand` o insertando señales con métricas).

**Verificación:** `uv run python -c "from content_intel.pipeline.validate import run_validate; print('ok')"` imprime `ok`.

---

## FASE 7 — Sink de Notion

**Commit:** `feat: notion sink — upsert scored topics to notion database`

### 7.1 Contrato del schema de Notion (DEBE coincidir exacto con el doc de creación)

La base de datos de Notion tiene estas propiedades (nombres y tipos EXACTOS):

| Propiedad | Tipo Notion | Origen (DB) | Quién escribe |
|---|---|---|---|
| `Tema` | Title | `topics.label` | pipeline |
| `Score` | Number | `topic_scores.final_score` (hoy) | pipeline |
| `Demanda` | Number | `topic_scores.demand` | pipeline |
| `Saturación` | Number | `topic_scores.saturation` | pipeline |
| `Validación` | Number | `topic_scores.validation` | pipeline |
| `Tendencia` | Select | calculado (↑/→/↓) | pipeline |
| `Score pico` | Number | `MAX(topic_scores.final_score)` | pipeline |
| `Prom. 7d` | Number | `AVG` últimos 7 | pipeline |
| `Histórico` | Rich text | sparkline | pipeline |
| `Días en radar` | Number | desde `first_seen` | pipeline |
| `Fuentes` | Multi-select | `DISTINCT signals.source` (prefijo) | pipeline |
| `# Señales` | Number | `COUNT(signals)` | pipeline |
| `Idiomas` | Multi-select | `DISTINCT signals.language` | pipeline |
| `Keywords` | Multi-select | `topics.keywords` | pipeline |
| `Breakout sin cubrir` | Checkbox | `topic_scores.uncovered_breakout` | pipeline |
| `Estado pipeline` | Select | `Activo`/`Stale` | pipeline |
| `Primera vez` | Date | `topics.first_seen` | pipeline |
| `Última señal` | Date | `topics.last_seen` | pipeline |
| `Actualizado` | Date | hoy | pipeline |
| `Mi decisión` | Select | — | **DUEÑO (el pipeline NUNCA la escribe en update; en create la pone en `📥 Nuevo`)** |

Valores de `Tendencia` (Select): `↑ Subiendo`, `→ Estable`, `↓ Bajando`.
Valores de `Mi decisión` (Select): `📥 Nuevo`, `👀 Considerando`, `🎬 A grabar`, `✅ Grabado`, `🗑️ Descartado`.
Valores de `Estado pipeline` (Select): `Activo`, `Stale`.

### 7.2 Nuevo paquete `src/content_intel/sinks/`
Crea `src/content_intel/sinks/__init__.py` (vacío) y `src/content_intel/sinks/notion.py`.

```python
"""Notion sink — upsert scored topics. Uses the Notion API (NOT an LLM)."""
from __future__ import annotations

import json
import logging
import math
import os
import random
import sqlite3
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from content_intel.db import DB_PATH, get_db
from content_intel.pipeline.score import _load_scoring_config

logger = logging.getLogger(__name__)

NOTION_VERSION = "2025-09-03"
_SPARK = "▁▂▃▄▅▆▇█"


def _client() -> Any:
    from notion_client import Client

    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        raise RuntimeError("NOTION_API_KEY not set — cannot sync to Notion")
    return Client(auth=api_key, notion_version=NOTION_VERSION)


def _with_retry(fn: Any, max_retries: int = 5) -> Any:
    from notion_client.errors import APIResponseError

    for attempt in range(max_retries):
        try:
            return fn()
        except APIResponseError as e:
            if e.status == 429:
                time.sleep((2 ** attempt) + random.uniform(0, 1))
            elif e.status >= 500:
                time.sleep(2 ** attempt)
            else:
                raise
    raise RuntimeError(f"Notion request failed after {max_retries} retries")


def _get_data_source_id(notion: Any, database_id: str) -> str:
    resp = _with_retry(lambda: notion.request(method="GET", path=f"databases/{database_id}"))
    data_sources = resp.get("data_sources", [])
    if not data_sources:
        raise RuntimeError(f"No data sources for database {database_id}")
    return str(data_sources[0]["id"])


def _sparkline(values: list[float]) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    return "".join(_SPARK[min(7, int((v - lo) / span * 7))] for v in values)


def _trend(today: float, yesterday: float | None, cfg: dict[str, Any]) -> str:
    if yesterday is None:
        return "→ Estable"
    th = cfg.get("thresholds", {})
    delta = today - yesterday
    if delta >= float(th.get("trend_up_delta", 2.0)):
        return "↑ Subiendo"
    if delta <= float(th.get("trend_down_delta", -2.0)):
        return "↓ Bajando"
    return "→ Estable"


def _gather(conn: sqlite3.Connection, topic_id: int, cfg: dict[str, Any]) -> dict[str, Any]:
    """Collect everything needed to build a Notion page for a topic."""
    today_iso = date.today().isoformat()
    yest_iso = (date.today() - timedelta(days=1)).isoformat()
    window = int(cfg.get("thresholds", {}).get("sparkline_window_days", 14))

    t = conn.execute(
        "SELECT label, keywords, first_seen, last_seen, status, notion_page_id FROM topics WHERE id=?",
        (topic_id,),
    ).fetchone()
    ts_today = conn.execute(
        "SELECT demand, saturation, validation, final_score, uncovered_breakout"
        " FROM topic_scores WHERE topic_id=? AND date=?", (topic_id, today_iso),
    ).fetchone()
    ts_yest = conn.execute(
        "SELECT final_score FROM topic_scores WHERE topic_id=? AND date=?", (topic_id, yest_iso),
    ).fetchone()
    peak = conn.execute(
        "SELECT MAX(final_score) m FROM topic_scores WHERE topic_id=?", (topic_id,),
    ).fetchone()["m"]
    avg7 = conn.execute(
        "SELECT AVG(final_score) a FROM (SELECT final_score FROM topic_scores"
        " WHERE topic_id=? ORDER BY date DESC LIMIT 7)", (topic_id,),
    ).fetchone()["a"]
    hist = conn.execute(
        "SELECT final_score FROM (SELECT date, final_score FROM topic_scores"
        " WHERE topic_id=? ORDER BY date DESC LIMIT ?) ORDER BY date ASC",
        (topic_id, window),
    ).fetchall()
    sources = [r["source"].split(":")[0] for r in conn.execute(
        "SELECT DISTINCT source FROM signals WHERE topic_id=?", (topic_id,)).fetchall()]
    langs = [r["language"] for r in conn.execute(
        "SELECT DISTINCT language FROM signals WHERE topic_id=? AND language IS NOT NULL",
        (topic_id,)).fetchall()]
    n_signals = conn.execute(
        "SELECT COUNT(*) c FROM signals WHERE topic_id=?", (topic_id,)).fetchone()["c"]
    signal_rows = conn.execute(
        "SELECT title, url FROM signals WHERE topic_id=? AND url IS NOT NULL"
        " ORDER BY posted_at DESC LIMIT 15", (topic_id,)).fetchall()
    video_rows = conn.execute(
        "SELECT title, views, outlier_ratio, video_id FROM yt_videos"
        " WHERE topic_id=? AND outlier_ratio IS NOT NULL ORDER BY outlier_ratio DESC LIMIT 5",
        (topic_id,)).fetchall()

    first_seen = str(t["first_seen"])[:10]
    days = (date.today() - date.fromisoformat(first_seen)).days if first_seen else 0
    keywords = json.loads(t["keywords"] or "[]")

    return {
        "page_id": t["notion_page_id"],
        "label": t["label"] or "(sin título)",
        "demand": round(float(ts_today["demand"]), 1),
        "saturation": round(float(ts_today["saturation"]), 1),
        "validation": round(float(ts_today["validation"]), 1),
        "final": round(float(ts_today["final_score"]), 1),
        "uncovered": bool(ts_today["uncovered_breakout"]),
        "trend": _trend(float(ts_today["final_score"]),
                        float(ts_yest["final_score"]) if ts_yest else None, cfg),
        "peak": round(float(peak or 0), 1),
        "avg7": round(float(avg7 or 0), 1),
        "sparkline": _sparkline([float(r["final_score"]) for r in hist]),
        "days": days,
        "sources": sorted(set(sources)),
        "langs": sorted(set(langs)),
        "keywords": keywords,
        "n_signals": int(n_signals),
        "first_seen": first_seen,
        "last_seen": str(t["last_seen"])[:10],
        "status": "Stale" if t["status"] == "stale" else "Activo",
        "signals": [(r["title"], r["url"]) for r in signal_rows],
        "videos": [(r["title"], int(r["views"] or 0), float(r["outlier_ratio"] or 0), r["video_id"])
                   for r in video_rows],
    }


def _properties(d: dict[str, Any], *, is_create: bool) -> dict[str, Any]:
    """Build the Notion properties payload. NEVER includes 'Mi decisión' on update."""
    props: dict[str, Any] = {
        "Tema": {"title": [{"text": {"content": d["label"][:200]}}]},
        "Score": {"number": d["final"]},
        "Demanda": {"number": d["demand"]},
        "Saturación": {"number": d["saturation"]},
        "Validación": {"number": d["validation"]},
        "Tendencia": {"select": {"name": d["trend"]}},
        "Score pico": {"number": d["peak"]},
        "Prom. 7d": {"number": d["avg7"]},
        "Histórico": {"rich_text": [{"text": {"content": d["sparkline"] or "—"}}]},
        "Días en radar": {"number": d["days"]},
        "Fuentes": {"multi_select": [{"name": s} for s in d["sources"]]},
        "# Señales": {"number": d["n_signals"]},
        "Idiomas": {"multi_select": [{"name": l} for l in d["langs"]]},
        "Keywords": {"multi_select": [{"name": k[:100]} for k in d["keywords"]]},
        "Breakout sin cubrir": {"checkbox": d["uncovered"]},
        "Estado pipeline": {"select": {"name": d["status"]}},
        "Primera vez": {"date": {"start": d["first_seen"]}},
        "Última señal": {"date": {"start": d["last_seen"]}},
        "Actualizado": {"date": {"start": date.today().isoformat()}},
    }
    if is_create:
        props["Mi decisión"] = {"select": {"name": "📥 Nuevo"}}
    return props


def _body_blocks(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Children blocks written ONLY on page creation (signals + reference videos)."""
    blocks: list[dict[str, Any]] = [
        {"object": "block", "type": "heading_2",
         "heading_2": {"rich_text": [{"text": {"content": "Señales"}}]}},
    ]
    for title, url in d["signals"]:
        blocks.append({
            "object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": title[:180], "link": {"url": url}}}]},
        })
    blocks.append({"object": "block", "type": "heading_2",
                   "heading_2": {"rich_text": [{"text": {"content": "Videos de referencia (EN)"}}]}})
    for title, views, ratio, vid in d["videos"]:
        line = f"{title[:120]} — {views:,} views ({ratio:.1f}×)"
        blocks.append({
            "object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": line,
                 "link": {"url": f"https://youtube.com/watch?v={vid}"}}}]},
        })
    return blocks


def run_notion_sync(db_path: Path = DB_PATH) -> None:
    database_id = os.environ.get("NOTION_DATABASE_ID")
    if not database_id:
        raise RuntimeError("NOTION_DATABASE_ID not set — cannot sync to Notion")

    cfg = _load_scoring_config()
    min_score = float(cfg.get("thresholds", {}).get("notion_min_score", 55))
    today_iso = date.today().isoformat()

    notion = _client()
    data_source_id = _get_data_source_id(notion, database_id)
    conn = get_db(db_path)
    try:
        # Temas a sincronizar: los que hoy superan el umbral, MÁS los que ya están en Notion
        # (actualización perpetua para ver su evolución aunque bajen).
        rows = conn.execute(
            "SELECT DISTINCT t.id FROM topics t"
            " JOIN topic_scores ts ON ts.topic_id=t.id AND ts.date=?"
            " WHERE ts.final_score >= ? OR t.notion_page_id IS NOT NULL",
            (today_iso, min_score),
        ).fetchall()

        synced = 0
        for row in rows:
            topic_id = row["id"]
            has_today = conn.execute(
                "SELECT 1 FROM topic_scores WHERE topic_id=? AND date=?", (topic_id, today_iso),
            ).fetchone()
            if not has_today:
                continue  # sin score de hoy no hay nada que actualizar
            d = _gather(conn, topic_id, cfg)
            if d["page_id"]:
                _with_retry(lambda d=d: notion.pages.update(
                    page_id=d["page_id"], properties=_properties(d, is_create=False)))
            else:
                created = _with_retry(lambda d=d: notion.pages.create(
                    parent={"type": "data_source_id", "data_source_id": data_source_id},
                    properties=_properties(d, is_create=True),
                    children=_body_blocks(d),
                ))
                conn.execute("UPDATE topics SET notion_page_id=? WHERE id=?",
                             (created["id"], topic_id))
            conn.execute("UPDATE topics SET notion_synced_at=? WHERE id=?",
                         (datetime.now(UTC).isoformat(), topic_id))
            conn.commit()
            synced += 1

        logger.info("Notion sync complete: %d topics upserted", synced)
    finally:
        conn.close()
```

> **Reglas críticas del sink:**
> - En `update` **nunca** se envía `Mi decisión` (la decisión del dueño es intocable).
> - El cuerpo (`children`) se escribe **solo al crear** la página. En updates solo se actualizan propiedades. La evolución temporal es visible vía `Histórico` (sparkline), `Tendencia`, `Score pico` y `Prom. 7d`, que SÍ se actualizan a diario.
> - `notion_page_id` se persiste en la DB para que el pipeline **nunca** tenga que consultar Notion.

### 7.3 CLI
En `src/content_intel/cli.py` agrega un comando:
```python
@app.command("notion-sync")
def notion_sync() -> None:
    """Upsert scored topics to the Notion database."""
    from content_intel.sinks.notion import run_notion_sync

    run_notion_sync()
```

### 7.4 Test
`tests/test_sinks/test_notion.py` (crea `tests/test_sinks/__init__.py`):
- Test `_sparkline([0,50,100]) == "▁▅█"` (o equivalente determinista — ajusta el assert al mapeo exacto).
- Test `_trend(80, 70, cfg) == "↑ Subiendo"`, `_trend(70, 80, cfg) == "↓ Bajando"`, `_trend(75, 75, cfg) == "→ Estable"`, `_trend(80, None, cfg) == "→ Estable"`.
- Test `_properties(d, is_create=False)` **no** contiene la clave `"Mi decisión"`; `_properties(d, is_create=True)` **sí** y vale `📥 Nuevo`.

**Verificación:** `uv run pytest tests/test_sinks/ -q` pasa. `uv run mypy --strict src/` pasa.

---

## FASE 8 — Orquestación (run_pipeline + workflow)

**Commit:** `feat: wire notion sync into finalize stage, drop telegram/queue from orchestration`

### 8.1 `scripts/run_pipeline.py`
1. En el stage `finalize`, después de `run_score()`, agrega el sync de Notion:
```python
    if args.stage in ("finalize", "all"):
        from content_intel.pipeline.score import run_score
        run_score()
        from content_intel.sinks.notion import run_notion_sync
        run_notion_sync()
```
2. No hay cambios en los demás stages.

### 8.2 `.github/workflows/daily.yml`
1. En el step **"Run pipeline stage"**, en `env:`: **elimina** `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`. **Agrega**:
```yaml
          NOTION_API_KEY: ${{ secrets.NOTION_API_KEY }}
          NOTION_DATABASE_ID: ${{ secrets.NOTION_DATABASE_ID }}
```
2. **Elimina** completo el step **"Notify on failure"** (dependía de Telegram). GitHub Actions ya notifica fallos por su cuenta al dueño del repo.
3. No cambies los crons ni la lógica de mapeo de stages.

### 8.3 `CLAUDE.md` (raíz del proyecto `code/Scripts automation/`)
Actualiza la sección de Routines y la tabla de stages para reflejar v2:
- Borra la sección **"Claude.ai Routines (the reasoning layer)"** entera.
- En la tabla de stages, cambia la fila `finalize` a: `final scoring pass + upsert a Notion`.
- Borra menciones a Telegram (la fila de fallo) y a la cola.
- Agrega un punto en "Architecture invariants": *"7. La única superficie de salida es la base de datos de Notion, escrita por `sinks/notion.py` vía la API de Notion (no es un LLM). El pipeline nunca lee de Notion; la DB SQLite es la única fuente de verdad."*

### 8.4 Secretos (documentar en README.md)
Tabla de secrets: **quita** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. **Agrega** `NOTION_API_KEY`, `NOTION_DATABASE_ID`.

**Verificación:** `uv run python scripts/run_pipeline.py --stage finalize` corre contra una DB local. Si `NOTION_API_KEY`/`NOTION_DATABASE_ID` no están, falla con `RuntimeError` claro (comportamiento correcto: fallar ruidoso, sin fallback silencioso). Con secretos válidos y una base de Notion compartida con la integración, crea/actualiza páginas.

---

## FASE 9 — Borrado final de código muerto + verificación E2E

**Commit:** `chore: remove dead queue/routine/telegram code, end-to-end verification`

### 9.1 Borrar
- `src/content_intel/pipeline/queue.py` (verifica antes con `grep -rn "pipeline.queue\|pipeline import queue" src/ tests/ scripts/` que no quede ningún import; los de cluster/validate ya se quitaron en Fases 3 y 6).
- `prompts/daily_routine.md`, `prompts/weekly_routine.md` (y el `prompts/` si queda vacío salvo placeholder).
- Tests obsoletos: cualquiera que pruebe `queue`, `needs_mining`, `needs_labeling`, Telegram, o `ingest_done_files`.
- En `.gitignore`: la línea `data/queue/*/processed/` puede quedarse (inofensiva) o borrarse.

> **No borres** las tablas `comment_insights`, `queue_log`, `run_log` de la DB — son inofensivas y borrarlas implicaría migración destructiva. Quedan sin uso.

### 9.2 Verificación end-to-end (sin red para fuentes, con DB sintética)
1. `uv run ruff check .` → sin errores.
2. `uv run mypy --strict src/` → sin errores.
3. `uv run pytest -q` → todo verde.
4. Smoke test del flujo de scoring→notion con una DB sintética y la API de Notion mockeada (un test E2E en `tests/test_e2e_finalize.py` que inserte 1 topic con señales de GitHub explotando, corra `run_score`, y verifique que `topic_scores` tiene una fila con `final_score >= notion_min_score` y `uncovered_breakout=1`).

### 9.3 Checklist de aceptación final (todo debe cumplirse)
- [ ] El pipeline no importa `anthropic`, `openai`, ni `transformers` (salvo `sentence-transformers`). `grep -rn "import anthropic\|import openai" src/` vacío.
- [ ] `grep -rn "telegram\|send_message\|alerts" src/` vacío.
- [ ] `grep -rn "needs_mining\|needs_labeling\|pipeline.queue" src/` vacío.
- [ ] Un repo de GitHub con muchas estrellas-hoy, sin ninguna otra fuente, supera `min_demand` y entra a Notion (test de Fase 4 + Fase 9).
- [ ] Un topic con validación 0 (uncovered) y demanda alta NO se hunde (test de Fase 5).
- [ ] `Mi decisión` nunca aparece en un payload de `update` (test de Fase 7).
- [ ] La DB `data/intel.db` conserva sus datos (la migración fue aditiva).

---

## Apéndice A — Mapa de cambios por archivo

| Archivo | Acción |
|---|---|
| `pyproject.toml` | + `notion-client`, + override mypy |
| `src/content_intel/db.py` | + `migrate_db`, `_column_exists`; columnas nuevas en `_SCHEMA`; `init_db` llama migración |
| `src/content_intel/sources/github_trending.py` | + captura de estrellas, + URLs all-languages |
| `src/content_intel/pipeline/labeling.py` | **nuevo** — medoide + keywords |
| `src/content_intel/pipeline/importance.py` | **nuevo** — modelo de importancia (Demanda) |
| `src/content_intel/pipeline/_cluster_impl.py` | etiquetado inline, status='active', sin cola, sin `ingest_done_files` |
| `src/content_intel/pipeline/cluster.py` | sin cambios (sigue delegando a `_cluster_impl`) |
| `src/content_intel/pipeline/score.py` | reescrito: importancia, validación-bono, sin fit, sin Telegram |
| `src/content_intel/pipeline/validate.py` | sin comment mining, candidatos por importancia |
| `src/content_intel/sinks/__init__.py` | **nuevo** (vacío) |
| `src/content_intel/sinks/notion.py` | **nuevo** — sink de Notion |
| `src/content_intel/cli.py` | + comando `notion-sync` |
| `src/content_intel/alerts.py` | **borrado** |
| `src/content_intel/pipeline/queue.py` | **borrado** |
| `config/scoring.yml` | reescrito (v2) |
| `config/fit_weights.yml` | queda sin uso (puede borrarse) |
| `scripts/run_pipeline.py` | finalize llama `run_notion_sync` |
| `.github/workflows/daily.yml` | secrets Notion en vez de Telegram, sin notify-on-failure |
| `prompts/*.md` | **borrados** |
| `CLAUDE.md`, `README.md` | actualizados a v2 |

## Apéndice B — Modelo de importancia (referencia matemática)

Para cada señal de fuente `S` con métrica nativa `m` y antigüedad `age` (días):
```
recency      = 0.5 ^ (age / halflife)                 # halflife = 3 días
signal_imp   = cap_S · (1 − e^(−m / ref_S)) · recency     (métrica continua)
signal_imp   = constant_value · recency                   (fuente 'constant', p.ej. rss)
```
Para cada fuente en un cluster (con señales i):
```
contrib_S = cap_S · (1 − Π_i (1 − signal_imp_i / cap_S))
```
Demanda del cluster:
```
demand = 100 · (1 − Π_S (1 − contrib_S / 100))
```
Score final:
```
final = min(100, demand · (saturation/100) · (1 + (validation/100)·max_bonus))
```
`max_bonus = 0.5`. La saturación descuenta (multiplicador ≤ 1); la validación solo suma (factor ≥ 1). Un breakout sin cubrir tiene `validation=0` → factor 1.0 → **no penaliza**.
