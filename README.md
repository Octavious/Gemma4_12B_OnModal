# Gemma 4 12B on Modal — OpenAI-Compatible Endpoint

Deploy Google's **Gemma 4 12B** on [Modal](https://modal.com) as a public,
OpenAI-compatible HTTPS endpoint secured with a Bearer API key. Built to be
consumed from coding agents (**Cline / RooCode**), desktop chat apps (**Jan**),
**Postman**, or plain `curl` / `fetch` — all from a machine that could never run
the model locally (e.g. a 6 GB GPU laptop).

The GPU lives in Modal's cloud; your machine only sends API requests.

---

## What you get

- `google/gemma-4-12B-it` served by **vLLM** (paged attention, batching).
- A URL like `https://<you>--gemma4-demo-serve.modal.run` exposing:
  - `GET  /v1/models`
  - `POST /v1/chat/completions`
  - `GET  /docs` (interactive Swagger UI — also a handy "warm-up" page)
- **Bearer-key auth** on every endpoint, with the key stored as a Modal secret
  (never hardcoded in the script).
- **Scale-to-zero**: you only pay for GPU time while the container is awake.

---

## Prerequisites

1. A Modal account (`pip install modal` then `modal setup`).
2. A Hugging Face account that has **accepted the Gemma license** on the
   [model page](https://huggingface.co/google/gemma-4-12B-it).
3. A Hugging Face **read token** from <https://huggingface.co/settings/tokens>.

---

## One-time setup

```bash
pip install modal
modal setup                       # authenticate this machine (opens browser)

# Hugging Face token — lets the container download the gated weights
modal secret create huggingface-secret HF_TOKEN=hf_xxxxxxxxxxxxxxxx

# Your endpoint API key — pick any string you like
modal secret create vllm-api-key VLLM_API_KEY=xxxxxxx-demo-key-2026
```

> Secrets can also be created/edited in the Modal dashboard under **Secrets**,
> which is the easiest way to rotate the key later.

---

## Deploy

```bash
modal deploy gemma4_demo.py
```

Modal prints your endpoint URL, e.g.:

```
https://xyz--gemma4-demo-serve.modal.run
```

The **first ever** boot downloads ~24 GB of weights (several minutes). After
that the weights live in a Modal Volume, so cold starts are much faster.

---

## Verify it works

Replace the URL and key with your own.

**1. Check the model id (and warm the container):**

```bash
curl https://xyz--gemma4-demo-serve.modal.run/v1/models \
  -H "Authorization: Bearer xxxxxxx-demo-key-2026"
```

Expect: `{"object":"list","data":[{"id":"gemma4-12b", ...}]}`
(The first call after sleep can take 1–3 minutes — that's the cold start.)

**2. Full chat round-trip:**

```bash
curl https://xzy--gemma4-demo-serve.modal.run/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer xxxxxxx-demo-key-2026" \
  -d '{"model":"gemma4-12b","messages":[{"role":"user","content":"Say hello"}]}'
```

---

## Client configuration

For **every** client below, the three values are the same:

| Field        | Value                                                       |
|--------------|-------------------------------------------------------------|
| Base URL     | `https://<you>--gemma4-demo-serve.modal.run/v1`             |
| API Key      | `xxxxxxx-demo-key-2026`  *(raw key — no "Bearer" prefix)*       |
| Model ID     | `gemma4-12b`                                                 |

> **Important:** type only the raw key in any app's API-key field. The app adds
> the `Authorization: Bearer ...` header for you. You only write the word
> `Bearer` yourself when building a header by hand (raw `curl` / `fetch`).

### Cline

Settings → **API Configuration**:
- API Provider: **OpenAI Compatible**
- Base URL / API Key / Model ID: as in the table above.

### RooCode

Settings (⚙) → your profile → **API Provider**:
- Provider: **OpenAI Compatible**
- Base URL / API Key / Model ID: as in the table above.
- Set **context window** to `32768` to match the server's `--max-model-len`.
- Tip: save this as a separate profile ("Modal Gemma 4") so you can switch
  between it and your usual model in one click.

### Jan (desktop)

Settings → **Model Providers** → **+** (add custom provider):
- Name: `Modal Gemma 4`
- Base URL: `…/v1`  *(end with `/v1`, no trailing slash)*
- API Key: `xxxxxxx-demo-key-2026`
- Add model manually with id `gemma4-12b` if auto-detect stays empty.
- Select it from the model dropdown in the chat input area to start chatting.

### Postman

- Method `GET` `…/v1/models` or `POST` `…/v1/chat/completions`
- Auth tab → Type **Bearer Token** → paste the raw key (Postman adds "Bearer").

---

## Useful commands

```bash
modal app logs gemma4-demo        # live container logs (watch startup here)
modal app stop gemma4-demo        # tear everything down
modal deploy gemma4_demo.py       # redeploy after edits

# rotate the API key without touching code:
modal secret create vllm-api-key VLLM_API_KEY=new-key --force
modal deploy gemma4_demo.py
```

---

## Cold starts (read this before recording / demoing)

A **green status** in the Modal dashboard means *deployed*, not *awake*. When
the container has scaled to zero, the first request triggers boot → GPU attach →
weight load (1–3 min once cached). Clients often time out and look broken during
this window.

**Fixes:**
- **Warm first:** open `/docs` in a browser or run the `/v1/models` curl and wait
  for a response *before* using Cline / RooCode / Jan.
- **Keep warm for a session:** add `min_containers=1` to the `@app.function(...)`
  decorator so one container never sleeps. (You pay for idle GPU — turn it back
  to `0` / remove it when done.)
- **Stay warm longer between requests:** increase `scaledown_window`.

---

## Cost notes

- An **L40S** bills only while the container is running (roughly a couple of
  dollars per hour of active use). With scale-to-zero, idle time is free.
- A full demo + testing session typically costs a couple of dollars; Modal's
  monthly free credits may cover it entirely.
- `min_containers=1` keeps the GPU billing continuously — use it only during the
  shoot, then revert.

---

## Tuning knobs

| Setting              | Effect                                                                 |
|----------------------|------------------------------------------------------------------------|
| `--max-model-len`    | Max context (prompt + output) tokens. Higher = more KV-cache memory.   |
| `--enforce-eager`    | **On:** faster cold boots, slower generation. **Off (default here):** slower boots, faster tokens. Agents prefer it off. |
| `gpu="L40S"`         | 48 GB, fits 12B bf16. For more headroom/throughput use `A100-40GB` / `H100`. Quantized weights can fit smaller GPUs (`L4`, `A10G`). |
| `max_inputs` (concurrent) | How many requests one warm container serves at once.              |
| `scaledown_window`   | Idle time before the container sleeps.                                 |

---

## Troubleshooting

**`RuntimeError: mat1 and mat2 shapes cannot be multiplied` at startup**
vLLM/Transformers too old for Gemma 4's architecture. Use the nightly image
(`vllm/vllm-openai:nightly`) as in this script. As stable vLLM gains Gemma 4
support, pin a stable version for reproducibility.

**`We were unable to determine the version of Python installed in the Image`**
The vLLM image keeps Python where Modal can't auto-detect it. Fix:
`modal.Image.from_registry("vllm/vllm-openai:nightly", add_python="3.12")`.

**Request hangs for 1–3 minutes, then works**
Cold start. Warm the container first (see above).

**`401 Unauthorized`**
Key mismatch. The client key must equal `VLLM_API_KEY` exactly. A common cause
is pasting `Bearer ` into the key field — apps add that word themselves.

**Jan shows no model id / auto-detect empty**
With auth enabled, `/v1/models` also needs the key. Just add the model id
manually (`gemma4-12b`); it works regardless of auto-detection.

**`google/gemma-4-12B-it` download fails (401/403, "gated repo")**
Accept the license on the HF model page with the same account as your token,
and confirm the `huggingface-secret` (key `HF_TOKEN`) is attached.

---

## Reproducibility note

`vllm/vllm-openai:nightly` moves daily. Once you have a working boot, pin the
exact version (check the logs for the vLLM version, or pin the image by digest)
so the demo stays reproducible. When Gemma 4 lands in a stable vLLM release,
switch the image tag to that release.

---

## How it fits together

```
Your machine (6 GB GPU)            Modal cloud (L40S, 48 GB)
┌───────────────────────┐          ┌──────────────────────────────┐
│ Cline / RooCode / Jan │  HTTPS   │  vLLM  →  google/gemma-4-12B   │
│  (holds the API key)  │ ───────► │  /v1/chat/completions (auth)  │
└───────────────────────┘          └──────────────────────────────┘
```

The model never touches your laptop — only API requests and responses do.
