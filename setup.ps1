<#
.SYNOPSIS
  Instala y comprueba todo lo necesario para clip-ing en Windows 10/11.

.DESCRIPCION
  Uso (desde la carpeta del repositorio):
    powershell -ExecutionPolicy Bypass -File .\setup.ps1
    powershell -ExecutionPolicy Bypass -File .\setup.ps1 -Si           # responde "si" a todo
    powershell -ExecutionPolicy Bypass -File .\setup.ps1 -CPU          # ignora la GPU NVIDIA
    powershell -ExecutionPolicy Bypass -File .\setup.ps1 -SinModelo    # no predescarga el modelo Whisper

  Es idempotente: se puede ejecutar varias veces; cada paso comprueba primero.
  Toda instalacion pide confirmacion (s/n) salvo con -Si.
  Pasos: winget, Python 3.11, ffmpeg, GPU, venv .venv, dependencias, CUDA (cuBLAS/cuDNN),
         modelo Whisper, .env, claude CLI (informativo), clip doctor.
#>
param(
    [switch]$Si,
    [switch]$SinModelo,
    [switch]$CPU
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$script:Hecho = New-Object System.Collections.ArrayList
$script:Pendiente = New-Object System.Collections.ArrayList
$script:TotalPasos = 8

function Paso($n, $txt) { Write-Host ""; Write-Host "[$n/$script:TotalPasos] $txt" -ForegroundColor Cyan }
function Ok($txt)    { Write-Host "[OK] $txt" -ForegroundColor Green }
function Info($txt)  { Write-Host "     $txt" -ForegroundColor Gray }
function Aviso($txt) { Write-Host "[!!] $txt" -ForegroundColor Yellow }
function Falla($txt) { Write-Host "[XX] $txt" -ForegroundColor Red }
function Hecho($txt) { [void]$script:Hecho.Add($txt) }
function Pend($txt)  { [void]$script:Pendiente.Add($txt) }

function Confirmar($msg) {
    if ($Si) { Write-Host "$msg (s/n): s [-Si]" -ForegroundColor Magenta; return $true }
    while ($true) {
        $r = Read-Host "$msg (s/n)"
        if ($r -match '^(s|si|y|yes)$') { return $true }
        if ($r -match '^(n|no)$') { return $false }
    }
}

function Actualizar-Path {
    $m = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($m, $u) | Where-Object { $_ }) -join ';'
}

function Existe($nombre) { return [bool](Get-Command $nombre -ErrorAction SilentlyContinue) }

# Ejecuta un comando nativo y devuelve $true si termina con codigo 0 (sin lanzar excepciones).
function Prueba-Nativo([scriptblock]$bloque) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $null = & $bloque 2>$null; return ($LASTEXITCODE -eq 0) }
    catch { return $false }
    finally { $ErrorActionPreference = $prev }
}

Write-Host "clip-ing :: instalacion" -ForegroundColor White
Write-Host "Carpeta: $PSScriptRoot"

# ---------------------------------------------------------------- [1/8] winget
Paso 1 "Comprobando winget"
$tieneWinget = Existe 'winget'
if ($tieneWinget) {
    Ok "winget disponible"
} else {
    Aviso "winget no esta disponible."
    Info "Instala 'App Installer' desde Microsoft Store (busca 'App Installer' / 'Instalador de aplicacion')"
    Info "y vuelve a ejecutar este script. Se continua con lo que se pueda."
    Pend "Instalar winget (App Installer de Microsoft Store)"
}

# ---------------------------------------------------------------- [2/8] Python
Paso 2 "Python 3.11"
$tienePy311 = Prueba-Nativo { py -3.11 --version }
if ($tienePy311) {
    Ok "ya instalado: $(& py -3.11 --version)"
} elseif (-not $tieneWinget) {
    Falla "Python 3.11 no encontrado y no hay winget. Instalalo desde https://www.python.org/downloads/ (marca 'Add to PATH' y el launcher 'py')."
    Pend "Instalar Python 3.11"
} elseif (Confirmar "Instalar Python 3.11 con winget") {
    winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
    Actualizar-Path
    $tienePy311 = Prueba-Nativo { py -3.11 --version }
    if ($tienePy311) { Ok "Python 3.11 instalado"; Hecho "Python 3.11 instalado" }
    else { Aviso "Python instalado pero 'py -3.11' aun no responde: cierra y abre la terminal y reejecuta el script."; Pend "Reabrir terminal y reejecutar setup.ps1 (Python)" }
} else {
    Pend "Instalar Python 3.11"
}

# ---------------------------------------------------------------- [3/8] ffmpeg
Paso 3 "ffmpeg (con NVENC)"
if (Prueba-Nativo { ffmpeg -version }) {
    Ok "ya instalado (ffmpeg en PATH)"
} elseif (-not $tieneWinget) {
    Falla "ffmpeg no encontrado y no hay winget."
    Pend "Instalar ffmpeg (winget install -e --id Gyan.FFmpeg)"
} elseif (Confirmar "Instalar ffmpeg (Gyan.FFmpeg, build completo con NVENC) con winget") {
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
    Actualizar-Path
    if (Prueba-Nativo { ffmpeg -version }) {
        Ok "ffmpeg instalado"; Hecho "ffmpeg instalado"
    } else {
        $bin = $null
        $base = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
        $dirs = Get-ChildItem -Path $base -Directory -Filter 'Gyan.FFmpeg*' -ErrorAction SilentlyContinue
        foreach ($d in $dirs) {
            $f = Get-ChildItem -Path $d.FullName -Recurse -Filter 'ffmpeg.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($f) { $bin = $f.DirectoryName; break }
        }
        if ($bin) {
            Info "ffmpeg.exe encontrado en: $bin"
            if (Confirmar "Anadir '$bin' al PATH de usuario") {
                $u = [Environment]::GetEnvironmentVariable('Path', 'User')
                if (-not $u) { $u = '' }
                if (($u -split ';') -notcontains $bin) {
                    [Environment]::SetEnvironmentVariable('Path', ($u.TrimEnd(';') + ';' + $bin), 'User')
                }
                Actualizar-Path
                if (Prueba-Nativo { ffmpeg -version }) { Ok "ffmpeg ya esta en PATH"; Hecho "ffmpeg anadido al PATH de usuario" }
                else { Aviso "Cierra y abre la terminal para que el PATH se aplique."; Pend "Reabrir terminal (PATH de ffmpeg)" }
            } else { Pend "Anadir ffmpeg al PATH: $bin" }
        } else {
            Aviso "No se encontro ffmpeg.exe tras instalar. Cierra y abre la terminal y reejecuta el script."
            Pend "Verificar ffmpeg en PATH"
        }
    }
} else {
    Pend "Instalar ffmpeg"
}

# ---------------------------------------------------------------- [4/8] GPU
Paso 4 "GPU NVIDIA"
$usarGpu = $false
$vramMb = 0
if ($CPU) {
    Info "-CPU indicado: se ignora la GPU (modo CPU)."
} elseif (-not (Existe 'nvidia-smi')) {
    Aviso "nvidia-smi no encontrado: no hay GPU NVIDIA o falta el driver. Modo CPU (mas lento)."
    Info "Driver: https://www.nvidia.com/drivers"
    Pend "Instalar driver NVIDIA si se quiere usar GPU"
} else {
    $linea = $null
    try { $linea = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits 2>$null | Select-Object -First 1) } catch { $linea = $null }
    if (-not $linea) {
        Aviso "nvidia-smi no devolvio datos. Modo CPU."
    } else {
        $p = $linea.ToString().Split(',') | ForEach-Object { $_.Trim() }
        if ($p.Count -ge 3) {
            $vramMb = [int]($p[1] -replace '[^\d]', '')
            Ok "GPU: $($p[0]) | VRAM: $vramMb MB | driver: $($p[2])"
            $usarGpu = $true
            $dv = $null
            try { $dv = [version]$p[2] } catch { $dv = $null }
            if ($dv -and $dv -lt [version]'527.41') {
                Aviso "Driver $($p[2]) < 527.41: CUDA 12 (faster-whisper) no funcionara en GPU. Actualiza en https://www.nvidia.com/drivers"
                Pend "Actualizar driver NVIDIA (>= 527.41)"
            }
        } else {
            Aviso "Salida inesperada de nvidia-smi: $linea. Modo CPU."
        }
    }
}
if (-not $usarGpu) { Info "Whisper se ejecutara en CPU (modelo small)." }

# ---------------------------------------------------------------- [5/8] venv
Paso 5 "Entorno virtual .venv"
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$venvListo = $false
if (Test-Path $py) {
    $ErrorActionPreference = 'Continue'
    $v = (& $py --version 2>&1 | Out-String)
    $ErrorActionPreference = 'Stop'
    if ($v -match 'Python 3\.11') { Ok "ya existe .venv ($($v.Trim()))"; $venvListo = $true }
    else { Aviso ".venv existe pero no es Python 3.11 ($($v.Trim())). Borra la carpeta .venv y reejecuta para recrearla."; Pend "Recrear .venv con Python 3.11"; $venvListo = $true }
} elseif ($tienePy311) {
    if (Confirmar "Crear entorno virtual .venv con Python 3.11") {
        py -3.11 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "No se pudo crear .venv" }
        Ok ".venv creado"; Hecho ".venv creado"; $venvListo = $true
    } else { Pend "Crear .venv" }
} else {
    Falla "No hay Python 3.11 disponible: no se puede crear .venv."
}

if (-not $venvListo) {
    Write-Host ""
    Falla "Sin entorno virtual no se puede continuar con los pasos 6-8."
    Write-Host "Pendiente:" -ForegroundColor Yellow
    $script:Pendiente | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    exit 1
}

if (Confirmar "Actualizar pip en .venv") {
    & $py -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { Aviso "No se pudo actualizar pip (se continua)." } else { Ok "pip actualizado" }
}

# ---------------------------------------------------------------- [6/8] dependencias
Paso 6 "Dependencias del proyecto (pip install -e .[full,dev])"
$yaInstalado = Prueba-Nativo { & $py -c "import clipping, faster_whisper, yt_dlp, scenedetect, pytest" }
if ($yaInstalado) {
    Ok "ya instalado (clipping, faster-whisper, yt-dlp, scenedetect, pytest)"
    if (Confirmar "Reejecutar pip install -e para actualizar dependencias") {
        & $py -m pip install -e ".[full,dev]"
        if ($LASTEXITCODE -ne 0) { throw "pip install fallo" }
    }
} elseif (Confirmar "Instalar dependencias (descarga cientos de MB)") {
    & $py -m pip install -e ".[full,dev]"
    if ($LASTEXITCODE -ne 0) { throw "pip install fallo" }
    Ok "dependencias instaladas"; Hecho "Dependencias Python instaladas"
} else {
    Pend "pip install -e `".[full,dev]`""
}

# ---------------------------------------------------------------- [7/8] CUDA
Paso 7 "CUDA 12 / cuDNN 9 para GPU (cuBLAS + cuDNN via pip)"
$chequeoCuda = 'import ctranslate2; print(ctranslate2.get_cuda_device_count())'
if (-not $usarGpu) {
    Info "Sin GPU (o -CPU): se omite."
} else {
    $cudaPkgs = Prueba-Nativo { & $py -c "import importlib.metadata as m; m.version('nvidia-cublas-cu12'); m.version('nvidia-cudnn-cu12')" }
    if ($cudaPkgs) {
        Ok "ya instalado (nvidia-cublas-cu12, nvidia-cudnn-cu12)"
    } elseif (Confirmar "Instalar nvidia-cublas-cu12 y nvidia-cudnn-cu12 9.* (~1 GB)") {
        & $py -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
        if ($LASTEXITCODE -ne 0) { Aviso "Fallo la instalacion de librerias CUDA." ; Pend "Reintentar instalacion cuBLAS/cuDNN" }
        else { Ok "librerias CUDA instaladas"; Hecho "cuBLAS/cuDNN instalados" }
    } else { Pend "Instalar nvidia-cublas-cu12 / nvidia-cudnn-cu12" }

    $ErrorActionPreference = 'Continue'
    try {
        $n = (& $py -c $chequeoCuda 2>$null | Select-Object -First 1)
        if ($n -and ([int]$n -gt 0)) { Ok "ctranslate2 ve $n dispositivo(s) CUDA" }
        else { Aviso "ctranslate2 no ve ninguna GPU CUDA (se usara CPU). Revisa el driver NVIDIA."; Pend "Verificar CUDA en ctranslate2" }
    } catch { Aviso "No se pudo verificar ctranslate2 (aun no instalado?)."; Pend "Verificar CUDA en ctranslate2" }
    $ErrorActionPreference = 'Stop'
}

# ---------------------------------------------------------------- [8/8] Modelo Whisper
Paso 8 "Modelo Whisper"
$modelo = $null
$ErrorActionPreference = 'Continue'
try {
    $rec = (& $py -c 'from clipping.hardware import detectar_gpus, recomendar_whisper as r; x=r(detectar_gpus()); print(x.modelo, x.dispositivo, x.compute_type)' 2>$null | Select-Object -Last 1)
    if ($rec) {
        $t = $rec.ToString().Trim().Split(' ')
        if ($t.Count -ge 3) {
            $modelo = $t[0]
            if ($CPU -and $t[1] -ne 'cpu') { $modelo = 'small'; $t[1] = 'cpu'; $t[2] = 'int8' }
            Ok "Recomendado: modelo=$modelo dispositivo=$($t[1]) compute_type=$($t[2])"
        }
    }
} catch { $modelo = $null }
$ErrorActionPreference = 'Stop'

if (-not $modelo) {
    Aviso "No se pudo determinar el modelo (paquete clipping no instalado?)."
    Pend "Predescargar modelo Whisper"
} elseif ($SinModelo) {
    Info "-SinModelo: se descargara automaticamente en el primer uso."
} else {
    $dl = 'import sys; from faster_whisper import download_model as d; print(d(sys.argv[1]))'
    if (Confirmar "Predescargar modelo Whisper '$modelo' (cache de HuggingFace, fuera del repo)") {
        & $py -c $dl $modelo
        if ($LASTEXITCODE -ne 0) { Aviso "No se pudo descargar el modelo (se bajara en el primer uso)."; Pend "Modelo Whisper $modelo" }
        else { Ok "modelo '$modelo' listo"; Hecho "Modelo Whisper $modelo descargado" }
    } else { Pend "Modelo Whisper $modelo" }
}

# ---------------------------------------------------------------- .env
Write-Host ""
Write-Host "Archivo .env" -ForegroundColor Cyan
if (Test-Path '.env') { Ok ".env ya existe" }
elseif (Test-Path '.env.example') {
    if (Confirmar "Copiar .env.example a .env") { Copy-Item '.env.example' '.env'; Ok ".env creado"; Hecho ".env creado" }
    else { Pend "Crear .env (copiar .env.example)" }
} else { Aviso ".env.example no existe." }

# ---------------------------------------------------------------- claude CLI
Write-Host ""
Write-Host "Claude Code CLI (opcional)" -ForegroundColor Cyan
if (Prueba-Nativo { claude --version }) {
    Ok "claude disponible: $(& claude --version)"
} else {
    Aviso "claude no encontrado: se usara la heuristica (--sin-ia). No se instala automaticamente."
    Info "Para usar IA: npm install -g @anthropic-ai/claude-code   (requiere Node.js)"
    Info "y luego ejecuta 'claude' una vez para iniciar sesion."
    Pend "(Opcional) instalar y autenticar claude CLI"
}

# ---------------------------------------------------------------- doctor
Write-Host ""
Write-Host "Diagnostico final (clip doctor)" -ForegroundColor Cyan
$clip = Join-Path $PSScriptRoot '.venv\Scripts\clip.exe'
if (Test-Path $clip) {
    try { & $clip doctor } catch { Aviso "clip doctor fallo: $($_.Exception.Message)" }
} else {
    Aviso "clip.exe no existe aun (dependencias sin instalar)."
}

# ---------------------------------------------------------------- resumen
Write-Host ""
Write-Host "================ RESUMEN ================" -ForegroundColor White
if ($script:Hecho.Count -gt 0) {
    Write-Host "Hecho:" -ForegroundColor Green
    $script:Hecho | ForEach-Object { Write-Host "  + $_" -ForegroundColor Green }
} else { Write-Host "No se instalo nada nuevo (todo estaba al dia)." -ForegroundColor Green }
if ($script:Pendiente.Count -gt 0) {
    Write-Host "Pendiente:" -ForegroundColor Yellow
    $script:Pendiente | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
}
Write-Host ""
Write-Host "Siguiente:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  clip auto `"C:\ruta\video.mp4`" --n 3 --sin-ia"
