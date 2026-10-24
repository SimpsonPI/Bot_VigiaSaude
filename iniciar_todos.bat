@echo off
title Iniciando Bots VigiaSaude
color 0A
echo ==========================================
echo    INICIANDO TODOS OS BOTS VIGIASAUDE
echo ==========================================
echo.

echo [1/4] Iniciando VS Bot...
start "VS Bot" cmd /k "cd /d C:\Users\User\Pictures\Bot_VigiaSaude && .\.venv\Scripts\python.exe servidor.py"
timeout /t 3 >nul

echo [2/4] Iniciando Bot Cidadao...
start "Bot Cidadao" cmd /k "cd /d C:\Users\User\Bot_VigiaSaude_Cidadao && .\.venv\Scripts\python.exe servidor.py"
timeout /t 3 >nul

echo [3/4] Iniciando Central de Atendimento...
start "Atendimento" cmd /k "cd /d C:\Users\User\Pictures\Atendimento_VigiaSaude_bot && .\.venv\Scripts\python.exe servidor.py"
timeout /t 3 >nul

echo [4/4] Iniciando Bot Admin...
start "Admin" cmd /k "cd /d C:\Users\User\Admin_VigiaSaude && .\.venv\Scripts\python.exe servidor.py"
timeout /t 3 >nul

echo.
echo ==========================================
echo    TENTATIVA DE INICIALIZACAO CONCLUIDA
echo ==========================================
echo As janelas dos bots foram abertas. Se fecharem, veja o erro nelas.
pause