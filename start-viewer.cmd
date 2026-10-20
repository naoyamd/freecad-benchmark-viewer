@echo off
pushd "%~dp0"
node server.mjs --open
if errorlevel 1 pause
popd
