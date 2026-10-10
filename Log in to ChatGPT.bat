@echo off
rem Opens normal Google Chrome with the script's own profile so you can log in to ChatGPT once
rem (works with "Continue with Google" too). Log in, then CLOSE that Chrome window before
rem running "Run Cardiology.bat" - the script reuses this login.
cd /d "%~dp0"
start "" chrome --user-data-dir="%~dp0chrome-profile" https://chatgpt.com
