@echo off
title Radar de licitaciones - Mercado Publico
cd /d "%~dp0"
py "scripts\abrir.py"
if errorlevel 1 (
  echo.
  echo Algo fallo. Copia el texto de arriba y muestraselo a Claude.
  pause
)
