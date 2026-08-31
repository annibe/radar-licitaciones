@echo off
title Organizador de anexos - Radar de licitaciones
cd /d "%~dp0"
py "scripts\organizador.py"
if errorlevel 1 (
  echo.
  echo Algo fallo. Copia el texto de arriba y muestraselo a Claude.
  pause
)
