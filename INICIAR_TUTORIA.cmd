@echo off
setlocal
pushd "%~dp0"
powershell -NoProfile -Command "& ([scriptblock]::Create([IO.File]::ReadAllText((Join-Path (Get-Location) 'scripts\start_local.ps1')))) -ProjectDirectory (Get-Location).Path"
set "TUTORIA_RESULT=%ERRORLEVEL%"
if not "%TUTORIA_RESULT%"=="0" echo No se completo el inicio. Conserva el mensaje de error para revisarlo.
pause
popd
exit /b %TUTORIA_RESULT%
