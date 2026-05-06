@echo off
chcp 65001 > nul
cd /d "%~dp0"

REM ── 仮想環境の作成（初回のみ）────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo 仮想環境を作成中...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo [エラー] 仮想環境の作成に失敗しました。
        echo Python がインストールされているか確認してください。
        pause
        exit /b 1
    )
    echo 仮想環境を作成しました。
)

REM ── 依存パッケージのインストール ─────────────────────────────────
echo 依存パッケージを確認中...
.venv\Scripts\python.exe -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo.
    echo [エラー] パッケージのインストールに失敗しました。
    pause
    exit /b 1
)

REM ── アプリ起動 ────────────────────────────────────────────────────
echo.
.venv\Scripts\python.exe app.py
pause
