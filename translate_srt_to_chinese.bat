@echo off
REM Translate SRT file to Chinese (zh-tw)
REM Usage: translate_srt_to_chinese.bat <filename_without_extension>

setlocal enabledelayedexpansion

REM Check if filename parameter is provided
if "%~1"=="" (
    echo Please provide a filename without extension
    echo Usage: translate_srt_to_chinese.bat ^<filename^>
    exit /b 1
)

set "WORKING_NAME=%~1"

echo Translating %WORKING_NAME%.srt to Chinese (zh-tw)...

REM Check if SRT file exists
if not exist "%WORKING_NAME%.srt" (
    echo Error: SRT file %WORKING_NAME%.srt not found
    exit /b 1
)

REM Translate the SRT file using Python script
echo Translating subtitles with Google Translate...
python translate_srt.py "%WORKING_NAME%.srt" "%WORKING_NAME%_zh-tw.srt"

REM Check if translation was successful
if exist "%WORKING_NAME%_zh-tw.srt" (
    echo Translation complete! Output file: %WORKING_NAME%_zh-tw.srt
) else (
    echo Error: Failed to create translated SRT file
    exit /b 1
)

endlocal