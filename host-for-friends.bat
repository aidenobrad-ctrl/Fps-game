@echo off
rem Hosts Recoil on this PC so friends anywhere can play with you: the backend and two
rem matchmaking servers, open to the internet, and Builds\Recoil-for-friends.zip to send them.
rem Build the game first (build.bat). Leave the window open while you play; press Enter in it to stop.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0host-for-friends.ps1"
