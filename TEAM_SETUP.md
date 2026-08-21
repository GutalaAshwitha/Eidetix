# Team Setup & Remote HydraDB Connection Guide

This guide explains how your team members can run the Track 03 Memory and Retrieval pipeline against a shared HydraDB instance (hosted locally or via ngrok).

---

## 1. Hosting HydraDB (Host Machine)

If you are hosting the database for your team on your machine:

1. **Start HydraDB Graph Server:**
   ```bash
   cd ~/hackhydra/hydradb
   CLOUD_PROVIDER=local LOCAL_PATH=$PWD/.hydradb/store GRAPH_NAMESPACE=default GRAPH_ID=default GRAPH_CELL_ID=cell-0 GRAPH_CELLS=cell-0 GRAPH_NODE_ID=node-0 GRAPH_BOLT_NODE_ADDRESSES=node-0=127.0.0.1:7687 GRAPH_ADVERTISED_BOLT_ADDR=127.0.0.1:7687 GRAPH_DATA_CACHE_DIR=$PWD/.hydradb/cache GRAPH_AUTH_TOKEN_FILE=$PWD/.hydradb/auth-token GRAPH_ALLOW_PLAINTEXT=true RUST_MIN_STACK=33554432 cargo run --locked --features server-runtime --bin graph-node
   ```

2. **Expose Ports via ngrok:**
   Install `ngrok` if not already installed, then run:
   ```bash
   ngrok http 8443
   ```
   Or use the helper script:
   ```bash
   bash scripts/share_hydra.sh
   ```

3. **Share the HTTP URL with Teammates:**
   Share the generated ngrok URL, for example:
   `https://a1b2c3d4.ngrok-free.app`

---

## 2. Connecting from Client / Teammate Machine

Teammates do **not** need to run HydraDB locally. They simply set the environment variable pointing to the host's ngrok URL:

```bash
export HYDRA_URL="https://<ngrok-url>.ngrok-free.app/v1/graphs/default/query"
export HYDRA_TOKEN="local-development-token-32-bytes"
```

Then run the pipeline or tests:
```bash
python3 -m pytest tests/ -v
# or run end-to-end prototype:
python3 -m memory.pipeline
```

---

## 3. Environment Variables Reference

| Variable | Default Value | Description |
|---|---|---|
| `HYDRA_URL` | `http://127.0.0.1:8443/v1/graphs/default/query` | HydraDB HTTP query endpoint |
| `HYDRA_TOKEN` | `local-development-token-32-bytes` | Bearer token for HydraDB API |
| `GROQ_API_KEY` | *(Optional)* | Groq API key for LLM-based fact extraction |
| `OPENAI_API_KEY` | *(Optional)* | OpenAI API key for LLM-based fact extraction |
