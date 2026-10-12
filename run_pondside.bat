@echo off
rem Launch Pondside with no console window (errors go to pondside.log)
cd /d "%~dp0"
start "" pyw -3.14 pondside.py
