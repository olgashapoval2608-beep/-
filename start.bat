@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Calorie Bot

where python >nul 2>nul
if errorlevel 1 goto nopython

if exist ".venv\installed.ok" goto checkenv
echo === Перший запуск: встановлюю бота, це займе 2-5 хвилин ===
python -m venv .venv
if errorlevel 1 goto nopython
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto installfail
echo ok> ".venv\installed.ok"

:checkenv
if exist ".env" goto run
copy ".env.example" ".env" >nul
echo.
echo === Створено файл .env ===
echo Зараз відкриється Блокнот. Впиши TELEGRAM_BOT_TOKEN і GEMINI_API_KEY,
echo збережи файл через Ctrl+S, закрий Блокнот і знову запусти start.bat
notepad ".env"
pause
exit /b 0

:run
echo === Бот запущений. Не закривай це вікно, поки користуєшся ботом ===
echo Щоб зупинити бота, натисни Ctrl+C або просто закрий вікно.
echo.
".venv\Scripts\python.exe" -m bot.main
echo.
echo Бот зупинився. Якщо вище є помилка, дивись розділ Якщо щось не так в інструкції.
pause
exit /b 0

:nopython
echo Python не знайдено. Встанови його з https://www.python.org/downloads/
echo і обовязково постав галочку Add python.exe to PATH. Потім запусти start.bat знову.
pause
exit /b 1

:installfail
echo Не вдалося встановити бібліотеки. Перевір інтернет і запусти start.bat ще раз.
pause
exit /b 1
