@echo off
REM ========================================================
REM z_blender_BATCH_metal_ingot_render.py Batch Runner
REM ========================================================
REM This batch file runs the Metal Ingot Batch Renderer script
REM in Blender's background mode for automated rendering.
REM ========================================================

echo Starting Metal Ingot Batch Renderer...
echo.

REM Set the path to Blender executable and script
set BLENDER_PATH="C:\Program Files\Blender Foundation\Blender 4.0\blender.exe"
set SCRIPT_PATH="%~dp0z_blender_BATCH_metal_ingot_render.py"
set BLENDER_PROJECT_DIR="d:\BLENDER"

REM Change to the Blender project directory
cd %BLENDER_PROJECT_DIR%
echo Working directory set to: %BLENDER_PROJECT_DIR%

REM Run Blender in background mode with the script
%BLENDER_PATH% --background --python %SCRIPT_PATH%

echo.
echo Batch rendering complete!
echo Output files saved to: %~dp0metal_ingot_renders
echo.

pause
