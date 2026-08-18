# Python Compute Service

Standalone HTTP service for Collabora Online / Collabora Office `=PY()` formulas.
coolwsd POSTs dumb JSON to `/v1/execute`; this process runs sandboxed Python and
returns JSON results. **It does not read `writeragent.json`.**

## Quick start

```bash
./compute_service/start.sh
# or
python compute_service/server.py --host 127.0.0.1 --port 8000
```

- `GET /health` → `{"status":"healthy","service":"python-compute","version":"<version>"}` (no auth required)
- `POST /v1/execute` → `{ "id?", "code", "data?", "mode?", "session_id?", "timeout_ms?", "init_script?" }`

---

## API & Wire Protocol

### 1. Health Endpoint (`GET /health`)

Unauthenticated health probe suitable for Kubernetes/Docker liveness and readiness checks.
Always unauthenticated even when Bearer authentication is configured for execution.

- **Request**: `GET /health`
- **Response**: `200 OK`
  ```json
  {
    "status": "healthy",
    "service": "python-compute",
    "version": "0.8.59"
  }
  ```

### 2. Execution Endpoint (`POST /v1/execute`)

Evaluates sandboxed Python code and emits kit-safe dumb JSON (`allow_nan=False`, `NaN`/`Inf` → `null`).

- **Request Schema**:
  ```json
  {
    "id": "req-123",
    "code": "result = float(np.sum(data))",
    "data": [10, 20, 30],
    "mode": "isolated",
    "session_id": "optional-session-id",
    "timeout_ms": 5000,
    "init_script": "optional-init-code"
  }
  ```

- **Success Response (`200 OK`)**:
  ```json
  {
    "id": "req-123",
    "status": "ok",
    "result": 60.0,
    "stdout": ""
  }
  ```
  *(If Matplotlib plots are generated, they are returned in `images: [{"format": "png", "data_b64": "..."}]`)*

- **Evaluation Error Response (`200 OK`)**:
  Evaluation errors (e.g. `SyntaxError`, `ZeroDivisionError`, unauthorized imports) return `200 OK` with `status: "error"` so HTTP transport is distinguished from evaluated code errors:
  ```json
  {
    "id": "req-123",
    "status": "error",
    "error": "SyntaxError: invalid syntax (<string>, line 1)",
    "stdout": "",
    "message": "SyntaxError: invalid syntax (<string>, line 1)"
  }
  ```

### 3. HTTP Status Codes & Error Semantics

| HTTP Status | Condition | Response Payload Shape |
| :--- | :--- | :--- |
| **`200 OK`** | Evaluation completed (success or runtime evaluation error) | `{"id"?: "...", "status": "ok"\|"error", "result"\|"error": ...}` |
| **`400 Bad Request`** | Malformed JSON, non-object body, or missing `code` | `{"id"?: "...", "status": "error", "error": "Bad Request: ..."}` |
| **`401 Unauthorized`** | Missing or incorrect `Authorization: Bearer <secret>` | `{"status": "error", "error": "Unauthorized"}` + `WWW-Authenticate: Bearer` |
| **`404 Not Found`** | Unknown path or unsupported HTTP method | Plaintext `Not Found` |
| **`413 Payload Too Large`**| Request body exceeds `max_body_bytes` | `{"status": "error", "error": "Request body too large"}` |
| **`500 Internal Server Error`**| Unhandled server exception or JSON encoding failure | `{"id"?: "...", "status": "error", "error": "..."}` |

---

## Authentication (shared Bearer secret)

coolwsd sends `Authorization: Bearer <security.python_compute.api_key>` when that
key is non-empty. Configure the **same** secret on the service:

| Source | How |
|--------|-----|
| Environment | `PYTHON_COMPUTE_API_KEY=...` |
| Key file | `PYTHON_COMPUTE_API_KEY_FILE=/path` or `--api-key-file /path` |
| Config JSON | `"auth": { "api_key_file": "..." }` (no raw key in the JSON file) |

There is **no** `--api-key` CLI flag (secrets in argv are visible in `ps`).

Rules:

- **No key configured** → `/v1/execute` is open (insecure; fine for local/dev/test).
- **Key configured** → `/v1/execute` requires an exact `Bearer <token>` match
  (`hmac.compare_digest`). Failures return HTTP 401 + `WWW-Authenticate: Bearer`.

Match coolwsd (`coolwsd.xml`):

```xml
<python_compute>
  <enable type="bool">true</enable>
  <url>http://127.0.0.1:8000/v1/execute</url>
  <api_key>same-secret-as-service</api_key>
  <timeout_secs type="int">60</timeout_secs>
</python_compute>
```

---

## Configuration & Ops (no writeragent.json)

Precedence (later wins): defaults → `--config` / `PYTHON_COMPUTE_CONFIG` JSON →
`PYTHON_COMPUTE_*` env (plus legacy `HOST`/`PORT`) → `--host` / `--port` /
`--api-key-file`.

Example JSON: [`python-compute.example.json`](python-compute.example.json).

| Variable | Meaning | Default |
|----------|---------|---------|
| `HOST` / `PYTHON_COMPUTE_HOST` | Bind address (loopback default) | `127.0.0.1` |
| `PORT` / `PYTHON_COMPUTE_PORT` | Listening port | `8000` |
| `PYTHON_COMPUTE_API_KEY` | Shared Bearer secret | `""` |
| `PYTHON_COMPUTE_API_KEY_FILE` | Path to secret file (strip one trailing newline) | `""` |
| `PYTHON_COMPUTE_CONFIG` | Path to JSON config | `""` |
| `PYTHON_COMPUTE_LOG_LEVEL` | Log verbosity (`DEBUG`, `INFO`, `WARN`, `ERROR`) | `INFO` |
| `PYTHON_COMPUTE_MAX_BODY_BYTES` | Request body cap | `33554432` (32 MiB) |
| `PYTHON_COMPUTE_DEFAULT_TIMEOUT_SEC` | Default execution timeout in seconds | `30` |
| `PYTHON_COMPUTE_MAX_TIMEOUT_SEC` | Upper bound clamp for `timeout_ms` | `600` |
| `PYTHON_COMPUTE_MAX_THREADS` | Worker thread pool capacity | `min(32, cpu_count + 4)` |

Key file permissions: readable only by the service user (e.g. mode `0400`).

---

## Lifecycle & Signal Handling

- **Graceful Shutdown**: The service traps `SIGTERM` and `SIGINT`.
- When `SIGTERM` is received (from Kubernetes pod termination or `docker stop`), the server initiates `server.shutdown()` on a background thread, stops accepting new connections, drains in-flight evaluations, and closes listening sockets cleanly.

---

## Threading, Concurrency & Scaling Architecture

### 1. Thread Pool Concurrency Model
The Python Compute Service uses a bounded `concurrent.futures.ThreadPoolExecutor` worker pool integrated into `DualStackThreadPoolHTTPServer`.

- **Bounded Worker Pool**: Instead of unbounded thread spawning, incoming connections are queued and executed by a fixed-capacity thread pool (`max_threads`, default `min(32, os.cpu_count() + 4)`). This protects the host from thread exhaustion and excessive context-switching overhead during high-concurrency spikes.
- **Isolated vs. Shared State**:
  - `mode="isolated"`: Each request executes in a fresh, independent AST-sandboxed execution namespace. Evaluations run concurrently across worker threads with zero lock contention.
  - `mode="shared"`: Stateful session requests referencing the same `session_id` are synchronized using a per-session lock (`_session_lock(session_id)`). This prevents race conditions and data corruption within a single session's namespace while allowing requests for different sessions to execute concurrently across separate threads.

### 2. Python GIL & NumPy Multi-Core Performance
In standard CPython, the Global Interpreter Lock (GIL) serializes execution of pure Python bytecode so that only one thread executes Python bytecodes at a time within a single process.

However, for numerical and scientific computing workloads:
- **GIL Release in C/Fortran Extensions**: High-performance compute libraries such as **NumPy**, **SciPy**, **OpenBLAS**, **MKL**, **SymPy** C-routines, and **Polars** explicitly release the GIL during heavy numerical operations (e.g. matrix multiplications, array vectorization, aggregations, FFTs, and linear algebra routines).
- **True Multi-Core Concurrency**: While a NumPy operation is computing in native C/Fortran code with the GIL released, other worker threads in the pool can simultaneously acquire the GIL or run their own numeric compute routines on separate CPU cores.
- **I/O Parallelism**: Network I/O (receiving HTTP payloads, streaming output, socket communications) also releases the GIL, ensuring that socket operations and JSON serialization/deserialization do not stall compute threads.

Because typical Collabora Online `=PY()` spreadsheet workloads consist primarily of NumPy/SciPy vector operations and array manipulations, thread pool request handling achieves high CPU utilization across multiple cores with minimal memory overhead and zero inter-process communication (IPC) serialization penalty.

### 3. Scaling Up & Scaling Out

| Scaling Dimension | Strategy | Characteristics & Recommendations |
| :--- | :--- | :--- |
| **Vertical Scale (Threads)** | Thread pool (`max_threads`) (Current default) | Excellent for NumPy/SciPy-dominated workloads where GIL is frequently released. Minimal memory footprint, shared module caches, zero IPC latency. Bounded to prevent thread exhaustion. |
| **Vertical Scale (Processes)** | Multi-worker WSGI processes (e.g., Gunicorn / uWSGI / multi-instance ports) | Recommended if workloads involve extensive pure-Python CPU loops that hold the GIL. Multiple OS processes bypass the single-interpreter GIL entirely and saturate all CPU cores. |
| **Horizontal Scale (Containers/K8s)** | Multiple container replicas behind a load balancer | The compute service is lightweight and stateless (for isolated evaluations). Multiple instances can be deployed across Kubernetes pods or Docker hosts behind coolwsd or a reverse proxy (e.g. Nginx, Envoy, HAProxy) with round-robin load balancing. For `mode="shared"`, configure session-affinity (sticky routing) by session ID if persistent state is retained across calls. |

---

## Logging & Observability

The service uses standard Python `logging` under the logger name `compute_service`.
Log format includes timestamps, log level, request IDs, modes, code size, execution durations, and status:

```text
2026-08-17 20:00:00,123 [INFO] compute_service: Starting Python Compute Service on 127.0.0.1:8000 (auth=yes)...
2026-08-17 20:00:01,456 [INFO] compute_service: exec /v1/execute id='req-123' mode=isolated session=None code_len=32 timeout=30s
2026-08-17 20:00:01,489 [INFO] compute_service: done /v1/execute id='req-123' status='ok' duration=32.40ms
```

---

## Docker & Container Hardening

```bash
docker build -f compute_service/Dockerfile -t python-compute .
docker run --rm -p 127.0.0.1:8000:8000 \
  --read-only --tmpfs /tmp:rw,size=64m,mode=1777 \
  --memory=1g --cpus=1 --pids-limit=256 \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  -e PYTHON_COMPUTE_API_KEY_FILE=/run/secrets/key \
  -v /secure/key:/run/secrets/key:ro \
  python-compute
```

- For cross-container networking within a private bridge network, set `HOST=0.0.0.0`.
- The multi-stage Dockerfile copies only pre-compiled packages into the runner image, drops root privileges (`USER appuser`), and excludes compiler build tools (`build-essential`).

---

## CLI

```bash
python compute_service/server.py --help
python compute_service/server.py --config compute_service/python-compute.example.json \
  --api-key-file /run/secrets/python_compute_api_key
```

## Tests

```bash
pytest tests/compute_service/
```

See also [`docs/numpy-jailsafe.md`](../docs/numpy-jailsafe.md).
