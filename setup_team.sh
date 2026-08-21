#!/bin/bash

echo "Setting up Hack Hydra Track 3..."

export HYDRA_URL="https://beverley-standardizable-erin.ngrok-free.dev/v1/graphs/default/query"
export HYDRA_TOKEN="local-development-token-32-bytes"

echo "HydraDB URL configured:"
echo "$HYDRA_URL"

echo "Setup complete!"
echo "Run: python3 -m memory.pipeline"