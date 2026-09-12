@echo off
chcp 65001 >nul 2>&1
title TrackImage
:: v4.33: everything TrackImage owns now lives one level down, in
:: Trackimage_files. This launcher is the only thing the user should see in the
:: folder they unpacked, so it goes there itself and works from there.
set "TIDIR=%~dp0Trackimage_files"
if not exist "%TIDIR%\app.py" (
  echo  [ERROR] Trackimage_files\app.py not found next to this launcher.
  echo          Unpack the whole ZIP, keeping start-windows.bat and the
  echo          Trackimage_files folder side by side.
  pause & exit /b 1
)
cd /d "%TIDIR%"
:: v4.51: these live under Userdata now. Making them here, where they used to
:: be, made TrackImage take two empty folders for an older layout and back
:: them up as .pre449 on a brand new install.
if not exist "Userdata" md "Userdata"
if not exist "Userdata\Logs" md "Userdata\Logs"
if not exist "Userdata\Databank" md "Userdata\Databank"
echo.
echo  ========================================
echo   TrackImage v4.63 - Setup ^& Start
echo  ========================================
echo.
python --version >nul 2>&1
if errorlevel 1 ( echo  [ERROR] Python not found! & pause & exit /b 1 )
:: v4.36: TrackImage needs 3.10 or newer. Older ones get through the setup and
:: fail later on syntax, which reads like a broken download rather than an old
:: interpreter.
python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if errorlevel 1 (
  echo  [WARN] This Python is older than 3.10. TrackImage is built for 3.10+
  echo         and will probably not start. Installing a current Python from
  echo         python.org and running this file again is the fix.
  echo.
)
if not exist "venv" ( echo  [1/3] Creating virtual environment... & python -m venv venv )
call venv\Scripts\activate.bat
:: v3.76: everything TrackImage needs lives in THIS venv. Blocking the per-user
:: site-packages stops an older "pip install --user nvidia-cudnn-cu12" elsewhere
:: on the machine from leaking in - mixing two cuDNN versions broke GPU tagging.
set "PYTHONNOUSERSITE=1"
set "ILOG=%TIDIR%\Userdata\Logs\install.log"
>"%ILOG%" echo TrackImage setup log
:: v4.36: bring pip, setuptools and wheel up to date BEFORE anything else is
:: fetched. A fresh virtual environment on Python 3.12 contains pip and nothing
:: more -- no setuptools, no wheel. Packages that ship only a source archive and
:: no pyproject.toml then fall back to the old setup.py route, which needs
:: exactly the setuptools that is not there. proxy_tools, which comes in with
:: pywebview, is one of them: on one machine pip printed a deprecation notice
:: and died mid-install, and the start went quiet from there. Three seconds here
:: instead of a first run that ends in silence.
"%TIDIR%\venv\Scripts\python.exe" "%TIDIR%\launcher_check.py" bootstrap
call :say " [2/3] Checking dependencies..."
:: v4.14: say which package is being fetched. This step used to run silently, so a
:: first start looked frozen for minutes and a package that failed to download
:: completely left no trace at all -- one user lost a single CUDA DLL that way and
:: only found out much later, through an unrelated crash.
:: v4.21: every package is named together with what it is FOR. Somebody watching
:: a fresh install should be able to see that nothing here is a mystery.
call :dep flask          "the local web server TrackImage runs on"
call :dep pillow         "reading and resizing images"
call :dep pillow-heif    "iPhone HEIC photos"
call :dep imageio-ffmpeg "thumbnails for video files"
call :dep watchdog       "noticing when files change on disk"
call :dep send2trash     "deleting to the Recycle Bin instead of for good"
call :dep numpy          "the maths behind duplicate detection"
call :dep pywebview      "the app window itself, instead of a browser tab"
call :dep pywin32        "dragging files out of the window into other programs"
call :dep qrcode         "the scan-me code for opening TrackImage on a phone"
goto :deps_done

:dep
:: v4.22: no ( ) block in here, and no brackets in the descriptions either.
:: v4.21 wrapped these echoes in if(...)else(...). cmd expands %WHY% BEFORE it
:: parses the block, so the ")" inside "the app window (instead of a browser
:: tab)" closed the block early and the rest of the script never ran -- the
:: packages installed and then no window ever appeared. Plain gotos cannot do
:: that to us.
setlocal
set "PKG=%~1"
set "WHY=%~2"
python -c "import importlib.util,sys; n='%PKG%'.replace('-','_'); sys.exit(0 if importlib.util.find_spec({'pillow':'PIL','pillow_heif':'pillow_heif','pywebview':'webview','pywin32':'win32com','imageio_ffmpeg':'imageio_ffmpeg','send2trash':'send2trash'}.get(n,n)) else 1)" >nul 2>&1
if not errorlevel 1 goto :dep_have
call :say "       installing %PKG% - %WHY% ..."
python -m pip install %PKG% -q --disable-pip-version-check
if errorlevel 1 set "DEPFAIL=%DEPFAIL% %PKG%"
if errorlevel 1 call :say "       [!] %PKG% did not install"
goto :dep_out
:dep_have
call :say "       %PKG% ok - %WHY%"
:dep_out
:: v4.36: carry the list of failures back out of the subroutine. %DEPFAIL% is
:: expanded while the line is parsed, which happens before endlocal runs, so the
:: inner value survives into the outer scope.
endlocal & set "DEPFAIL=%DEPFAIL%"
goto :eof

:say
:: v4.22: onto the screen and into install.log, so the Settings console can show
:: afterwards what happened during setup.
echo %~1
>>"%ILOG%" echo %~1
goto :eof

:deps_done

:: v4.36: check what is actually importable rather than trusting that pip said
:: nothing. A package can install and still be unusable, and until now the only
:: sign of that was a window that never opened.
echo.
"%TIDIR%\venv\Scripts\python.exe" "%TIDIR%\launcher_check.py" deps
if errorlevel 1 (
  echo.
  echo  [ERROR] TrackImage cannot start until the packages listed above are
  echo          installed. The full setup output is in Userdata\Logs\install.log.
  echo.
  pause
  exit /b 1
)
if defined DEPFAIL call :say "       note: pip reported trouble with:%DEPFAIL%"
echo.

:: v3.85: the ONNX runtime is NOT installed here any more. It only arrives when the
:: user clicks "Install auto-tagging" in Settings, which keeps a fresh install that
:: never tags at ~700 MB instead of ~3.9 GB. An already installed runtime is left
:: alone -- app.py detects it on import, exactly as before.
echo  [3/3] Starting TrackImage...
echo.
:: Friendly hostname: map trackimage -> 127.0.0.1 so http://trackimage:5001 works (run as admin once). localhost always works.
set "URLHOST=localhost"
set "HF=%SystemRoot%\System32\drivers\etc\hosts"
findstr /I /C:"trackimage" "%HF%" >nul 2>&1 && set "URLHOST=trackimage"
if /I "%URLHOST%"=="localhost" ( (echo 127.0.0.1 trackimage>>"%HF%") 2>nul && set "URLHOST=trackimage" )
:: v4.0: TrackImage opens its own window, so the console is no longer needed once
:: setup is done. pythonw.exe starts without one; app.py redirects stdout/stderr to
:: trackimage.log, so nothing is lost. The console stays for the setup above -- a
:: first run installs packages for minutes and needs to show that it is working.
echo  Starting TrackImage...
if not exist "%TIDIR%\venv\Scripts\pythonw.exe" (
  echo  [WARN] pythonw.exe missing in the venv - starting with the console instead.
  python app.py
  if errorlevel 1 ( echo. & echo  [ERROR] Server crashed! & pause )
  exit /b
)
start "" "%TIDIR%\venv\Scripts\pythonw.exe" "%TIDIR%\app.py"
:: v4.01: verify it actually came up. Window mode has no console, so a crash used
:: to be completely silent - the window flashed and nothing happened. If nothing
:: is listening on 5001 after ~15 s, the app is restarted visibly so the error
:: ends up on screen instead of nowhere.
:: v4.05: the readiness check is done by Python, not by batch string juggling.
:: netstat piped into findstr was two attempts and two bugs; a socket connect is
:: one line and cannot be misparsed.
echo  Waiting for the window to appear...
:: v4.16: one interpreter does the whole wait. This used to start a fresh Python
:: up to twenty times over with a ping between each, so most of the delay after
:: the console closed was the waiting itself -- and it happened in silence.
:: any() stops at the first successful connect; a failed one sleeps and moves on.
:: v4.36: ask who is on the port, not merely whether somebody is. The old check
:: was satisfied by any listener at all -- including a leftover process from a
:: failed attempt -- and then closed the console without a word, which is the
:: single most confusing thing this script has ever done.
"%TIDIR%\venv\Scripts\python.exe" "%TIDIR%\launcher_check.py" wait 35
if errorlevel 2 goto :other_instance
if errorlevel 1 goto :no_start
exit /b

:other_instance
echo.
echo  TrackImage is already running from an earlier start. Opening it instead
echo  of starting a second copy.
echo.
echo      http://%URLHOST%:5001
echo.
start "" "http://%URLHOST%:5001"
echo  To start this version instead, close that window - or end pythonw.exe in
echo  the Task Manager - and run this file again.
echo.
pause
exit /b

:no_start
echo.
echo  [ERROR] TrackImage did not come up in window mode.
echo.
echo  If Windows showed an error box about pythonw.exe instead, the program was
echo  stopped by Windows itself - not by a Python error - so Userdata\Logs\trackimage.log
echo  will be empty for that attempt. That is almost always a damaged native library.
echo  This test names the usual culprit:
echo.
echo      venv\Scripts\python.exe -c "import onnxruntime"
echo.
echo  If that crashes, remove it and TrackImage starts again without tagging:
echo.
echo      venv\Scripts\python.exe -m pip uninstall -y onnxruntime-gpu onnxruntime-directml onnxruntime
echo.
echo  ---- last lines of Userdata\Logs\trackimage.log ----
powershell -NoProfile -Command "if (Test-Path 'Userdata\Logs\trackimage.log') { Get-Content -Tail 25 'Userdata\Logs\trackimage.log' }" 2>nul
echo  --------------------------------------
echo.
echo  Restarting with the console visible so the error can be read:
echo.
python app.py
:: v4.36: whatever happened, this window stays open. It used to close on a clean
:: exit as well, and a start that ended in half a second looked like nothing had
:: happened at all.
echo.
pause
exit /b
