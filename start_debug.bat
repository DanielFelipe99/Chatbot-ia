@echo off
echo ======================================
echo   MODO DEBUG - Chatbot
echo ======================================
echo.

:: Verificar estructura de archivos
echo Verificando estructura de archivos...
if exist "app/app.py" (
    echo [OK] app\app.py encontrado
) else (
    echo [ERROR] No se encuentra app\app.py
    echo Directorio actual: %CD%
    dir /B
    pause
    exit /b 1
)

if exist "api.php" (
    echo [OK] api.php encontrado
) else (
    echo [ERROR] No se encuentra api.php
    pause
    exit /b 1
)

:: Limpiar puertos
echo.
echo Limpiando puertos...
taskkill /F /IM php.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul

:: Iniciar servicios en ventanas separadas para ver errores
echo.
echo Iniciando servicios en ventanas separadas...
echo.

:: PHP en ventana nueva
echo Iniciando PHP API...
start "PHP API - Puerto 8000" cmd /k "php -S localhost:8000 api.php"
timeout /t 3 /nobreak >nul

:: Flask en ventana nueva
echo Iniciando Flask...
start "Flask - Puerto 5000" cmd /k "cd app && python app.py"
timeout /t 5 /nobreak >nul

echo.
echo ======================================
echo Si todo funciona correctamente:
echo   - PHP API: http://localhost:8000
echo   - Flask:   http://localhost:5000
echo ======================================
echo.
echo Las ventanas muestran los logs en tiempo real.
echo Cierra esta ventana para mantener los servicios corriendo.
echo.
pause