#!/bin/bash
python3 -m pip install -r requirements.txt
streamlit run app.py --server.port "${PORT:-8501}" --server.address 0.0.0.0 --server.headless true
