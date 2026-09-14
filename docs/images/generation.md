# WriterAgent Image Generation

Image generation and editing in WriterAgent uses the **same endpoint URL and API key as chat**; only the **image model** (`image_model`) differs from the text/chat model.

## Architecture

### Core image service

[`plugin/writer/images/image_utils.py`](../../plugin/writer/images/image_utils.py):

- **`EndpointImageProvider`**: requests images via `LlmClient` (routing dedicated text-to-image models to OpenRouter's dedicated Image API via `POST /api/v1/images`, falling back to standard `modalities: ["image"]` chat completions for multimodal models).
- **OpenRouter `/images` payload** ([`OpenRouterShim.build_image_request`](../../plugin/framework/client/openai_shim.py)): `output_format` is `png` (not `webp` — models such as `black-forest-labs/flux.2-klein-4b` only accept png/jpeg). When width/height are set it sends `size` (`WxH`) and omits `aspect_ratio`; OpenRouter treats an explicit pixel size as authoritative and returns HTTP 400 if a paired `aspect_ratio` is considered mismatched.
- **`ImageService`**: merges config defaults (base size, steps) and delegates to `EndpointImageProvider`.

### Tools and document insertion

[`plugin/writer/images/images.py`](../../plugin/writer/images/images.py) — `image_generate` tool (also via `delegate_to_specialized_*_toolset(domain="images")`):

- Text-to-image from a prompt.
- Img2img when `source_image='selection'` and an image is selected in the document. Omitting `source_image` while a graphic is selected also edits in place (parent/specialist often drop the argument after rewriting an edit into a generate-new prompt).

**Sidebar Image mode** (`chat_mode = Image`, not Chat/specialist) calls `image_generate` directly — no chat LLM. With a document graphic selected, the send path passes `source_image='selection'` so the same img2img + in-place replace runs. With nothing selected, it generates and inserts a new graphic.

[`plugin/writer/images/image_tools.py`](../../plugin/writer/images/image_tools.py):

- **`image_insert`**: inserts into Writer, Calc, Draw, and Impress; stable paths are linked, temp/cache paths are embedded. Writer letterheads use `target=header`/`footer`; a different-first-page logo needs `first_is_shared=false` then `target=header_first`/`footer_first` (same `AS_CHARACTER` + `auto_height` path). Draw/Impress take millimetres (`page`, `x_mm`, `y_mm`; omitted x/y centers on the page).
- **`get_selected_image_base64`**: extracts selected image for img2img.
- **`add_image_to_gallery`**: optional Media Gallery add after generation.

## Model naming

| Key | Role |
|-----|------|
| `text_model` | Chat/text model (also exposed to `LlmClient` as `"model"` via `get_api_config()`). Writes use `set_text_model()`; recent ids per endpoint live in `model_lru@<endpoint>`. |
| `image_model` | Model id for image generation on the configured endpoint. Writes use `set_image_model()`. |
| `image_model_lru` | Recent image model ids for Settings and sidebar comboboxes. |

## Settings UI

**General tab** ([`SettingsDialog.xdl.tpl`](../../extension/WriterAgentDialogs/SettingsDialog.xdl.tpl)): endpoint, API key, **Text/Chat Model**, **Image Model**, audio model, temperature, max tokens, additional instructions.

**Image Settings tab**: base size, aspect ratio, steps, seed, auto gallery, insert frame.

**Chat sidebar** ([`ChatPanelDialog.xdl`](../../extension/WriterAgentDialogs/ChatPanelDialog.xdl)): text model and image model comboboxes; additional instructions come from config only (Settings).

## Config keys used by `image_generate`

| Config key | Role |
|------------|------|
| `image_model` | Image model on the chat endpoint (fallback: text model / provider defaults). |
| `image_base_size` | Default width/height base dimension. |
| `image_default_aspect` | Default aspect ratio for the tool. |
| `image_steps` | Steps passed to the endpoint when &gt; 0. |
| `image_auto_gallery` | Add generated images to Media Gallery. |
| `image_insert_frame` | Wrap inserted images in a frame. |
| `seed` | Reserved for future local generation backends. |

After a successful endpoint generation, the model used is pushed into `image_model_lru`.

## Img2img (edit selected image)

Single `generate_image(prompt, source_image=...)` API. Per-dropdown wire format, gaps, and coding notes: [Image edit by Settings endpoint](#image-edit-by-settings-endpoint).

| Backend | How edit works today |
|---------|----------------------|
| **OpenRouter** | Dedicated `/api/v1/images` (image-only models such as `black-forest-labs/flux.2-klein-4b`): `input_references` with a `image_url` data URL. Chat-completions multimodal path (`modalities: ["image"]`) still sends the source as a user `image_url` part. |
| **Together / Grok / Google Gemini image / Ollama** | Same `image_completion` / `build_image_request` path as create, with per-shim edit fields (table below). |
| **Other dropdown / custom OpenAI-compat** | Same path; optional top-level `image_url` where the server honors it. |

Tool usage: pass `source_image='selection'` with an image selected in the document; optional `strength` (default 0.75) is accepted by the tool but **not sent on the wire**. If `source_image` is omitted and a graphic is selected, `image_generate` treats that as an in-place edit. Clear the selection to create a new image.

The **parent** main agent is steered in `SPECIALIZED_TASK_RULES` and `DELEGATE_SPECIALIZED_TASK_PARAM_HINT`: when the user wants to edit/change/restyle an existing or selected image, the `delegate_to_specialized_*` `task` must instruct `image_generate(source_image='selection')` and keep the user's wording. A generate-new paraphrase (“Generate an image of … dressed as a wizard”) is what the specialist then executes as create-new.

The images specialist is steered the same way: `images_specialized_sub_agent_hint()` plus `IMAGES_SPECIALIZED_EXAMPLES` (`writer:images` / `calc:images` / `draw:images`). Edit/change/restyle of an existing or selected image (e.g. “make it look like a wizard”) must call `image_generate` with `source_image='selection'` so img2img + `replace_image_in_place` keep the graphic in the same frame. A delete plus a prompt-only generate creates a new image instead of editing.

## Image edit by Settings endpoint

Follow-up after the OpenRouter img2img fix (`input_references` on `POST /api/v1/images`). The Settings **endpoint combobox** is `ENDPOINT_PRESETS` in [`plugin/framework/client/model_fetcher.py`](../../plugin/framework/client/model_fetcher.py). Together, Grok, Google Gemini image models, and Ollama now send the selected graphic on edit; remaining presets are still create-only or unverified.

### Did the OpenRouter fix change create?

**No.** [`OpenRouterShim.build_image_request`](../../plugin/framework/client/openai_shim.py) only adds `input_references` when `image_url` or `source_image` is set. A create call (prompt only) still sends `prompt`, `model`, `n`, `output_format: png`, and optional `size` — same as before. The chat-completions path (`modalities: ["image"]`) was not touched; it already attached the source as a user `image_url` part for non-image-only models.

The previous bug was OpenRouter-specific: a top-level `image_url` on `/api/v1/images` is ignored (HTTP 200, text-only prompt tokens), so Flux generated a new picture. Other shims were not part of that commit.

### How edit is routed today

`image_generate` still extracts selection base64 and calls `ImageService.generate_image(..., source_image=b64)`. Then [`EndpointImageProvider.generate`](../../plugin/writer/images/image_utils.py):

| Config | Path | Source image on the wire |
|--------|------|--------------------------|
| OpenRouter + image-only model (`is_image_only_model`) | `LlmClient.image_completion` → `OpenRouterShim` → `POST /api/v1/images` | **`input_references`** (fixed) |
| OpenRouter + multimodal image model | `make_chat_request` + `modalities: ["image"]` | User content: text + `image_url` data URL |
| Together / Grok / Google / Ollama | `image_completion` → that provider’s `build_image_request` | Together `reference_images` (Kontext: `image_url`); Grok `POST /images/edits`; Gemini `inlineData`; Ollama `images[]` |
| Other dropdown / custom URL | `image_completion` → `OpenAIShim` | Top-level `image_url` if the server honors it |

`strength` is copied into `generate_image` kwargs and then ignored by every shim.

### Per-preset: what we send vs what the vendor wants

“Uses source?” means: if the user has a graphic selected, does the HTTP body include it in a field the vendor documents for img2img? Not “did we live-test this model.”

| Settings preset | Shim | Create (today) | Edit (today) | Uses source? | Vendor edit API (for later coding) |
|-----------------|------|----------------|--------------|--------------|-------------------------------------|
| **OpenRouter** | `OpenRouterShim` | `POST /api/v1/images` or chat `modalities: ["image"]` | Dedicated: `input_references: [{type: image_url, image_url: {url}}]`. Chat: user `image_url` part. | **Yes** (after the fix, for models that advertise references) | Already the documented field. Cap count from `GET /api/v1/images/models` (`supported_parameters.input_references`, e.g. flux.2-klein-4b is 0–4). |
| **Together AI** | `TogetherShim` | `POST …/images/generations` OpenAI-style JSON | Same URL. Non-Kontext: **`reference_images: [data URL]`** (no `image_url`). Model id contains `kontext`: top-level **`image_url`**. | **Yes** | [Together reference images](https://docs.together.ai/docs/inference/images/reference-images). Default `google/flash-image-2.5` is array-only. |
| **X.ai (Grok)** | `GrokShim` | `POST /v1/images/generations` (`aurora` default, `response_format: b64_json`; **no size**) | `POST /v1/images/edits` JSON `image: {url, type: image_url}`. Does not send `image_url` on `/images/generations`. Keeps the caller’s `image_model`. | **Yes** | xAI [image editing](https://docs.x.ai/developers/model-capabilities/images/editing) (JSON, not OpenAI multipart). |
| **Google Gemini** | `GoogleShim` | Imagen: native `:predict`. Other (e.g. `gemini-*-flash-image`): `:generateContent` with `responseModalities: [IMAGE, TEXT]`. Text prompt only. | Gemini: `:generateContent` with an `inlineData` part (`mimeType` + raw base64) next to the text. **Imagen + source raises** (create-only; would otherwise replace the graphic with a new image). | **Yes** (Gemini image models) | Imagen `:predict` stays text-to-image. Dropdown URL `…/v1beta/openai` is stripped; the shim talks native REST. |
| **Local (Ollama)** | `OllamaShim` | `POST /api/generate` `{model, prompt, stream: false, width, height}` | Same URL plus **`images: [raw base64]`** (no data-URL prefix, no `image_url`). | **Yes** | [Ollama generate](https://docs.ollama.com/api/generate) `images` array. Width/height are top-level, not inside `options`. |
| **Local (LM Studio)** | `OpenAIShim` | `POST …/images/generations` + optional `image_url` | Top-level `image_url` | **Only if that server honors it** | Whatever the loaded plugin exposes. Many OpenAI-compat servers implement create only. If they add `/images/edits` (multipart) or a JSON `image`/`images` field, branch on that — do not assume `image_url` on generations. |
| **Mistral** | `OpenAIShim` | `POST …/images/generations` | Top-level `image_url` | **No useful image API** | Mistral image gen is the **Agents** `image_generation` tool on the conversations API, not `/images/generations`. Out of scope unless we add that connector. |
| **Groq** | `OpenAIShim` | same | `image_url` on generations | **No** | Vision chat only (`image_url` on `/chat/completions` → text). No image **output**. Do not pretend img2img works. |
| **DeepSeek** | `OpenAIShim` | same | same | **No** | Chat/reasoner only. No image generation endpoint. |
| **Cerebras** | `OpenAIShim` | same | same | **No** | Chat only. |
| **Perplexity** | `OpenAIShim` | same | same | **No** | Search/chat. No image generation. |
| **Anthropic** | `AnthropicShim` (inherits default image builder) | `POST …/images/generations` (Anthropic does not serve this) | Top-level `image_url` on that missing route | **No** | Messages API is vision **in**, text **out**. No first-party image generate/edit. |
| **NVIDIA NIM** | `OpenAIShim` | `POST …/images/generations` | Top-level `image_url` | **Model-dependent** | NIM wraps many backends. Treat like custom OpenAI-compat: probe `/images/generations` vs `/images/edits`; do not assume `image_url`. |
| **Z.ai** | `OpenAIShim` | `POST {base}/api/paas/v4/images/generations` | Top-level `image_url` | **Unknown / unverified** | Confirm against current Z.ai image docs before adding a shim. Until then, same silent-ignore risk as OpenRouter’s old `image_url`. |

Custom typed URLs (not a preset label) use the same detection as chat (`get_provider_from_endpoint` / `PROVIDERS` in [`auth.py`](../../plugin/framework/client/auth.py)) and fall through to `OpenAIShim` unless the host matches ollama / openrouter / xai / google / anthropic.

OpenAI’s own host is in `PROVIDERS` and Quick Setup but **not** in the Settings dropdown. If someone pastes `api.openai.com`, edit today still hits `/images/generations` with JSON `image_url`. Official edit is `POST /v1/images/edits` (multipart file, or GPT-image JSON `images[]` / `image_url`). That is a separate coding item from the dropdown.

### Same failure mode as OpenRouter

The OpenRouter bug was: **HTTP 200 + a new image**, because the field name was wrong. Together / Grok / Gemini image / Ollama now send a documented edit field (Imagen raises instead of generating). That pattern is still possible on OpenAI-compat leftovers (LM Studio, NVIDIA, Z.ai, pasted `api.openai.com`) that ignore top-level `image_url` on `/images/generations`.

UI still runs `replace_image_in_place`, so a create-only server will swap the selected graphic for an unrelated generation.

### Remaining (not this round)

Do not add a new `ImageProvider` or a second HTTP client.

1. **OpenAI-compat leftovers** (LM Studio, NVIDIA, Z.ai, pasted `api.openai.com`) — `/images/edits` when the server has it; otherwise document “create only.”
2. **`strength`** — only emit it for backends that document it (diffusion img2img). Ignore for Gemini / Grok-edit / OpenRouter `input_references` / Together `reference_images`.
3. Skip Mistral / Groq / DeepSeek / Cerebras / Perplexity / Anthropic for image **output** until they ship a real generate/edit route.

## Future Work

### OpenRouter Image Generation Enhancements
- **Support Additional Parameters**: Extend settings UI and model request payload to support OpenRouter image parameters such as `aspect_ratio` (e.g. 16:9, 1:1, etc.), `background` (auto/transparent/opaque), `output_format` (png/webp), and `output_compression`.
- **Image Model Metadata Checking**: Call `GET https://openrouter.ai/api/v1/images/models` (or filter `/api/v1/models` by `output_modalities=image`) dynamically to discover supported parameters (e.g., specific resolutions, aspect ratios) and populate/validate settings.

## Related docs

- Endpoint HTTP details: [`plugin/framework/client/llm_client.py`](../../plugin/framework/client/llm_client.py)
- Sidebar / direct-image mode: [`../chat/sidebar-implementation.md`](../chat/sidebar-implementation.md)
- **Planned local backends:** [diffusers-comfyui-dev-plan.md](diffusers-comfyui-dev-plan.md) — **ComfyUI** (new backend); local images via **Ollama/endpoint** already supported
