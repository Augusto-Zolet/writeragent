### Mock LLM for sidebar soak

To chat without a real model (streaming HTML, scroll, tool loops, Stop, empty replies, errors), run a stdlib OpenAI-compatible stub:

```bash
make mock-llm
# or: .venv/bin/python scripts/mock_llm_server.py --delay-ms 30 --offline
# Soak Stop:     .venv/bin/python scripts/mock_llm_server.py --delay-ms 40 --scenario ramble
# Nested Stop (E8): --delay-ms 80 --sync-delay-ms 8000 (snappy SSE, long nested stream=False POSTs)
# Soak errors:   .venv/bin/python scripts/mock_llm_server.py --fail hang --fail-after-chunks 4
```

Default bind is **`http://127.0.0.1:18766`** (not `8765` / `18765`, which are MCP). In Settings: that endpoint, model `writeragent-mock`, Rich Text Control Sidebar on. **Record** sends native `input_audio` on chat completions; the mock replies with canned HTML (`Hello from the mock microphone.`, `--transcript` to change it). `GET /v1/models` advertises audio input and lists `writeragent-mock-whisper` for the STT combobox. `POST /v1/audio/transcriptions` (JSON or multipart) returns `{"text": …}` for the fallback path.

Plain “hello” streams two HTML paragraphs (rotating lists/tables/code). Phrases like “look up …” emit `web_research`; the same server scripts the smol `web_search` → `visit_webpage` → `final_answer` steps. `--offline` skips live DuckDuckGo (`final_answer` only). `--scenario` forces a journey on user turns; `--fail` fails every request. Phrase matching uses the last `### CURRENT QUERY:` suffix when librarian/smol wraps the task, so a recovery `hello` after `crash the stream` does not keep matching conversation history. Tests: `tests/scripts/test_mock_llm_server.py`.

**Phrase table** (case-insensitive; first match wins; missing tools fall back to HTML):

| Say… | What happens |
|------|----------------|
| `look up …` | `web_research` (then smol search loop) |
| `comment` | `add_comment` or empty-doc `apply_document_content` |
| `keep talking` / `ramble` / `stop me` | ~200 content chunks — hit **Stop**, then send again |
| `say nothing` / `empty reply` | no content, `finish_reason=length` → `[Response truncated -- the model ran out of tokens...]` (session stores that banner so a later empty turn is not HTML-rerendered as the previous reply) |
| `empty finish stop` / `blank stop reason` | no content, `finish_reason=stop` → `[No text from model…]` plus `[Debug: round=…, finish_reason='stop'…]` |
| `content filter` / `filtered reply` | no content, `finish_reason=content_filter` → `[Content filter: response was truncated.]` |
| `think out loud` | several `delta.reasoning` chunks, then HTML |
| `think tags` | XML think markers inside `content` |
| `reasoning details` | `reasoning_content` + `reasoning_details` then HTML |
| `fill the sidebar` / `very long` | 40 paragraphs + table + nested lists |
| `outline this` / `use the writer toolset` | `delegate_to_specialized_writer_toolset` (`document_research`) |
| `empty nested answer` | Same delegate; inner `final_answer` / `specialized_workflow_finished` with empty `answer` (E17) |
| `endless nested outline` | Same delegate; inner never finishes until `max_tool_rounds` (E22) |
| `mixed tools` / `one tool fails` | `add_comment` (empty search → error) + `apply_document_content` filler (E21) |
| `two tools` / `in parallel` | `search_in_document` + `get_document_tree` in one round |
| `insert filler` / `append a paragraph` | `apply_document_content` at end |
| `list sheets` / `list pages` | Calc/Draw list tools when advertised |
| `crash the stream` / `error 500` | HTTP 500 JSON error |
| `rate limit` / `error 429` | HTTP 429 |
| `error 401` / `unauthorized` | HTTP 401 |
| `error 403` / `forbidden` | HTTP 403 |
| `hang the stream` | a few SSE chunks, then the socket drops (no `[DONE]`) |
| `sse pings` | `: ping` comments between events (`--sse-comments` does this for every stream) |
| `event ping` | `event: ping` named SSE events between `data:` lines |
| `malformed sse` | `data: {not json}` then a valid stream + `[DONE]` |
| `truncated json` | incomplete `data: {` then valid stream + `[DONE]` |
| `two dones` | normal stream then two `data: [DONE]` lines |
| `empty body` | HTTP 200 with Content-Length 0 |
| `connection reset` | close socket before any status line |

Specialized inner HTTP (any request advertising `specialized_workflow_finished`, or `get_document_tree` plus `final_answer`) is scripted as document_research-shaped soak: one discovery tool (`get_document_tree` if advertised, else `list_nearby_files` / `search_nearby_files` / `grep_nearby_files`), then `specialized_workflow_finished` / `final_answer` with a canned outline. Never `delegate_read_document` with an empty path. Phrase “outline this” on that inner request must not fall through to the main-chat delegate scenario (which would emit HTML as the specialized `answer`).

Smolagents nested memory is Action JSON in user/assistant **content** (not `assistant.tool_calls`); the mock reads those Actions and `### CURRENT QUERY:` so online research is `web_search` → `visit_webpage` → `final_answer` instead of looping search. Later smol turns prefix `Step budget:` without the marker — scan earlier messages, do not treat the banner as the query.

### Mock LLM agent test plan

Hand these packets to separate agents. Each case is something **pytest cannot paint**: live SSE + the main-thread drain loop (`pump_ui_idle`) + real UNO (RichTextControl, tools, Record). Unit tests already cover `decide_completion` and HTTP envelopes in `tests/scripts/test_mock_llm_server.py`.

**Shared setup (every packet)**

1. `make mock-llm` (or `.venv/bin/python scripts/mock_llm_server.py` with flags noted per case). Bind `http://127.0.0.1:18766`.
2. WriterAgent Settings: that endpoint, model `writeragent-mock`, Rich Text Control Sidebar **on**. Dummy API key if Settings require one.
3. Fresh Writer document unless the case says Calc/Draw or empty doc.
4. Log: `writeragent_debug.log` next to `writeragent.json`. Optional: `RICH_SCROLL_VERBOSE_DEBUG = True` in `rich_text_control.py` for `[RICH-SCROLL]` lines.
5. Pass = UI behavior below **and** LibreOffice still accepts the **next** send (no stuck Stop, no frozen VCL).

Assign by packet id (`A`–`H`). Do not skip the “why hard” line — that is the reason the mock exists.

**v2 (scripted, no humans):** [Mock LLM tests v2](#mock-llm-tests-v2--scripted-b--c--d--e--f--g-audio) is the CI contract for Stop, empty/truncated, reasoning, tool-loop, HITL, HTTP/SSE, then **mocked Record**. Packets A (scroll/resize) and H (theme/exit) stay soak. v1 tables remain the human/agent checklist; v2 IDs are what `make test-mock-sidebar` should own.

#### Packet A — stream, HTML paste, scroll

*Hard: hidden-Writer copy after `STREAM_DONE`, VisArea, caret-follow, no `setFocus` steal. See scroll diagnostics above.*

| ID | Mock | Steps | Pass | Watch |
|----|------|-------|------|-------|
| A1 | default, send `hello` | Stream then formatted rerender | Plain stream first; after done, bold/lists as in rotating templates; query field keeps focus | `_copy_formatted_from_hidden_doc_to_control: ok`; no `phase=reveal_caret` on user insert |
| A2 | send 5–8 hellos | Fill transcript | Newest text visible; no jump to top on each send | `phase=user_append_done`; after `copy_done` expect trailing-break then Hidden scroll, not `reason=user_trailing_break` |
| A3 | `fill the sidebar` | One huge HTML message, then **resize** sidebar | Viewport stays on newest text; no H-scrollbar gutter | `phase=sync_bounds` then Hidden SelectAll, not `reason=resize` / `phase=reveal_caret` |
| A4 | rotating templates | Send until you see list, ordered list, table, `<pre>` | Table cells survive as tab-separated rows (first row bold+underline, not a grid); monospace `<pre>` survives paste | fallback WARNING lines absent |
| A5 | default | Click into the **Writer document** during stream, type | Keystrokes stay in the document, not the history control | no `setFocus` on stream append |
| A6 | default | Toggle rich setting off, restart, send hello; toggle on, restart | Plain path vs rich path; history reloads scrolled to bottom | `config rich_text_control_sidebar=` |

#### Packet B — Stop, drain loop, Send/Record FSM

*Hard: Stop while a worker holds the SSE socket; drain must exit; `SendButtonState` Record/Stop Rec/Send. Queue items are `StreamQueueKind`, not strings.*

| ID | Mock | Steps | Pass | Watch |
|----|------|-------|------|-------|
| B1 | `--delay-ms 40`, type `keep talking` (or `--scenario ramble`) | Click **Stop** while words still arrive | Stream stops; `[Stopped by user]` stays visible (do not replace the tail with `No response.`); button returns to Send/Record; **next hello works** | `Stop clicked` / `StopButtonListener: STOP_CLICKED` (action or `mousePressed`) in the log; drain is **not** inside Send `actionPerformed`; no second nested drain; query restore must not run after Stop pointer (`stream focus: left query`); skip rich rerender after Stop |
| B2 | ramble | Stop, immediately Send again | No double-stream, no stuck “Starting…” | `_active_q` cleared in tool-loop `finally`; reused `LlmClient` re-registers on the new send scope |
| B3 | ramble | Click Stop twice | Second click is a no-op, not a crash | |
| B4 | empty query box, venv configured | Record → Stop Rec without speaking long | Button Record ↔ Stop Rec ↔ Send; no send if truly empty and no wav | `SendEventKind.RECORD_CLICKED` / `STOP_REC_CLICKED` |
| B5 | ramble | Resize / click other sidebar widgets **during** stream | UI paints; Stop still works | drain owns `processEventsToIdle` |

**v2 scripted extras (B):** see [v2 Packet B](#v2-packet-b--stop-sendrecord-fsm). Not automated: **B5** (resize during stream). **B4** only if Record is invoked via `RECORD_CLICKED` without a real mic (optional wav fixture).

#### Packet C — empty / truncated model

*Hard: `format_empty_model_response_debug` is only visible on a real drain. Pytest never shows the banner.*

| ID | Mock | Steps | Pass | Watch |
|----|------|-------|------|-------|
| C1 | `say nothing` | Send | `[Response truncated -- the model ran out of tokens...]` (FSM `finish_reason=length` branch; **not** the Debug banner) | |
| C2 | C1 then `hello` | Recovery | Normal HTML chat; no stuck error state. v2: C1’s `_hello_ok()` | |
| C3 | `--scenario empty` | Several empty rounds | Truncated banner each time; transcript does not grow garbage HTML | |
| C4 | `empty finish stop` | Send | `[No text from model; any tool changes were still applied.]` plus `[Debug: round=…, finish_reason='stop'…]` | `format_empty_model_response_debug` on a real drain |

#### Packet D — reasoning vs content

*Hard: `[Thinking]` vs HTML paste race; field names in `stream_normalizer` (`llm-hacks.md`). Unit tests parse deltas; they do not paint the sidebar.*

| ID | Mock | Steps | Pass | Watch |
|----|------|-------|------|-------|
| D1 | `think out loud` | Send | `[Thinking]` appears **during** stream, then HTML after `STREAM_DONE`; thinking is **not** parsed as a tool call | `delta.reasoning` chunks |
| D2 | `think tags` | Send | In-content XML think markers handled; final HTML is the body, not raw tags in the rich control (or documented fallback) | content think markers |
| D3 | `reasoning details` | Send | `reasoning_content` / `reasoning_details` still show thinking then HTML | |
| D4 | D1 then tool phrase `look up cats` | Next turn | Reasoning from the previous turn is **not** stuffed into tool_calls | display-only reasoning |

#### Packet E — tool loop, nested agent, document refresh

*Hard: mutating UNO on the UI thread while the drain runs; nested smol HTTP; mid-loop `[DOCUMENT CONTENT]` refresh. Pytest mocks `LlmClient` and tools.*

| ID | Mock | Steps | Pass | Watch |
|----|------|-------|------|-------|
| E1 | `--offline`, `look up latest Python` | Web research | Status/thinking for search steps; final HTML summary in main chat; DuckDuckGo not required | smol `final_answer` uses `### CURRENT QUERY:` (not the “Step budget” banner); `_record_assistant_start` only on final report |
| E2 | omit `--offline`, same phrase | Live search optional | `web_search` once, then `visit_webpage` on a hit URL, then HTML wrap-up — not 15× search | smol Action JSON in content, not native `tool_calls` |
| E3 | Doc with text “Welcome…”, type `add a comment` | Comment tool | Comment anchored on first word; sidebar “Comment inserted” | `add_comment`; undo stack has the comment |
| E4 | **Empty** Writer doc, `insert a comment` | apply then comment | Text inserted at beginning, then comment on `Hello` | two-round tool loop; document context refresh |
| E5 | `insert filler` | Mutate end | Paragraph appended; **next** hello’s system prompt sees new length (not stale snapshot) | `apply_document_content`; `refresh_document_context` |
| E6 | `two tools` / `in parallel` | One send | `search_in_document` **and** `get_document_tree` run; one HTML wrap-up | `accumulate_delta` two `index` values |
| E7 | `outline this` | Delegate | Nested agent status while main drain stays alive; then main-chat HTML; Stop still works mid-delegate | `delegate_to_specialized_writer_toolset` domain `document_research`; inner discovery tool (often `list_nearby_files`, or `get_document_tree` when advertised) then `specialized_workflow_finished` (canned outline) — not main-chat HTML as the specialized `answer` |
| E8 | E7 + click Stop during nested work (`--delay-ms 80 --sync-delay-ms 8000` so inner `stream=False` POSTs stay clickable without a slow main SSE eating the window) | Cancel | Nested work stops; UI recovers; next hello works | `resolve_stop_checker()`, not a panel boolean alone |

**v2 scripted extras (E):** HITL Accept/Change/Reject on the same Send/Stop widgets, Calc `list sheets`, context refresh after mutate, Stop during tool round — [v2 Packet E](#v2-packet-e--tools-delegate-hitl).

#### Packet F — HTTP errors, hang, SSE quirks

*Hard: half-closed SSE under `processEventsToIdle`; error queue item vs freeze. Auth/HTTP errors are easy in pytest; hung sockets are not.*

| ID | Mock | Steps | Pass | Watch |
|----|------|-------|------|-------|
| F1 | `crash the stream` | Send, then `hello` | Error surfaced (not a hang); hello recovers | HTTP 500 JSON `error` object; match **current query** only, not librarian history |
| F2 | `rate limit` / `error 429` | Send | Distinct 429 handling or at least a visible error; recover with hello | `[API error: Rate limited (429)…]`; do not HTML-rerender the previous assistant over that line |
| F3 | `hang the stream` or `--fail hang --fail-after-chunks 4` | Send | UI does **not** freeze forever; Stop or timeout/error; next send works | socket half-close / no `[DONE]`; worker must not block VCL |
| F4 | `--sse-comments` or `sse pings` | hello | Stream still parses; comments ignored | `: ping` between `data:` lines |
| F5 | `--fail http500` for **all** requests | Open sidebar send | Consistent error path; Settings still usable | |
| F6 | F3 during ramble (`--scenario ramble --fail hang`) | Stop vs hang | Either Stop or error; never a wedged soffice | |

**v2 scripted extras (F):** 401/403, timeout, malformed SSE, `[DONE]` twice, recovery after each class of error — [v2 Packet F](#v2-packet-f--http-sse-errors).

#### Packet G — native audio and STT

*Hard: Record child + main-thread `STOP_REC` + `input_audio` on the next chat POST; history strips blobs; STT fallback when `has_native_audio` is False. See [audio-architecture.md](audio-architecture.md).*

Canned transcript default: `Hello from the mock microphone.` (`--transcript` to change).

| ID | Mock | Steps | Pass | Watch |
|----|------|-------|------|-------|
| G1 | default mock as **chat** model | Record ~1s (or silence) → Stop Rec | Native chat path (not `/audio/transcriptions`); HTML contains canned transcript and optional `~Ns` | `has_native_audio` is not False; `input_audio` in request; log “supports native audio” |
| G2 | G1 + type `hello` in the box while recording / before send | Typed text + audio | HTML echoes typed text **and** transcript | |
| G3 | G1 | After reply, inspect history / new session | No huge base64 in SQLite; `[Audio Attached]` or equivalent | `history_db.message_to_dict` strips `input_audio` |
| G4 | Silence auto-stop (Settings silence ms > 0) | Speak then pause | Auto-stop posts `STOP_REC` on **main thread**; same native reply as G1 | `auto_stopped` IPC; `execute_on_main_thread` |
| G5 | STT model `writeragent-mock-whisper`; force chat model **without** native audio (`audio_support_map` False, or a text-only id on the same endpoint if you add one) | Record | Fallback `POST /v1/audio/transcriptions` or chat “Transcribe this audio exactly…”; query becomes canned text then normal chat | `transcribe_audio`; multipart vs JSON |
| G6 | `--transcript Custom line.` | G1 | Sidebar shows **Custom line.** | |
| G7 | Record during an in-flight ramble | Should refuse or queue sanely | No two workers; button state consistent | |
| G8 | Missing venv / audio unsupported | Empty box | Record hidden or error from Test Python; Send still works for typed text | `SendButtonState.audio_supported` |

**v2 scripted extras (G):** fake WAV + Record/Stop Rec dispatch, no mic — [v2 Packet G](#v2-packet-g--mocked-audio-record--stt). After B/E/F.

#### Packet H — decks, session, recovery cross-cuts

*Hard: same drain + rich control on Calc/Draw; session switch mid-stream.*

| ID | Mock | Steps | Pass | Watch |
|----|------|-------|------|-------|
| H1 | Calc, `list sheets` | Open Calc sidebar, send | Tool runs if advertised; HTML wrap-up; resize still ok | `list_sheets` |
| H2 | Draw/Impress, `list pages` | Same | `list_pages` | |
| H3 | Writer A1–A3 in **Calc** and **Draw** decks | hello + fill the sidebar | Rich control exists; scroll/resize; no plain field stuck visible | `on_rich_control_ready` |
| H4 | Mid-ramble, switch document / close doc | | Error or clean abort; no `DisposedException` swallowed into a freeze | `is_disposed_exception` / `DocumentDisposedError` |
| H5 | Clear transcript / new chat, then hello | | History batch paste; scroll at bottom | `append_rich_messages_via_clipboard` |
| H6 | Light/dark theme switch with a long flood transcript | | Readable; no leftover inverse selection | |
| H7 | Exit LO during ramble | | No worse crash than plain path (nested hidden Writer) | |

**Out of scope for this mock** (do not assign): real ASR quality, librarian/brainstorming/ppt-master modes, image gen, MCP clients, `=PROMPT()` cells.

**Suggested split:** one agent per packet; A+D can share a Writer window; G needs a mic/venv; E needs a named Writer doc; F should not share a soffice with A (error/hang).

---

## Mock LLM tests v2 — scripted B / C / D / E / F (+ G audio)

**Goal:** every case below runs in **`testing_runner` / `make test-uno`** (or a dedicated `make test-mock-sidebar` that is still no-human). No eyeballs, no resize, no “does the viewport look right.” Pass = logs + control/query text + UNO document + **SendButtonState** (or button labels) + **next hello succeeds**.

**Why B/E/F first:** Stop, drain, tools, HITL. Packet A scroll/resize and Packet H theme/exit stay soak. **Packets C and D are landed** on the same harness (`FILTER=C` / `FILTER=D`).

**Packet G (mocked audio) is next after B/E/F is boring** — lower priority only because manual Record feels fine, but it is a **second FSM** (`AudioRecorderState`: idle → initializing → recording → stopping) stacked on Send/Stop Rec/Send. That stack has acted up (busy vs recording, Stop vs Stop Rec, Record during ramble). Script it with a **fake capture child** (no mic, no `sounddevice`). The mock LLM already accepts `input_audio` and `/v1/audio/transcriptions`.

Optional WAV fixture: a few hundred ms of tone (or zeros) plus trailing silence so auto-stop / duration (`~Ns`) can be real bytes on the wire. The **words** in the reply stay canned (`--transcript`); nobody is scoring ASR.

### Harness (brief)

One native test module (e.g. `tests/chatbot/test_mock_llm_sidebar_uno.py`). Shared setup:

1. Start mock in-process (`make_handler_class` + `ThreadingHTTPServer` on 18766 or an ephemeral port).
2. Point `endpoint` / `text_model` at `writeragent-mock` for this LO user profile (test helper; restore after).
3. Open Writer (or Calc when the case says so), **open the chat sidebar** so wiring created `SendButtonListener`.
4. Hooks below; `toolkit.processEventsToIdle()` (or existing drain helper) between steps.
5. Teardown: Stop if busy, shut mock, restore config.

Run serial (`testing_runner`); do not xdist a live soffice + one mock port.

### Hooks (shipped, debug / non-release only)

Do **not** synthesize screen clicks. Drive the same listeners the widgets use.

**Code:** [`plugin/chatbot/sidebar_test_hooks.py`](../../plugin/chatbot/sidebar_test_hooks.py) (dev trees and ``make build`` / ``make deploy`` only). Live panels: debug-only `WeakSet` in [`panel_factory.py`](../../plugin/chatbot/panel_factory.py) (`register_debug_live_panel`, gated on full `thread_guard`) plus the hooks module set. HITL Change in tests uses existing `_finish_inline_web_approval`. In-process mock: [`tests/chatbot/mock_llm_harness.py`](../../tests/chatbot/mock_llm_harness.py).

**Release:** the hook file is **omitted** (`should_exclude` on ``--no-tests``, and `omit_sidebar_test_hooks` deletes it from stripped trees). There is no stub with `press_send`. LibrePy does not ship this module. Unit tests: [`tests/chatbot/test_sidebar_test_hooks.py`](../../tests/chatbot/test_sidebar_test_hooks.py).

| Hook | Does | Used for |
|------|------|----------|
| `sidebar_panel()` / `send_listener()` | Live `SendButtonListener` after deck init | Everything |
| `set_query_text(s)` | Query model `Text = s` + `TEXT_UPDATED` | All sends |
| `press_send()` | `dispatch(SEND_CLICKED)` or Send `on_action_performed` with Label Send | Start stream |
| `press_stop()` | `dispatch(STOP_CLICKED)` | Cancel (Windows/ActionEvent path) |
| `press_stop_mouse()` | `notify_stop_mouse_pressed(send_listener)` | GTK path (Packet B1) |
| `pump_until(pred, timeout)` | Idle-pump until log/UI predicate | “while ramble chunks arrive” |
| `transcript_contains(s)` / `query_text()` | Rich or plain response + query box | Stopped banner, errors, recovery |
| `send_state()` | `is_busy`, labels Send/Stop/Record/Accept/Change/Reject | FSM |
| `wait_idle()` | `is_busy is False` and not recording | Between cases |
| `next_hello_ok()` | set `hello`, send, wait idle, assistant HTML or plain “hello” path | **Required closer on almost every case** |
| `mock_config(**flags)` | ramble delay, `sync_delay_ms`, `--offline`, `--fail hang` | B/E8/F |
| `press_record()` | `dispatch(RECORD_CLICKED)` or URP `chatbot.debug_sidebar.RECORD_CLICKED` | G — start capture (label-independent) |
| `press_stop_rec()` | `dispatch(STOP_REC_CLICKED)` | G — stop capture (not `STOP_CLICKED`) |
| `inject_wav(path or bytes)` | Skip venv/PortAudio; host sees a finished temp WAV as if the child wrote it | G native + STT |
| `stub_recorder_child()` | Fake IPC: `{"status":"ready"}` then stop/exit without a device | G initializing vs recording |
| `set_audio_supported(bool)` | Force `SendButtonState.audio_supported` / `audio_support_map` | G8, STT fallback |
| `audio_status()` | `AudioRecorderState.status` + `has_audio` | G illegal combos |

HITL (same two buttons, different labels):

| Hook | Does |
|------|------|
| `press_accept()` | Send `on_action_performed` while Label is Accept |
| `press_change()` / `press_reject()` | Stop listener Change/Reject branches — **must not** be `STOP_CLICKED` |
| `approval_active()` | `_approval_event is not None` |

Optional later: `press_record()` / `press_stop_rec()` (`RECORD_CLICKED` / `STOP_REC_CLICKED`) without opening a device.

**Invariant:** `press_stop_mouse()` while `approval_active()` is a no-op (see `notify_stop_mouse_pressed`). Tests must cover that.

### Pass / fail (every v2 case)

- LibreOffice still alive; no nested drain (`NestedDrainOwnerError` absent).
- After terminal state: `is_busy is False`; Send enabled for typed text.
- `next_hello_ok()` unless the case is “second Stop is no-op” (then hello after).
- Queue kinds in logs are `StreamQueueKind` names, not ad-hoc strings (if logged).

### Out of v2 (do not script)

Resize sidebar, H-scrollbar, “click into Writer during stream,” light/dark, LO exit during ramble, real microphone ASR, MCP, `=PROMPT()`, brainstorming UI, image gen, VisArea/scroll-to-bottom as a visual check.

---

### v2 Packet B — Stop, Send/Record FSM

**Live URP (`make test-mock-sidebar FILTER=B`):** **OK:** B1a, B1c, B2, B3, B3b, B6, B7, B9, B10, B11, B14, B15, **B16, B19, B21**. **SKIP:** B1b (mouse / in-process), B4/B12 (Record → Packet G), B5 (resize soak), **B8** (harness: URP `Text=` does not fire `TEXT_UPDATED`; needs sync hook — not product). **Product fix landed:** **B13** — `LlmClient.stop()` latches `_stopped` so Stop before the first socket cannot reconnect and hold `llm_request_lane`. Full-suite Calc **E12** still kills URP; stay off Calc from Packet B.

Mock: `--delay-ms 40` (and ramble phrases) unless noted. Tests: [`tests/chatbot/test_mock_llm_sidebar_uno.py`](../../tests/chatbot/test_mock_llm_sidebar_uno.py) (`test_b*`).

#### Scratchpad — B8 / B13 (2026-08-29)

**B13 (product — done):** Stop before/during early SSE closed the sock, but `streaming_loop` kept reading and `finally: response.read()` blocked ~`request_timeout`, holding `llm_request_lane`. Fix: latch `_stopped`, `break` on Stop (not `continue`), skip body drain when stopped, late `register_client` after cancel calls `stop()`, UI `clear_stop()` on next send. Verify: `FILTER=b13` then `FILTER=B`.

**B8 (skipped — harness):** `test_b8_send_enabled_only_with_text` skipped. URP `set_query_text_via_controls` does not dispatch `TEXT_UPDATED`; leftover `has_text` / Record stays Enabled. Do not disable Record on empty. Harness needs a `TEXT_UPDATED` sync later; B7 already covers empty click must not POST.

**How to reproduce:**

```bash
make test-mock-sidebar FILTER=B
make test-mock-sidebar FILTER=b13
```

Out-of-process: live `SendButtonListener` is in soffice. Tests drive `uno_click` + Stop `Enabled` + transcript. `send_listener()` is usually `None`. Do **not** `processEventsToIdle` on the URP pipe.

**What already works (do not regress):** Stop **after** at least one SSE chunk (`keep talking`, `delay_ms=40`) → `[Stopped by user]`, not `No response.`, no full ramble HTML wipe, next hello works, double Stop, Stop while idle, natural ramble end then Stop on a second ramble, serial hello→ramble+Stop→empty→hello. Mock `BrokenPipeError` on Stop while writing SSE is **expected** (client closed the socket); B1a still OK.

---

**Not this packet (leave for later):**

- **E12 Calc** on the **full** suite: `list sheets` then `DisposedException: Binary URP bridge already disposed`. Isolate with `FILTER=e12` after B is green; do not open Calc from Packet B.
- **E9 HITL:** `Accept` never appeared over URP. Separate from B.
- Root MP3s `hello-writeragent-1s.mp3` / `hello-writeragent-5s.mp3` are **Packet G**, not B.

| ID | Drive | Pass (assert) |
|----|--------|----------------|
| **B1a** | `keep talking`; pump until ≥1 chunk; `press_stop()` | Log `Stop clicked` or `STOP_CLICKED`; transcript has `[Stopped by user]`; **not** replaced by `No response.`; `is_busy` becomes false; `next_hello_ok()` |
| **B1b** | Same; cancel with `press_stop_mouse()` only | Same as B1a (GTK path). Log `STOP_CLICKED (mousePressed)` |
| **B1c** | B1a; after Stop, rich tail not re-pasted as full HTML of the ramble | No `_copy_formatted…` success **after** stop for that turn (or skip-rerender log) |
| **B2** | Stop then `press_send()` immediately (`hello` or ramble) | One in-flight send; no stuck Starting…; `_active_q` not dual-owned; `next_hello_ok()` if second was ramble+stop+hello |
| **B3** | Ramble; `press_stop()` twice quickly | Second is no-op (log at most one cancel scope or second `STOP_CLICKED` with `not is_busy` ignored); no exception; hello |
| **B3b** | `press_stop()` when **idle** | No crash; labels unchanged; Send still works |
| **B6** | `press_send()` twice without waiting (double Send) | FSM rejects second (`is_busy`); one stream; hello after done or after stop |
| **B7** | Send with **empty** query, no audio | No `StartSendEffect` / no HTTP to mock (mock request count 0) |
| **B8** | TEXT_UPDATED empty ↔ nonempty | **SKIP** — harness needs `TEXT_UPDATED` sync over URP |
| **B9** | Ramble until **natural end** (no Stop); wait idle | Button Send; then Stop during a **second** ramble still works (no stale cancel scope) |
| **B10** | Stop; `next_hello_ok()`; ramble+Stop again | Cancel works twice in one panel lifetime |
| **B11** | Stop; assert query box text restored or left as designed; `stream focus: left query` if Stop pointer path | No focus restore **after** Stop that would steal the next Send |
| **B12** | Record hooks if cheap: empty box `RECORD_CLICKED` then `STOP_REC_CLICKED` with no wav | Returns to Send; no chat POST; typed hello still works. **Skip** if Record needs a real device |
| **B13** | `press_send()` then Stop **before** first SSE chunk (`delay-ms` high) | Cancelled starting state; not stuck Stop; hello; **no** `LLM request lane lock` in transcript |
| **B14** | Stop during `[Thinking]`-style ramble (`think out loud` + delay) | Thinking cleared or frozen; Stopped banner or idle; hello |
| **B15** | Serial: hello (complete) → ramble+Stop → `say nothing` → hello | Four terminals; never stuck busy |
| **B16** | `add_comment` **tool_calls only** (no content), `delay_ms` high; Stop **before** the tool runs | Comment never appears; `is_busy` false; hello |
| **B19** | Two **sequential** tool rounds (not E6 parallel); Stop after first tool result (`insert a comment` on empty doc) | Second tool never runs; idle; hello |
| **B21** | Clear during ramble (`uno_click` on `controls["clear"]`) | Greeting visible; Stop still enabled; press Stop; idle; hello |

#### Dropped (do not re-add)

- **B17** — `STREAM_DONE` vs click in the same window is not deterministic over URP. B1a (mid-stream) and B9 (natural end) already bracket it
- **B18** — Stop ×5 is soak. B10 already cancels twice in one panel lifetime
- **B20** — Stop during `UpdateDocumentContext` is not observable over URP; E5 already proves refresh
- **B22** — folded into B21 (Clear after Stop is the same recovery)
- **B23** — after `STREAM_DONE` the FSM is often already idle (B3b). Rerender timing is Packet A soak

---

### v2 Packet C — empty / truncated model

**Landed:** C1, C3, C4, **C5** in [`tests/chatbot/test_mock_llm_sidebar_uno.py`](../../tests/chatbot/test_mock_llm_sidebar_uno.py) (`make test-mock-sidebar FILTER=C`). **C2** is C1’s `_hello_ok()` (not a separate function). B15 still sends `say nothing` without asserting the banner.

Empty / truncated STREAM_DONE must **AddMessageEffect** the banner ([`tool_loop_state.py`](../../plugin/chatbot/tool_loop_state.py)) so finalize does not paste the previous HTML assistant over the new turn (C3 after hello used to show leftover Mock notes).

| ID | Drive | Pass (assert) |
|----|--------|----------------|
| **C1** | `say nothing` | Suffix has `[Response truncated -- the model ran out of tokens...]`; **not** `[No text from model]`; `_hello_ok()` |
| **C3** | `_session.config.scenario = "empty"`; send `round one` / `round two` / `round three`; restore `scenario=none` | Truncated banner each round; no rotating hello HTML (`<ul>`, `print('mock-llm')`); hello after restore |
| **C4** | `empty finish stop` | `[No text from model; any tool changes were still applied.]` plus `[Debug:` with `finish_reason='stop'`; hello |
| **C5** | `content filter` / `filtered reply` → `finish_reason=content_filter` | `[Content filter: response was truncated.]`; **not** the length or Debug banners; hello |

---

### v2 Packet D — reasoning vs content

**Landed:** D1–D4 (`make test-mock-sidebar FILTER=D`). B14 **Stops during** `think out loud`; D1 lets the stream **finish**. Mid-stream `[Thinking]` must be polled while Stop is Enabled: HTML rerender replaces the assistant tail so the prefix is usually gone after idle. `chatbot.show_search_thinking` (default false) gates tool thinking only; main-chat `delta.reasoning` still paints.

| ID | Drive | Pass (assert) |
|----|--------|----------------|
| **D1** | `think out loud`, `delay_ms=80`; poll `[Thinking]` while busy; wait idle | Saw `[Thinking]` during stream; after idle, mock HTML body; think-turn `decided_tools == []`; hello |
| **D2** | `think tags` | After idle: no `<think` / `</think>` in transcript; HTML body present (tags in `content` are the [`llm-hacks.md`](llm-hacks.md) gap — do not require `[Thinking]`); hello |
| **D3** | `reasoning details` (same poll as D1) | Mid-stream `[Thinking]`; after idle HTML; `decided_tools == []`; hello |
| **D4** | D1-style think to idle, then `look up cats` (`--offline`) | Look-up user-turn capture: `last_assistant_tool_calls == []`; no junk history tool names; research `decided_tools`; hello |

---

### v2 Packet E — tools, delegate, HITL

**Landed:** E1, E3–E8a, E9a–c/e, E10–E11, E13–E15, **E17, E21, E22** in [`tests/chatbot/test_mock_llm_sidebar_uno.py`](../../tests/chatbot/test_mock_llm_sidebar_uno.py) (`make test-mock-sidebar`). **Skipped:** E2 (live DDG), E8b/E9d (`press_stop_mouse` / in-process listener, same as F3b), **E12** (full-suite Calc hangs URP — isolate `FILTER=e12`), E9c unless the live listener is in-process.

Writer with body text “Welcome to WriterAgent.” unless **empty** is specified. Mock `--offline` for research unless E2. Setup turns `chatbot.prompt_for_web_research` **off** except E9. Mock request captures live on `MockLLMConfig.captures`.

| ID | Drive | Pass (assert) |
|----|--------|----------------|
| **E1** | `--offline`, `look up latest Python` | `web_research` or smol `final_answer`; HTML summary in transcript; mock saw `### CURRENT QUERY:`; hello |
| **E2** | Online research optional; if run: `look up …` | At most one `web_search` then `visit_webpage` then wrap-up (mock request log); hello. **Skip in CI** if you do not want live DDG (`--offline` only on Jenkins) |
| **E3** | Doc has Welcome…; `add a comment` | ≥1 comment on doc; log `add_comment`; sidebar mentions comment; hello |
| **E4** | **Empty** doc; `insert a comment` | `apply_document_content` then comment; doc nonempty; hello |
| **E5** | `insert filler` | Doc longer; **next** mock capture of chat POST system/user includes new length (`refresh_document_context`); hello is extra |
| **E6** | `two tools` / `in parallel` | Both `search_in_document` and `get_document_tree` executed (tool log or mock `tool` messages); one wrap-up; hello |
| **E7** | `outline this` | `delegate_to_specialized_writer_toolset`; inner discovery **not** empty-path `delegate_read_document`; `specialized_workflow_finished` or inner `final_answer`; main transcript HTML outline; hello |
| **E8a** | E7 + `--delay-ms 80 --sync-delay-ms 8000`; `press_stop()` during nested POST | Nested stops; `is_busy` false; hello. Log `resolve_stop_checker` / cancel, not only a panel flag |
| **E8b** | Same with `press_stop_mouse()` | Same as E8a |
| **E9** | HITL: phrase that opens web-search **approval** (mock `web_research` + host waits). Wait `approval_active()` | Send label Accept; Stop label Change or Reject (i18n `_()`); `is_busy` still true |
| **E9a** | E9 then `press_accept()` | Approval clears; search/tools continue or finish; labels Send/Stop; hello |
| **E9b** | E9 then `press_reject()` | Approval clears; search not applied (or aborted); idle; hello |
| **E9c** | E9 then `press_change()` | Change dialog path **or** hook that applies edited query if dialog is too heavy; must **not** log ramble `STOP_CLICKED` as cancel-stream; hello or continued search |
| **E9d** | E9 then `press_stop_mouse()` | **No** stream cancel; still `approval_active()` |
| **E9e** | E9 then `press_stop()` ActionEvent | Change/Reject branch, not `StopSendEffect` |
| **E10** | Tool error: mock tool-follow-up that returns 500 mid-loop | Error in transcript; not busy; hello |
| **E11** | `insert filler` then `add a comment` as **two sends** | Both mutations present; context refresh between |
| **E12** | Calc doc + `list sheets` | **SKIP** on full suite (URP hang after `scalc`). Isolate `FILTER=e12` later |
| **E13** | Stop **during** `add_comment` round (delay tools via mock) | Partial or no comment; not busy; hello; no freeze |
| **E14** | Delegate E7 completes; second `outline this` | Nested agent works twice (no stale inner session) |
| **E15** | `insert filler` with Stop **after** tool result queued but before HTML wrap-up | Doc may have mutation; UI idle; hello; no double drain |
| **E17** | Nested `final_answer` empty / `None` (`empty nested answer`) | Main wrap-up or clean empty banner; **no** leftover previous HTML (C3 analog for delegate); hello |
| **E21** | `mixed tools` / `one tool fails` — apply filler succeeds, `add_comment` empty search errors | Partial wrap-up; error surfaced, successful mutation kept; not the whole round dropped; hello. Distinct from E6 (both ok) and E10 (follow-up HTTP 500) |
| **E22** | Nested agent never emits `final_answer` (`endless nested outline` + `nested_never_finish`) | Budget-exhausted error, not an infinite loop; main UI idle; hello. Nested analog of F3 |

#### Next-level (not landed)

Same filter as Packet B. Unknown-domain / `VALIDATION_ERROR` / shrink-refresh are pytest ([`test_tool.py`](../../tests/framework/test_tool.py), [`test_tool_loop_state.py`](../../tests/chatbot/test_tool_loop_state.py), E5). Do not close the Writer doc under this suite.

**Dropped (do not re-add):**

- **E16** — unknown domain already `_tool_error`s when `domain_tools` is empty; same UI as E10
- **E18** — zero search hits is tool content, not a drain hang
- **E19** — `tool.validate` / `VALIDATION_ERROR` is pytest
- **E20** — close doc mid-tool kills the **shared** soffice; that is H4 soak
- **E23** — shorter-doc refresh is the same `refresh_document_context` path as E5
- **E24** — same in-process hole as skipped E9c; do not list as “assume harness exists”

---

### v2 Packet F — HTTP / SSE errors

**Landed:** F1–F18 except **F11 / F18 SKIP** (2026-08-29 full suite: transcript `wait_for="mock"` failed; F3b skipped over URP) in [`tests/chatbot/test_mock_llm_sidebar_uno.py`](../../tests/chatbot/test_mock_llm_sidebar_uno.py). Run **`make test-mock-sidebar`** (not `make test-uno`). Visible soffice with **your** LibreOffice user profile:

**Filter (skip long packets while debugging):** definition order is F → B → C → D → E → G. Pass `FILTER=` to the Make target (forwarded to `testing_runner`):

```bash
make test-mock-sidebar                 # all packets
make test-mock-sidebar FILTER=G        # packet G (mocked audio)
make test-mock-sidebar FILTER=C        # empty / truncated banners
make test-mock-sidebar FILTER=D        # reasoning vs content
make test-mock-sidebar FILTER=B
make test-mock-sidebar FILTER=f3a      # one case id
make test-mock-sidebar FILTER=test_e7_outline_delegate
make test-mock-sidebar FILTER="B E"    # two packets
```

Shared `@setup` (mock + sidebar) still runs once; only non-matching `@native_test` functions are skipped. A filter that matches nothing fails the suite (exit non-zero).

- **Bootstrap:** Popen ``--norestore --writer --accept=socket,host=127.0.0.1,port=<ephemeral>;urp;`` like ``make lo-start`` (TCP, not a named pipe). Do **not** use ``officehelper.bootstrap`` (it appends ``--nodefault`` and the GUI crashed / URP disposed). Child env strips ``PYTHONPATH`` so the OXT is not mixed with the checkout. A leftover ``.lock`` with ``IPCServer=false`` is removed when no ``soffice.bin`` is running so ``--accept`` binds (OSL pipes under ``tempfile.gettempdir()``, not a hardcoded ``/tmp``).
- **Crash recovery:** ``--norestore`` skips the recovery dialog that otherwise blocks the UNO pipe.
- **View → Sidebar off:** tests dispatch ``.uno:SidebarDeck.WriterAgentDeck`` (shows the sidebar; ``.uno:Sidebar`` *toggles*). Do **not** dispatch ``SidebarDeck.WriterAgentDeck`` when ``XSidebarProvider.isVisible()`` is already true — that command is OpenThenToggleDeck and would hide the sidebar; use ``showDecks`` / ``XDeck.activate`` instead. Decks come from ``controller.Sidebar`` (``XSidebarProvider.getDecks`` on SwXTextView). The soffice child sets ``WRITERAGENT_UNO_THREAD_GUARD=0`` so URP deck dispatch can create ChatPanel (otherwise ``getRealInterface`` aborts on Dummy-N).
- **Out-of-process UNO:** the live ``SendButtonListener`` lives in soffice. Drive query/send/stop over URP (``uno_click``); poll Stop ``Enabled`` and transcript text. Do not ``processEventsToIdle`` on the pipe.
- **F3b skipped:** ``press_stop_mouse()`` needs an in-process listener; URP only has ActionEvent (covered by **F17** Stop during hang).

Harness: [`tests/chatbot/mock_llm_harness.py`](../../tests/chatbot/mock_llm_harness.py). Hooks: [`plugin/chatbot/sidebar_test_hooks.py`](../../plugin/chatbot/sidebar_test_hooks.py). Other UNO tests stay `make test-uno` (headless + throwaway profile).

Each case ends with **`next_hello_ok()`** unless noted. Prefer phrase triggers so default mock stays up; use `--fail` only for “all requests” cases (then restart mock or toggle fail off before hello).

| ID | Drive | Pass (assert) |
|----|--------|----------------|
| **F1** | `crash the stream` | Visible API/error text; not hang; hello. Mock 500 body; current-query match only |
| **F2** | `rate limit` / `error 429` | Distinct 429 string or generic error; **do not** HTML-rerender prior assistant over the error line; hello |
| **F3a** | `hang the stream` or `--fail hang --fail-after-chunks 4`; wait timeout **or** `press_stop()` | Idle; error or Stopped; hello. Worker must not block: pump still runs during hang |
| **F3b** | Hang then `press_stop_mouse()` | Same |
| **F4** | `sse pings` / `--sse-comments` + `hello` | Completes; HTML or stream text present; no parse crash |
| **F5** | `--fail http500` all requests; send hello | Error path; then **disable fail** (or new mock); hello succeeds |
| **F6** | Ramble + hang (`--scenario ramble --fail hang`) | Stop or error; never wedged; hello after mock reset if needed |
| **F7** | `error 401` / unauthorized (add phrase or mock status) | Auth-style message; hello after |
| **F8** | `error 403` | Same family as F7 |
| **F9** | Malformed SSE (`data: {not json}` then hang/done) | Error or skip chunk; idle; hello |
| **F10** | Truncated JSON chunk then `[DONE]` | Error or partial; idle; hello |
| **F11** | Two `[DONE]` lines | **SKIP** on full suite 2026-08-29 (`wait_for="mock"` failed). Isolate `FILTER=f11` |

| **F12** | HTTP 200 empty body | Empty-model or error banner; hello |
| **F13** | Connection reset on first byte | Error; hello |
| **F14** | 429 then immediately hello (mock not failing) | Recovery; no sticky 429 state |
| **F15** | F1 (500) then F2 (429) then hello | Both errors visible in history or last+hello; not busy |
| **F16** | Timeout: mock `delay-ms` > client timeout if configurable | ERROR_OCCURRED; Send enabled; hello |
| **F17** | Stop **during** F3 hang | Same as B1 vs hang; idle |
| **F18** | SSE `event: ping` / unknown event types if mock can emit | **SKIP** on full suite 2026-08-29 (transcript / BrokenPipe). Isolate `FILTER=f18` |

#### Next-level (not landed)

**None in this suite.** Packet F is landed (F1–F18). Further HTTP/SSE envelopes (redirect, 204, Content-Length, fragmented SSE, BOM, missing `finish_reason`, charset, non-UTF8, keep-alive, 503, `Retry-After`) belong in [`tests/framework/test_client_llm.py`](../../tests/framework/test_client_llm.py) / [`tests/scripts/test_mock_llm_server.py`](../../tests/scripts/test_mock_llm_server.py), not `test_mock_llm_sidebar_uno.py`.

F20 ≈ F12; F28/F31 ≈ F3; F30 ≈ F1; F26 is Packet A (`fill the sidebar`). The product does **not** sleep the UI thread on `Retry-After`. The empty-model `content_filter` banner is **C5**, not an F row.

**Dropped IDs (do not re-add):** F19–F32.

---

### v2 Packet G — mocked audio (Record / Stop Rec / STT)

**Landed (`make test-mock-sidebar FILTER=G`, after `make deploy`):** G1–G16, **G29** pass. **SKIP:** G17 (Calc / E12), G18 if HITL Accept never appears (same as E9). Record/Stop Rec use the Send widget when the label matches; if Record click is a no-op, fall back to `org.extension.writeragent:chatbot.debug_sidebar?OP` (Query string; LO drops dotted Path suffixes). Handler **posts** onto VCL (`set_force_marshal_mode`) — blocking `execute()` from URP deadlocks. Stub JSON is replaced each `_g_prep` so G4 `auto_stop` / G12 `fail_start` cannot leak.

Same harness as B/E/F. **Do not** open a microphone: `stub_recorder_child()` + `inject_wav()` write `/tmp/writeragent_stub_recorder.json` so the soffice OXT skips spawn (`AudioRecorder._test_skip_spawn`). Fixtures: `tests/chatbot/fixtures/hello-writeragent-1s.wav` (G1) and `hello-writeragent-5s.wav` (G4); source MP3s at repo root. Mock LLM: `writeragent-mock` native `input_audio`; `writeragent-mock-whisper` for `/v1/audio/transcriptions`.

Two machines must stay legal (`send_state.py`: never `is_busy and is_recording`):

- **Send:** idle → Record (label Record) → recording (Stop Rec) → stop rec (often `is_busy` while sending audio) → idle Send.
- **Recorder:** idle → initializing → recording → stopping → idle | error.

| ID | Drive | Pass (assert) |
|----|--------|----------------|
| **G1** | `audio_supported`; empty query; `press_record()`; stub `ready`; `press_stop_rec()`; inject canned WAV; wait idle | Native chat POST has `input_audio` (not whisper URL unless fallback); transcript contains mock line (`Hello from the mock microphone.` or `--transcript`); `has_audio` cleared after send; hello |
| **G2** | Type `hello` in query **then** Record → Stop Rec | Reply mentions typed **and** transcript |
| **G3** | G1 then inspect last history row (SQLite/JSON) | No huge base64; placeholder like `[Audio Attached]` |
| **G4** | Record; fire host **silence auto-stop** as `STOP_REC_CLICKED` on main thread (do not sleep for real silence) | Same native reply as G1; log auto-stop / `execute_on_main_thread` |
| **G5** | `set_audio_supported` native **False**; chat model text-only; Record → Stop Rec | `POST /v1/audio/transcriptions` **or** chat “Transcribe this audio exactly…”; query becomes canned text; then normal completion |
| **G6** | Mock `--transcript Custom line.` | G1 sidebar contains **Custom line.** |
| **G7** | Ramble in flight; `press_record()` | Rejected (`is_busy`); still ramble; Stop still works; no second worker |
| **G8** | `audio_supported=False`; empty box | Record not enabled; typed Send hello works |
| **G9** | `press_record()` twice | Second no-op; still recording; one child stub |
| **G10** | `press_stop_rec()` while **idle** | No crash; still Send |
| **G11** | Record; `press_stop()` (send-cancel), **not** Stop Rec | Must not treat as Stop Rec **or** must stop both cleanly; not `is_busy and is_recording`; hello |
| **G12** | Record; fail stub (`ErrorOccurredEvent` / child crash) | `audio_status` error then idle; Send works; no stuck Stop Rec |
| **G13** | Record; Stop Rec; **fail** chat POST (500) | Error in transcript; `has_audio` not stuck forever (can Record again); hello |
| **G14** | Stop Rec with **empty/missing WAV** | No send or explicit error; not busy; hello |
| **G15** | `press_send()` while `is_recording` | FSM ignores Send; still recording; Stop Rec then send works |
| **G16** | Record → Stop Rec → immediately Record again | Second take replaces audio; one in-flight capture |
| **G17** | G1 on **Calc** deck if sidebar exists | Same native path; hello |
| **G18** | HITL active; `press_record()` | No Record (approval owns buttons); E9 still valid |
| **G29** | Native chat POST with `input_audio` returns **400** (`fail_native_audio`); STT then succeeds **on the same drain** | Transcript shows `[Model does not support audio. Falling back to STT...]`; no nested drain (`_handle_stream_error` must not re-enter `_do_send`); hello. Distinct from G5 (which pre-sets `audio_supported=False`) |

#### Next-level (not landed)

IPC JSON parse and VAD child lines are pytest ([`test_audio_silence_detector.py`](../../tests/scripting/test_audio_silence_detector.py)). G4 already fires the same host `_notify_auto_stop` path. Do not add file-write races over URP.

| ID | Drive | Pass (assert) |
|----|--------|----------------|
| **G21** | Stub **never `ready`** (`hang_ready`; existing `wait_for_recording_ready` timeout). Distinct from G12 `fail_start` | Init timeout; `audio_status` error; not stuck initializing; Send still works. No mic |
| **G27** | STT returns **empty text** (WAV exists; not G14 missing file) | Query stays empty; no send; idle; hello |
| **G28** | STT returns **error JSON** (G5’s error cousin) | Error surfaced; `has_audio` cleared; hello |

**Dropped (do not re-add):**

- **G19** — G4 already is host auto-stop; child `auto_stopped` JSON is pytest
- **G20** — garbage IPC line is parser pytest
- **G22** — silent child exit is a G12 variant
- **G23** — 0-byte WAV is G14
- **G24** — corrupt bytes: fold into G14 / pytest of WAV load unless `has_audio` sticks (then it is G14’s assert)
- **G25 / G26** — late WAV and auto-stop vs Stop Rec are flaky over URP
- **G30** — stale WAV is G16 (second take replaces)

---

### v2 suggested implementation order

1. Harness: open sidebar, `set_query_text` + `press_send` + `wait_idle` + `next_hello_ok` (smoke).
2. **B1a, B1b, B3, B7, B10** (Stop is the mountain).
3. **C1, C4, D1, D2** (empty banners + `[Thinking]` vs HTML) — landed; `FILTER=C` / `FILTER=D`.
4. **F1, F2, F4, F14** (errors + recovery).
5. **E3, E5, E6, E7** (tools without HITL).
6. **E8a/b** (Stop mid-delegate).
7. **E9a–E9e** (HITL overlay on the same buttons).
8. F3/F6/F9+ only after cancel + hang are stable.
9. **G1, G7, G11, G12, G15** (Record FSM vs Send busy) — stub capture, no mic. Rest of G after that.
10. Next-level keep only (not the dropped F19–F32 dump): **C5**, **B16 / B19 / B21**, **E17 / E21 / E22**, and **G29** are landed. Remaining: **G21 / G27 / G28**.

Pytest already covers `decide_completion` in `tests/scripts/test_mock_llm_server.py`. v2 does **not** duplicate that; it covers **drain + FSM + UNO**. Mock already lists `writeragent-mock-whisper` and canned transcripts.