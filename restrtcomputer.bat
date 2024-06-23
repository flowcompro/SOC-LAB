@echo off
echo What is the name of the computer you want to reboot?
set /p input=""
cls
shutdown /r /m \\%input%  /t 001
cls
echo shutting down and restarting %input%
pause

