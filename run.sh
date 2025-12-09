#!/usr/bin/env bash
set -euo pipefail

# Create venv if not exists
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

pip install -r requirements.txt

# Generate synthetic data (Contracts_synthetic.xlsx / Prices_synthetic.xlsx)
python generate_synthetic_data.py

# Launch Streamlit app (this is the main entry point)
streamlit run app.py --server.port 8501
