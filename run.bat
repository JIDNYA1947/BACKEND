@echo off
REM Convenience script to set up and run the backend on Windows.

IF NOT EXIST .venv (
    python -m venv .venv
)

call .venv\Scripts\activate

pip install -r requirements.txt

IF NOT EXIST .env (
    copy .env.example .env
)

uvicorn app.main:app --reload
