@echo off
echo Iniciando os 3 bots...
echo.

cd /d "C:\Users\User\Pictures\Bot_VigiaSaude"
start "Bot VigiaSaude" cmd /k ".venv\Scripts\activate.bat && python servidor.py start"

timeout /t 3 /nobreak >nul

cd /d "C:\Users\User\Pictures\Atendimento_VigiaSaude_bot"
start "Central VigiaSaude" cmd /k ".venv\Scripts\activate.bat && python servidor.py start"

timeout /t 3 /nobreak >nul

cd /d "C:\Users\User\Admin_VigiaSaude"
start "Admin VigiaSaude" cmd /k ".venv\Scripts\activate.bat && python servidor.py start"

echo.
echo ✅ Os 3 bots foram iniciados em janelas separadas.
timeout /t 5