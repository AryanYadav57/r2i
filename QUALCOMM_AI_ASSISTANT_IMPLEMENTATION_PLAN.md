# R2I + Qualcomm Imagine AI Assistant — Implementation Plan

**Status:** Plan only; no application or engine integration is included in this document change.
**Objective:** Add a grounded assistant that explains an already-computed R2I route comparison and answers questions about that comparison, using the Qualcomm Imagine inference API.
**Architecture boundary:** Existing route calculations remain authoritative and unchanged. The assistant is a separate, optional presentation layer.

## 1. Product behavior

After a user calculates a route, the app can:

1. Explain why the selected R2I route differs from the normal route.
2. Summarize the travel-time, distance, emissions, fuel/energy, and cost trade-offs that are present in the result.
3. Answer follow-up questions about the currently displayed comparison, traffic scenario, and optimizer details using only supplied result data.
4. Say when a requested fact is unavailable instead of estimating or inventing it.

The user must explicitly request an explanation or submit a question. Route search, map interactions, and Streamlit reruns must not make implicit inference calls.

## 2. Non-negotiable engine boundary

The assistant must not select, rerank, mutate, or generate routes. It must not calculate traffic, emissions, travel time, risk, savings, or benchmark values. It must not feed generated text back into the optimizer.

During this work, leave these files and artifacts unchanged:

- `r2i_engine.py`
- `candidate_routes.py`
- `quantum_inspired.py`
- `traffic_provider.py`
- `benchmark.py` and `benchmark_comparison.py`
- GraphML road-network files and route candidate/weight formulas

`app.py` may receive presentation and orchestration changes only. New assistant behavior belongs in new modules. Existing engine outputs remain the only source of route and metric truth.

## 3. Target architecture

```text
User selects an origin, destination, and scenario
                    │
                    ▼
          Existing R2I route flow
 NetworkX · traffic · candidates · QUBO
                    │
                    ▼
      Existing route_results in app.py
       (immutable input to assistant)
                    │
       user clicks Explain / asks a question
                    ▼
       assistant_context.py
  whitelist + normalize result facts
                    │
                    ▼
         imagine_client.py
  authenticated, bounded HTTPS chat call
                    │
                    ▼
      AI explanation in the UI
  cannot alter route, metrics, or map
```

The Imagine API offers multiple inference categories. For this project, start with its chat-completion endpoint. The API's authenticated model listing was checked on **2026-11-03** and returned LLM models (`Llama-3.1-8B`, `Llama-3.3-70B`, `DeepSeek-R1-Distill-Llama-70B`, `Qwen-QwQ-32B`), text-to-image (`stabilityai/sdxl-turbo`), and embedding models (`BAAI/bge-base-en-v1.5`, `BAAI/bge-large-en-v1.5`). This verifies the model inventory returned for the configured key, not that every documented API feature is enabled. The API reference documents the chat operation and Bearer-token authentication. [Imagine API reference](https://aisuite.cirrascale.com/imagine-api-docs)

## 4. API and configuration contract

- Base endpoint: `https://aisuite.cirrascale.com/apis/v2`
- Chat endpoint: `{base_endpoint}/chat/completions`
- Authentication: `Authorization: Bearer <key>`
- Initial model: `Llama-3.1-8B` for a compact explanation; compare another account-enabled LLM only if evaluation shows a quality need.
- Initial request: non-streaming chat completion, low temperature, bounded output tokens, explicit connect/read timeout.
- Expected response text: `choices[0].message.content`; handle absent or malformed choices as a service error.
- Available-model discovery: `{base_endpoint}/models`, performed manually or by a small diagnostic command, not on every app rerun.

The project already has the local ignored `.streamlit/secrets.toml` configured with `inference_cloud_api_key` and `inference_cloud_endpoint`. Read these in the server-side client using the existing optional-secret pattern. Never put the key in source, docs, logs, prompts, browser JavaScript, or user-visible errors. Do not copy the credential into this plan or commit it.

## 5. Work phases

### Phase 0 — Freeze the contract and confirm provenance

1. Confirm API use is allowed for the hackathon demonstration and that the configured key is the team's intended key.
2. Keep a small sample of the current `route_results` shape as a local, non-secret fixture for context-builder work.
3. Decide the initial explanation format: a brief summary, key trade-off, and data caveat.
4. Record that Imagine supplies narrative only; it is not the QUBO solver or the routing engine.

**Deliverable:** accepted data contract and prompt scope.

### Phase 1 — Add an isolated Imagine client

Create `imagine_client.py` with one narrow operation such as `explain_route(context, question=None, history=None)`.

Responsibilities:

- Read the configured key, endpoint, and model server-side.
- Normalize the endpoint and append `/chat/completions` exactly once; the configured endpoint already includes `/apis/v2`.
- Make an HTTPS POST with a Bearer token, JSON content type, `stream: false`, and a bounded timeout.
- Parse and return only assistant text plus safe request metadata (model, elapsed milliseconds, token counts if returned).
- Raise a small set of sanitized exceptions for missing configuration, timeout, authentication, rate limit, server error, and unexpected response shape.
- Never include the key, full request headers, or raw response body in exception text or UI output.

No new dependency is needed if the existing `requests` package is retained.

**Deliverable:** API adapter that can be disabled without affecting route calculation.

### Phase 2 — Build a whitelisted, grounded context

Create `assistant_context.py` to convert a successful `route_results` object into a small allowlisted dictionary. Do not pass the full result object through to the model.

Include only available, useful facts, for example:

- Selected origin/destination labels.
- Normal-route and R2I-route distance and travel time.
- Existing computed resource metrics and deltas (CO₂, fuel or energy, cost).
- Vehicle type, eco/time priority, and traffic scenario, if already stored in results.
- Route data source, traffic source/confidence/time, and optimizer/fallback metadata, if present.
- Existing caveats such as estimated emissions or unavailable local edge traffic data.

Exclude API keys, raw road-node IDs, full path coordinates, full graph data, unrelated session state, and personal information. Convert missing fields to an explicit `not_available` marker; do not substitute invented defaults. Keep numeric values from the result unchanged apart from display rounding.

**Deliverable:** deterministic, low-data assistant context with a route-result fixture.

### Phase 3 — Ground the assistant prompt and response

Use one system instruction that states:

- The assistant explains only the supplied current-trip facts.
- The route and metrics are computed by R2I; the assistant does not choose or change them.
- Do not calculate new savings, infer live conditions, or introduce outside facts.
- If evidence is absent or the question is outside the supplied trip context, state that clearly.
- Distinguish Google/normal baseline facts from R2I facts.
- Keep explanations concise and identify model-generated text as an explanation.

Send the current context as structured JSON within the user message, alongside the question. Do not enable model tools or external browsing. Treat user questions as untrusted content and do not let them override the system constraints.

For the first version, render plain text safely with Streamlit's standard text/markdown rendering (no `unsafe_allow_html`). Do not rely on undocumented JSON mode or model-specific structured output.

**Deliverable:** prompt and response contract with a small approved question set.

### Phase 4 — Add the assistant to the results UI

Make UI-only changes in `app.py`:

- Add an **AI route assistant** section only after route results exist.
- Offer an explicit **Explain this comparison** action and a follow-up question input.
- Display the active route pair near the assistant so the user knows which trip is in context.
- Identify the answer as AI-generated and retain the existing engine's comparison cards/map as the factual source of truth.
- Show a small loading state while inference is pending.
- Preserve the route results and map if the AI request fails.
- If the API key/model configuration is absent, hide or disable the action with a concise local explanation; routing remains available.

Avoid placing a chat call inside route optimization, `on_change` callbacks, or code that runs on every Streamlit rerun. Keep assistant history in a separate `st.session_state` key and reset it when the active route context changes. Limit retained history to the current route and a small number of recent turns.

**Deliverable:** opt-in explanation and question-answer experience independent of route search.

### Phase 5 — Failure handling, privacy, and operational controls

- Add a feature flag such as `R2I_AI_ASSISTANT_ENABLED`; default off when configuration is missing.
- Set a strict request timeout and initially avoid automatic retry loops. If a single bounded retry is later added, only retry transient failures and do not retry authentication or validation failures.
- On failure, show a local deterministic explanation based on existing metrics, or a clear “assistant unavailable” message. Never block map rendering or route results.
- Do not log prompts, user questions, keys, or raw provider bodies by default. If latency diagnostics are retained, store only timestamp, model, elapsed time, status class, and token counts.
- Send only the minimum trip summary needed for the response; disclose in the UI that a cloud inference request is made when the user asks for AI assistance.
- Provide a clear action to clear the current conversation.

**Deliverable:** safe no-AI fallback and bounded data handling.

### Phase 6 — Evaluate and prepare the demo

Use a fixed prompt set against saved route-result fixtures. Include:

1. Explain why R2I and the baseline differ.
2. Summarize the emissions/time trade-off.
3. Explain what the traffic scenario changed, only when those facts exist.
4. Ask for a metric not supplied; the assistant must say it is unavailable.
5. Ask for unrelated traffic advice; the assistant must remain scoped to the displayed trip.
6. Simulate no key, invalid key, timeout, rate limit, and malformed response.

Review responses against the fixture: every number must match the supplied data, and no generated answer may change route paths, engine metrics, or route selection. Measure median and p95 request latency for the chosen model and report the sample size. Do not make quality/speed claims from one run.

Demo sequence: select a trip → calculate the normal and R2I routes → inspect the computed trade-offs → request an AI explanation → ask one grounded follow-up → show that route results remain available if the assistant is disabled.

**Deliverable:** evaluation notes and a short demo script with an offline fallback.

## 6. File ownership and planned change surface

| File | Planned responsibility | Engine boundary |
|---|---|---|
| `imagine_client.py` (new) | API configuration, authenticated request, timeout, response/error parsing | Outside engine |
| `assistant_context.py` (new) | Whitelist current result facts for the model | Read-only adapter |
| `app.py` | Opt-in assistant controls and display only | UI/orchestration only |
| `.streamlit/secrets.toml` | Existing local key and endpoint configuration | Ignored local secret; never commit |
| `README.md` | Optional setup, privacy, model choice, and offline behavior | Documentation only |

No changes are planned for the protected engine, optimizer, traffic provider, route scoring, graph data, or benchmark logic.

## 7. Acceptance criteria

- Existing routing and benchmark outputs are unchanged with the assistant enabled or disabled.
- The assistant is called only after explicit user action.
- It receives only whitelisted current-trip fields and never receives the key or path coordinates.
- Every numeric statement in the answer is traceable to the supplied route result; unavailable facts are called out.
- Invalid credentials, network failure, and service errors do not break route results, metrics, or map rendering.
- The UI visibly distinguishes model-generated explanation from R2I-computed data.
- No credential or sensitive provider response is committed or printed.
- The exact selected model, API latency measurement method, and known limitations are documented for the demo.

## 8. Explicit non-goals

- Letting an LLM choose a route, alter an objective weight, or override a hard constraint.
- Calling the model during candidate generation, QUBO construction, route scoring, or benchmarking.
- Claiming that inference on Qualcomm AI100 is quantum computation or a quantum speedup.
- Using generated images as map tiles, traffic evidence, or route geometry.
- Building persistent user profiles, a general-purpose city chatbot, or a vector database for this MVP.
