@echo off
rem Prompt helper for your Cardiology project - nothing is automated inside ChatGPT.
rem A small window copies each question for you: in ChatGPT press Ctrl+V, Enter, then click Next.
rem
rem For other projects: copy this file, rename it, and change SECTION and PROJECT_URL.
rem SECTION is a file name in the syllabus folder (pulmonary, rheumatic, hematologic,
rem endocrine_metabolic, gastrointestinal, renal, toxicology_allergy, oncologic, treatment_principles).

set "SECTION=cardiovascular"
set "PROJECT_URL=PASTE-YOUR-CARDIOLOGY-PROJECT-ADDRESS-HERE"

rem Extra options, e.g.  --points 13-16,18-38   to skip points you already did
set "OPTIONS="

cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
%PY% prompt_helper.py --section "%SECTION%" --project-url "%PROJECT_URL%" %OPTIONS% %*
if errorlevel 1 pause
