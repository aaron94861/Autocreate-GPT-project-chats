@echo off
rem Creates one ChatGPT chat per Cardiology syllabus point (13-38) in your Cardiology project
rem and asks the 6 questions in each. Safe to run again: finished points are skipped.
rem
rem 1) Open your Cardiology project in ChatGPT, copy the address bar, paste it below.
rem 2) Double-click this file. First time only: log in to ChatGPT in the window that opens.
rem
rem For other projects: copy this file, rename it, and change SECTION and PROJECT_URL.
rem SECTION is a file name in the syllabus folder (pulmonary, rheumatic, hematologic,
rem endocrine_metabolic, gastrointestinal, renal, toxicology_allergy, oncologic, treatment_principles).

set "SECTION=cardiovascular"
set "PROJECT_URL=PASTE-YOUR-CARDIOLOGY-PROJECT-ADDRESS-HERE"

rem Extra options, e.g.  --points 17   or   --points 13-20   or   --max-points 10
set "OPTIONS=--save-replies"

cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul
if not errorlevel 1 set "PY=py"
%PY% syllabus_prompter.py --section "%SECTION%" --project-url "%PROJECT_URL%" %OPTIONS% %*
pause
