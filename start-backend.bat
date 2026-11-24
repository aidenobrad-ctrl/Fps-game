@echo off
rem Starts Recoil's backend on this PC at http://localhost:5080: accounts, matchmaking, friends, parties.
rem It needs Docker Desktop (it runs the backend's database and Redis) and the .NET 10 SDK;
rem if either is missing this says how to install it.
rem Leave this window open while you play. Close it, or press Ctrl+C, to stop the backend.
setlocal
cd /d "%~dp0"

if exist "backend\src\Recoil.Api\Recoil.Api.csproj" goto havebackend
echo Getting the backend folder from GitHub...
git sparse-checkout add backend
if not exist "backend\src\Recoil.Api\Recoil.Api.csproj" goto nobackend

:havebackend
where docker >nul 2>nul
if errorlevel 1 goto nodocker
docker info >nul 2>nul
if errorlevel 1 goto dockeroff
where dotnet >nul 2>nul
if errorlevel 1 goto nodotnet
dotnet --list-sdks | findstr /b "10." >nul
if errorlevel 1 goto nodotnet

echo Starting the backend's database and Redis in Docker...
docker compose -f backend\docker-compose.yml up -d --wait
if errorlevel 1 goto composefailed

echo.
echo Starting the backend at http://localhost:5080
echo While it runs, emails (verification and password codes) are printed in this window instead of sent.
echo.
set ASPNETCORE_ENVIRONMENT=Development
dotnet run --project backend\src\Recoil.Api --launch-profile Recoil.Api
echo.
echo The backend stopped.
pause
exit /b 0

:nobackend
echo Could not get the backend folder. In this folder, run:
echo     git sparse-checkout add backend
echo and then double-click this file again.
goto end

:nodocker
echo Docker Desktop is not installed. Install it with:
echo     winget install -e --id Docker.DockerDesktop
echo or from https://www.docker.com/products/docker-desktop/ then restart the PC,
echo start Docker Desktop, and double-click this file again.
goto end

:dockeroff
echo Docker Desktop is installed but not running. Start it from the Start menu,
echo wait until it says Engine running, then double-click this file again.
goto end

:nodotnet
echo The .NET 10 SDK is not installed. Install it with:
echo     winget install -e --id Microsoft.DotNet.SDK.10
echo or from https://dotnet.microsoft.com/download then open a new window and double-click this file again.
goto end

:composefailed
echo Docker could not start the database and Redis. The lines above say why.
echo If a port is already in use, another PostgreSQL or Redis is running on this PC: stop it, or use that one.
goto end

:end
echo.
pause
exit /b 1
