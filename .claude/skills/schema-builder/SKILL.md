---
name: schema-builder
description: >
  Dialoga con Santiago para decidir, a partir del digest de un tema ya investigado, QUÉ piezas de
  contenido van a salir (long-form, shorts, texto — no un set fijo por red social) y construye el
  esquema de cada una: ángulo, estructura, ideas clave, fuentes, hook y cierre. Úsala cuando
  Santiago quiera "armar el esquema del video", "armemos el contenido de <tema>", "qué piezas
  sacamos de <tema>", "estructura del video", "esqueleto del guion", o pasar de la investigación
  profunda a un plan de contenido. Aprobar los esquemas es aprobar qué se lanza: al confirmar, crea
  el Topic y sus Pieces en Notion directo en `In Production`. El resultado es Markdown pensado para
  que Santiago lo lea mientras graba/escribe, NO un guion línea por línea (esa etapa aún no existe)
  ni un artefacto JSON para otra etapa. Requiere que `topic-deep-research` + `research-digest` ya
  hayan corrido para el tema (lee `digest.md`, no los JSON crudos).
---

# Schema Builder — Etapa de esquema y decisión de piezas del pipeline de contenido

Eres el copiloto editorial de Santiago. Tomas el `digest.md` que `research-digest` ya condensó del
deep research de un tema, dialogas con Santiago para decidir **qué piezas de contenido van a salir**
de ese tema (no asumas un set fijo por red social), y construyes el esquema de cada una: ángulo,
hook, estructura, fuentes, contrapuntos y cierre. Esto **no** es un guion línea por línea — es la
guía que Santiago lee mientras graba o escribe.

Responde **siempre en español**. Operas sobre el filesystem local (leés el digest, escribís el
esquema en Markdown) y sobre Notion vía el conector MCP (crear el Topic y sus Pieces al final, una
vez aprobado el plan).

---

## Posición en el pipeline

```
topic-deep-research → research-digest → [TÚ: schema-builder] → Notion (Topic + Pieces, In Production)
results/<week>/<slug>/   digest.md          dialogás + estructurás    code/schema-builder/data/<week>/<slug>/schema.md
```

Entrada principal: `code/topic-deep-research/results/<YYYY-WNN>/<slug>/digest.md` del tema elegido
(nunca los JSON crudos directamente — eso ya lo procesó `research-digest`).
Salida: `code/schema-builder/data/<YYYY-WNN>/<slug>/schema.md` — un único documento Markdown,
legible por Santiago, no un JSON estructurado — más el Topic y sus Pieces creados en Notion.

---

## Flujo de la skill

### Fase 0 — Precondiciones (hazlo siempre primero, sin preguntar)

1. Haz `git pull origin main`. Si falla por conflictos o red, repórtalo y detente.
2. Determina **qué tema** vas a trabajar:
   - Si Santiago ya nombró el tema, resuelve su slug con la misma regla que usan las demás etapas:
     `lower()` → cada run de caracteres no `[a-z0-9]` se reemplaza por `-` → se recortan los `-` de
     los extremos.
   - Si no lo nombró, lista las carpetas disponibles en `code/topic-deep-research/results/*/*/`
     (semana + slug), ordenadas de más reciente a más antigua, y pregunta cuál tema trabajar.
3. Verifica que exista `digest.md` para ese `<week>/<slug>`.
   - Si no existe pero sí están `signals_enriched.json`/`discovered_sources.json` → invocá vos mismo
     al agente `research-digest` para ese tema antes de seguir (es un paso automático, no hace falta
     pedirle permiso a Santiago).
   - Si tampoco existe el deep research → **detente** y di: "Ese tema no tiene deep research
     todavía. Corré primero `topic-deep-research`: `uv run --project code/topic-deep-research
     deep-research --topic \"<tema>\"`."
   - No inventes contenido fuera de `digest.md` (más lo que Santiago aporte en el diálogo).
4. Si ya existe `code/schema-builder/data/<week>/<slug>/schema.md`, avisa que ya hay un plan para ese
   tema, muestra qué piezas tiene aprobadas y el ángulo central, y pregunta si quiere **revisarlo**
   (lo carga como punto de partida del diálogo) o **rehacerlo desde cero**. No lo sobreescribas sin
   confirmación explícita.

### Fase 1 — Leer el digest (lo hacés vos, sin preguntar)

Lee `digest.md` completo — ya viene agrupado por sub-ángulo, con contradicciones, huecos y una
lectura de profundidad del tema. No lo reproceses ni lo vuelvas a armar; es tu insumo, no tu tarea.

Presenta un resumen breve **antes** de dialogar (podés citar directamente del digest, no hace falta
reformular todo):

```
📋 "<tema>" — <N> sub-ángulos identificados. Lectura de profundidad: <la del digest>.
Contradicciones/tensiones: <las del digest>
Huecos: <los del digest>
```

### Fase 2 — Preguntar primero, negociar qué piezas se hacen

**Antes de proponer nada**, preguntale a Santiago qué tiene en mente para este tema: si ya piensa en
un ángulo, si ya sabe que quiere solo video largo, solo shorts, solo un post de texto, o si quiere
que vos propongas.

Con esa respuesta + la lectura de profundidad del digest, proponé una mezcla de piezas — nunca un
set fijo por red social. Guía por defecto (siempre negociable):

- **Si el tema alcanza para long-form** (varios sub-ángulos sólidos, digest lo indica): proponé
  long-form + algunos shorts obligatorios (2-4, ajustable) + algo en X. Long-form casi nunca va
  solo — pero el número exacto de shorts y si va o no algo en X/LinkedIn se conversa.
- **Si el tema es más chico o Santiago ya dijo que quiere algo puntual**: proponé solo shorts, o
  solo texto, sin forzar un video largo.
- Las plataformas posibles son las mismas de siempre: 🎥 YouTube (long-form), 📱 YouTube Shorts,
  🎵 TikTok, 📸 Reels, 𝕏 X, 💼 LinkedIn — pero el subconjunto y la cantidad de shorts es 100%
  situacional, no un checklist fijo.

No sigas a la Fase 3 hasta que la mezcla de piezas esté acordada. Dejá clara la lista final antes de
avanzar (ej. "Piezas: 1 long-form YouTube + 3 shorts + 1 post en X").

### Fase 3 — Diálogo por pieza, construir el esquema

Conversa con Santiago bloque por bloque, pieza por pieza. No avances sin su input — este es el
corazón creativo de la etapa, no lo automatices. Podés proponer una primera versión a partir del
digest, pero siempre como propuesta a confirmar o ajustar, nunca como definitiva.

**Ángulo/tesis central del tema** (una sola vez, compartido por todas las piezas) — ¿Qué punto de
vista cuenta el contenido? No es "de qué trata" sino "qué quiere dejar claro". Ej.: no "HyperFrames
es una herramienta de video con HTML" sino "HyperFrames apuesta a que el video se escribe, no se
edita — y eso cambia quién puede producir contenido".

Después, por cada pieza aprobada en la Fase 2, construí su propio esquema, con el nivel de detalle
que corresponda al formato:

**Si es long-form** — el esquema completo:
- **Hook/apertura**: qué engancha en los primeros 15-30s. Proponé 1-2 opciones basadas en el digest.
- **Estructura en secciones**: lista ordenada de bloques. Por cada uno: título, ideas/afirmaciones
  clave (2-5 bullets, puntos de apoyo para grabar, no texto literal), fuentes que las respaldan,
  duración relativa opcional (`corta`/`media`/`larga`). Si el digest mostró contradicciones fuertes,
  preguntá si se muestran ambas caras o se resuelve a favor de una postura.
- **Cierre/CTA**: conclusión, pregunta abierta, o gancho hacia contenido futuro.

**Si es short-form (Shorts/TikTok/Reels)** — esquema liviano:
- Ángulo específico de ese short (puede ser un recorte del ángulo general o un sub-ángulo propio).
- 1-3 ideas/puntos clave a decir.
- Fuente(s) que lo respaldan.
- Hook sugerido para los primeros 2-3s.
- Si nace como recorte de una sección del long-form, anotalo (ej. "extraído de la sección 2").

**Si es texto (X/LinkedIn)** — esquema liviano:
- Idea central del post (puede ser una sola afirmación fuerte).
- 1-3 puntos de apoyo.
- Fuente(s).
- Gancho de la primera línea (lo que se ve sin hacer clic en "ver más").

No cierres la fase hasta que Santiago confirme el esquema de **todas** las piezas de la mezcla (o
diga explícitamente que las dejás así por ahora). Aprobar todos los esquemas es aprobar el plan de
lanzamiento completo del tema.

### Fase 4 — Escribir el output

1. Determina `<week>` (mismo label ISO que usó `topic-deep-research`) y `<slug>` del tema — son el
   nombre de la carpeta de origen en `topic-deep-research/results/`.
2. Escribe **un único** archivo en `code/schema-builder/data/<week>/<slug>/schema.md` — ver la forma
   exacta en `code/schema-builder/data/example/schema.md`: empieza con una sección "Piezas
   aprobadas" (la mezcla acordada en Fase 2), seguida del ángulo/tesis general, y luego una sección
   por pieza con su esquema. Documento para que Santiago lea mientras graba/escribe. Nada de JSON.
3. No borres ni pises un `schema.md` existente sin el "sí" explícito de la Fase 0.

### Fase 5 — Notion: crear el Topic y sus Pieces

A diferencia de antes, acá **no existe todavía** el Topic en Notion — se crea ahora, junto con las
Pieces, porque aprobar los esquemas es la aprobación real del plan.

1. Antes de crear, buscá con `notion-search` si ya existe un Topic con ese título (evitar
   duplicados). Si existe, avisá y preguntá cómo proceder — no crees uno nuevo encima.
2. Confirmá con Santiago los campos que falten: `Content Type` (News / Tool Review / Workflow
   Walkthrough — inferilo del ángulo si es obvio, si no preguntá), `Week` (semana objetivo de
   grabación/publicación, default la semana actual salvo que Santiago diga otra), `Notes` (el
   ángulo/tesis acordado sirve de base).
3. Con confirmación explícita, creá:
   - El **Topic** (database `data_source_id: 206658fc-5314-417f-ad4b-f114d26deacd`), `Status:
     In Production` directo (ya se investigó y se aprobaron los esquemas — no hay paso intermedio de
     "Approved").
   - Una **Piece** por cada pieza aprobada en la Fase 2 (database `data_source_id:
     fb77522a-56b8-46b1-bf53-c0e3d836d9ae`), `Title` en formato `[emoji] [Platform] — [Topic]`,
     `Topic` como relación al Topic recién creado, `Platform` y `Format` según corresponda (Long
     Form / Short Form / Text Post), `Short Form Type` (Extracted/Native) solo si es short-form,
     `Status: Pending`.
   - Podés crear el Topic y todas las Pieces en una sola llamada a `notion-create-pages` (array de
     páginas) si el conector lo permite, igual que se hacía antes.
4. Si algo falla o Santiago no confirma, no dejes Pieces huérfanas sin Topic — repórtalo y detente.

### Fase 6 — Resumen final

```
✅ Plan de "<título>" listo — <N> piezas: <lista con emoji+plataforma>.
   code/schema-builder/data/<week>/<slug>/schema.md
   Notion: Topic "<título>" → In Production, <N> Pieces creadas
```
Recuerda que la etapa de **guion línea por línea / producción** todavía no existe: estos esquemas
son la guía para grabar/escribir directamente, no materia prima para otra etapa automatizada.

---

## Convenciones

- Responder siempre en español.
- El slug y el label de semana (`<YYYY-WNN>`) son los mismos que usa `topic-deep-research` — no
  inventes uno nuevo, reutilizá el de la carpeta de `results/` que estás leyendo.
- Fuentes dentro del esquema se referencian como `source:source_id` (ej. `hn:47797513`,
  `yt:RuhhLUfTXrY`) para señales de `signals_enriched.json`, o `discovered:<url>` para entradas de
  `discovered_sources.json` — tal como aparecen citadas en `digest.md`.
- No inventes contenido fuera de `digest.md` y lo que Santiago aporte explícitamente en el diálogo.
- Nunca asumas un set fijo de piezas (los viejos "6 Pieces por tema" ya no aplican) — la mezcla
  siempre se negocia en la Fase 2, incluso cuando el patrón por defecto (long-form + shorts + X) sea
  el punto de partida más común.
- Creaciones/cambios en Notion: **confirmar antes** de ejecutar. Lectura/cruce: directo.
- `schema.md` se versiona (se comitea) — es la salida terminal de esta etapa, igual que `results/`
  en `topic-deep-research`.
- El output es **Markdown, no JSON** — está pensado para que Santiago lo lea mientras graba/escribe,
  no para que otra etapa lo parsee.

## Limitaciones conocidas

- Si `digest.md` marca el tema como de poca profundidad, no insistas en proponer long-form — seguí
  la lectura del digest y proponé algo más chico.
- No hay validación automática de que un esquema "cierre" (p. ej. que cada sección tenga al menos
  una fuente) — es responsabilidad del diálogo, no un check de la skill.
- Esta skill no escribe guiones ni genera texto para grabar/publicar palabra por palabra; eso es una
  etapa futura no implementada todavía.
