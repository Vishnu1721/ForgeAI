# Verification
Use Python 3.12 and a disposable FORGE_DB. Run pip install -r requirements.txt, python -m pytest -v, python evaluate.py.
Optional live evaluation: python evaluate.py --live requires OPENAI_API_KEY.
Docker: docker build -t forgeai . ; docker run --rm -p 127.0.0.1:8001:8000 -v forge-data:/data forgeai
Demo tokens and role selector are not production authentication. Do not expose publicly. ERP/CRM and email are simulated. No cloud deployment performed.
