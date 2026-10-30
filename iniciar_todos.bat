@echo off
title Iniciando Bots VigiaSaude
color 0A
echo ==========================================
echo    INICIANDO TODOS OS BOTS VIGIASAUDE
echo ==========================================
echo.

echo [1/4] Iniciando VS Bot (Premium)...
cd /d "C:\Users\User\Pictures\Bot_VigiaSaude"
call .\.venv\Scripts\python.exe servidor.py restart
timeout /t 2 >nul

echo [2/4] Iniciando Bot Cidadao (Teresina)...
cd /d "C:\Users\User\Bot_VigiaSaude_Cidadao"
call .\.venv\Scripts\python.exe servidor.py restart
timeout /t 2 >nul

echo [3/4] Iniciando Central de Atendimento...
cd /d "C:\Users\User\Pictures\Atendimento_VigiaSaude_bot"
call .\.venv\Scripts\python.exe servidor.py restart
timeout /t 2 >nul

echo [4/4] Iniciando Bot Admin...
cd /d "C:\Users\User\Admin_VigiaSaude"
call .\.venv\Scripts\python.exe servidor.py restart
timeout /t 2 >nul

echo.
echo ==========================================
echo    TODOS OS BOTS FORAM INICIADOS COM SUCESSO!
echo ==========================================
pause