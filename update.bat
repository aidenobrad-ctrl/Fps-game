@echo off
rem Gets the newest version of Recoil from GitHub into this folder.
rem Close Unity (or at least stop Play mode), then double-click this file.
rem Everything is in one block so Windows reads it all before git changes any file, this one included.
(
  cd /d "%~dp0"
  where git >nul 2>nul
  if errorlevel 1 (
    echo Git is not installed on this PC.
    echo Install it with:  winget install --id Git.Git -e --source winget
    echo or from https://git-scm.com/download/win, then double-click this file again.
    echo.
    pause
    exit /b 1
  )
  echo Getting the newest Recoil...
  echo.
  git stash
  git pull
  if errorlevel 1 (
    echo.
    echo The update did not go through. The lines above say why.
  ) else (
    echo.
    echo Done. Open the game folder in Unity Hub, or click back into Unity so it imports the new files.
    echo The bottom line of the game's main menu names the update you now have.
  )
  echo.
  pause
)
