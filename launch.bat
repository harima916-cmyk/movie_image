@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo 依存パッケージを確認中...
python -m pip install -r requirements.txt -q
echo.
python app.py
pause
