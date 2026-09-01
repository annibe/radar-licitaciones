@echo off
chcp 65001 >nul
title Bajar anexos - Radar de licitaciones
cd /d "%~dp0"
py "scripts\anexos.py"
if errorlevel 1 (
  echo.
  echo Algo fallo. Copia el texto de arriba y muestraselo a Claude.
)
echo.
pause
