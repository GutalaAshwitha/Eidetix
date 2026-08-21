#!/bin/bash
export PATH="$HOME/.cargo/bin:$PATH"
cd /home/gutalaashwitha/hackhydra/hydradb
export CLOUD_PROVIDER=local
export LOCAL_PATH=$PWD/.hydradb/store
export GRAPH_NAMESPACE=default
export GRAPH_ID=default
export GRAPH_CELL_ID=cell-0
export GRAPH_CELLS=cell-0
export GRAPH_NODE_ID=node-0
export GRAPH_BOLT_NODE_ADDRESSES=node-0=127.0.0.1:7687
export GRAPH_ADVERTISED_BOLT_ADDR=127.0.0.1:7687
export GRAPH_DATA_CACHE_DIR=$PWD/.hydradb/cache
export GRAPH_AUTH_TOKEN_FILE=$PWD/.hydradb/auth-token
export GRAPH_ALLOW_PLAINTEXT=true
export RUST_MIN_STACK=33554432
exec cargo run --locked --features server-runtime --bin graph-node
