@echo off
REM Audio to Video with Subtitles Workflow
REM Usage: process_audio.bat <filename_without_extension>

setlocal enabledelayedexpansion

REM Check if filename parameter is provided
if "%~1"=="" (
    echo Please provide a filename without extension
    echo Usage: process_audio.bat ^<filename^>
    exit /b 1
)

REM Clean the filename parameter to remove any trailing spaces
set "WORKING_NAME=%~1"
REM Remove trailing spaces
for /f "tokens=*" %%a in ("%WORKING_NAME%") do set "WORKING_NAME=%%a"

echo Processing %WORKING_NAME%.wav...

REM Step 1: Generate .srt file from audio using Whisper
echo Step 1: Generating subtitles with Whisper...
REM Look for file in current directory first, then in Work_room folder
if exist "%WORKING_NAME%.wav" (
    set "AUDIO_PATH=%WORKING_NAME%.wav"
) else if exist "Work_room\%WORKING_NAME%.wav" (
    set "AUDIO_PATH=Work_room\%WORKING_NAME%.wav"
) else (
    echo Error: Could not find %WORKING_NAME%.wav in current directory or Work_room folder
    exit /b 1
)
REM Use word timestamps to prevent sentence splitting
whisper "%AUDIO_PATH%" --model base --output_format srt --word_timestamps True --append_punctuations "'.,!?;:)"]}"

REM Check if srt file was created
if not exist "%WORKING_NAME%.srt" (
    echo Error: Failed to create subtitle file
    exit /b 1
)

REM Step 2: Convert .srt file to .ass file using FFmpeg
echo Step 2: Converting SRT to ASS format...
ffmpeg -y -i "%WORKING_NAME%.srt" "%WORKING_NAME%.ass"

REM Check if ass file was created
if not exist "%WORKING_NAME%.ass" (
    echo Error: Failed to convert to ASS format
    exit /b 1
)

REM Step 3: Delete the original .srt file
echo Step 3: Removing intermediate SRT file...
del "%WORKING_NAME%.srt"

REM Step 4: Edit the .ass file to update the style
echo Step 4: Updating subtitle style...
powershell -Command "(Get-Content '%WORKING_NAME%.ass') -replace 'Style: Default.*', 'Style: Default,Arial,20,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,1,5,10,10,10,1' | Set-Content '%WORKING_NAME%.ass'"

REM Step 5: Create final MP4 video with subtitles
echo Step 5: Creating final video...
ffmpeg -y -f lavfi -i color=black:s=1280x720 -i "%AUDIO_PATH%" -c:v libx264 -c:a aac -vf "ass=%WORKING_NAME%.ass" -shortest "%WORKING_NAME%.mp4"

echo Processing complete! Output file: %WORKING_NAME%.mp4

endlocal