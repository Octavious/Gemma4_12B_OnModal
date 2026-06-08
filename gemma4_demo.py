"""
Gemma 4 12B on Modal — OpenAI-compatible vLLM endpoint.

Serves google/gemma-4-12B-it behind a public HTTPS endpoint that speaks the
OpenAI API, secured with a Bearer key read from a Modal secret. Designed to be
consumed by coding agents (Cline / RooCode), desktop chat clients (Jan), or
plain curl / fetch.

Deploy:   modal deploy gemma4_demo.py
Logs:     modal app logs gemma4-demo
Stop:     modal app stop gemma4-demo
"""

import modal

# --- Configuration -----------------------------------------------------------
MODEL_NAME = "google/gemma-4-12B-it"   # gated repo — license must be accepted on HF
SERVED_NAME = "gemma4-12b"             # the model id clients send in requests
VLLM_PORT = 8000
MINUTES = 60

# --- Image -------------------------------------------------------------------
# Gemma 4 is new; it needs vLLM's nightly build (matched Transformers included).
# `add_python` is required because Modal can't auto-detect Python in this image.
vllm_image = (
    modal.Image.from_registry("vllm/vllm-openai:nightly", add_python="3.12")
    .entrypoint([])  # clear the upstream entrypoint so our subprocess runs cleanly
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})  # faster HF weight downloads
)

# --- Persistent caches -------------------------------------------------------
# Weights (~24 GB) download once, then load from these Volumes on later boots.
hf_cache_vol = modal.Volume.from_name("huggingface-cache", create_if_missing=True)
vllm_cache_vol = modal.Volume.from_name("vllm-cache", create_if_missing=True)

app = modal.App("gemma4-demo")


@app.function(
    image=vllm_image,
    gpu="L40S",  # 48 GB — comfortably fits 12B bf16 weights + KV cache
    secrets=[
        modal.Secret.from_name("huggingface-secret"),  # HF_TOKEN (for gated weights)
        modal.Secret.from_name("vllm-api-key"),         # VLLM_API_KEY (endpoint auth)
    ],
    scaledown_window=15 * MINUTES,  # stay warm 15 min after the last request
    timeout=10 * MINUTES,
    volumes={
        "/root/.cache/huggingface": hf_cache_vol,
        "/root/.cache/vllm": vllm_cache_vol,
    },
)
@modal.concurrent(max_inputs=32)  # one container serves up to 32 concurrent requests
@modal.web_server(port=VLLM_PORT, startup_timeout=10 * MINUTES)
def serve():
    import os
    import subprocess

    cmd = [
        "vllm", "serve", MODEL_NAME,
        "--served-model-name", SERVED_NAME,
        "--host", "0.0.0.0",
        "--port", str(VLLM_PORT),
        "--max-model-len", "32768",            # agents send large prompts/context
        "--api-key", os.environ["VLLM_API_KEY"],  # Bearer auth on every endpoint
        # "--enforce-eager",  # uncomment for faster COLD BOOTS at the cost of
        #                     # slower generation. Left off here because coding
        #                     # agents favor fast tokens over fast boots.
    ]
    # Non-blocking launch is required under @modal.web_server.
    subprocess.Popen(" ".join(cmd), shell=True)
