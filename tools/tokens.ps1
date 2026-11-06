#===============================================================================
# tokens.ps1 — токены для бинарных (ironman) сейвов CK3
#
#   .\tokens.ps1 check   # что с токенами сейчас
#   .\tokens.ps1 get     # запустить игру, дождаться oos_dump и забрать файл
#   .\tokens.ps1 test    # проверить токены на свежем автосейве
#===============================================================================
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('check', 'get', 'test')]
    [string]$Mode = 'check',

    [int]$TimeoutMinutes = 20,

    [string]$Game = '',
    [string]$Extractor = '',
    [string]$Work = ''
)

$ErrorActionPreference = 'Stop'

# Пути берутся из параметров или переменных окружения — ничего личного в скрипте.
#   CK3_GAME       — папка с игрой (там binaries\ck3.exe)
#   CK3_EXTRACTOR  — путь к ck3_history_extractor.exe
#   CK3_WORK       — рабочая папка для проверки токенов
$Documents = Join-Path $env:USERPROFILE 'Documents\Paradox Interactive\Crusader Kings III'
$Tokens = Join-Path $Documents 'oos\dummy\tokens_1.tok'
$Saves = Join-Path $Documents 'save games'

$GameRoot = if ($Game) { $Game } elseif ($env:CK3_GAME) { Split-Path $env:CK3_GAME -Parent } else { '' }
$GameExe = if ($GameRoot) { Join-Path $GameRoot 'binaries\ck3.exe' } else { '' }
$GameBranch = if ($GameRoot) { Join-Path $GameRoot 'clausewitz_branch.txt' } else { '' }
$Extractor = if ($Extractor) { $Extractor } elseif ($env:CK3_EXTRACTOR) { $env:CK3_EXTRACTOR } else { '' }
$ExtractorDir = if ($Extractor) { Split-Path $Extractor -Parent } else { '' }
$Work = if ($Work) { $Work } elseif ($env:CK3_WORK) { $env:CK3_WORK } else { Join-Path $env:TEMP 'ck3-tokens' }

function Show-State {
    Write-Host ''
    Write-Host 'Токены:' -ForegroundColor Cyan
    if (Test-Path $Tokens) {
        $file = Get-Item $Tokens
        $lines = (Get-Content $Tokens | Measure-Object -Line).Lines
        Write-Host ("  {0}  {1:N0} КБ, {2:N0} строк, изменён {3}" -f $Tokens, ($file.Length / 1KB), $lines, $file.LastWriteTime)
    }
    else {
        Write-Host "  нет файла $Tokens" -ForegroundColor Yellow
    }

    if (Test-Path $GameBranch) {
        Write-Host ("  ветка игры: {0}" -f (Get-Content $GameBranch -Raw).Trim())
    }

    $newest = Get-ChildItem $Saves -File -Filter '*.ck3' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($newest) {
        $binary = $false
        $fs = [System.IO.File]::OpenRead($newest.FullName)
        $head = New-Object byte[] 4
        $null = $fs.Read($head, 0, 4)
        $fs.Close()
        $binary = -not ($head[0] -eq 0x50 -and $head[1] -eq 0x4B)
        Write-Host ("  свежий сейв: {0} ({1:N1} МБ, {2}, {3})" -f $newest.Name, ($newest.Length / 1MB), $(if ($binary) { 'бинарный' } else { 'текстовый' }), $newest.LastWriteTime)
        if (Test-Path $Tokens) {
            $stale = (Get-Item $Tokens).LastWriteTime -lt $newest.LastWriteTime
            if ($stale -and $binary) {
                Write-Host '  ВЕРДИКТ: токены старше сейва — бинарный сейв может не разобраться' -ForegroundColor Yellow
            }
            elseif ($stale) {
                Write-Host '  ВЕРДИКТ: токены старше сейва, но сейв текстовый — токены не нужны' -ForegroundColor DarkGray
            }
            else {
                Write-Host '  ВЕРДИКТ: токены свежее сейва' -ForegroundColor Green
            }
        }
        return $newest
    }
    Write-Host '  сейвов не найдено' -ForegroundColor Yellow
    return $null
}

function Invoke-Test {
    param($Save)
    if (-not $Save) { $Save = Get-ChildItem $Saves -File -Filter '*.ck3' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 }
    if (-not $Save) { Write-Host 'Нечего проверять: нет сейвов' -ForegroundColor Yellow; return }
    if (-not (Test-Path $Extractor)) { Write-Host "Нет экстрактора: $Extractor" -ForegroundColor Red; return }

    New-Item -ItemType Directory -Path $Work -Force | Out-Null
    $log = Join-Path $Work 'extract.log'
    Write-Host ''
    Write-Host ("Проверяю токены на {0}…" -f $Save.Name) -ForegroundColor Cyan

    Push-Location $ExtractorDir
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Extractor $Save.FullName -o $Work -n --no-vis 2>&1 | Out-File -FilePath $log -Encoding UTF8
    }
    finally {
        $ErrorActionPreference = $previous
        Pop-Location
    }

    $text = Get-Content $log -Raw -ErrorAction SilentlyContinue
    if ($text -match 'UnknownToken\((\d+)\)') {
        Write-Host ("  ОШИБКА: неизвестный токен {0} — токены устарели, нужен oos_dump" -f $Matches[1]) -ForegroundColor Red
        return $false
    }
    if ($text -match 'Loaded (\d+) binary-save tokens') {
        Write-Host ("  загружено токенов: {0}" -f $Matches[1]) -ForegroundColor DarkGray
    }
    if ($text -match 'Panic|embarrassing') {
        Write-Host '  падение экстрактора — смотрите лог' -ForegroundColor Red
        Write-Host "  $log" -ForegroundColor DarkGray
        return $false
    }
    Write-Host '  ОК: сейв разобран без ошибок токенов' -ForegroundColor Green
    return $true
}

function Invoke-Get {
    if (-not (Test-Path $GameExe)) { Write-Host "Нет игры: $GameExe" -ForegroundColor Red; return }
    $before = if (Test-Path $Tokens) { (Get-Item $Tokens).LastWriteTime } else { [datetime]::MinValue }

    Write-Host ''
    Write-Host 'Сейчас откроется Crusader Kings III в режиме отладки.' -ForegroundColor Cyan
    Write-Host 'В игре:'
    Write-Host '  1. Откройте консоль клавишей ` (тильда, слева от единицы).'
    Write-Host '  2. Введите:  oos_dump'
    Write-Host '  3. Дождитесь надписи в консоли и выйдите из игры.'
    Write-Host 'Скрипт сам заберёт файл, как только игра его перезапишет.'
    Write-Host ''

    Start-Process -FilePath $GameExe -ArgumentList '-debug_mode' -WorkingDirectory (Split-Path $GameExe -Parent)

    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        if ((Test-Path $Tokens) -and (Get-Item $Tokens).LastWriteTime -gt $before) {
            Start-Sleep -Seconds 2
            Copy-Item $Tokens (Join-Path $ExtractorDir 'tokens_1.tok') -Force
            Write-Host ''
            Write-Host ("Токены обновлены: {0}" -f (Get-Item $Tokens).LastWriteTime) -ForegroundColor Green
            Write-Host ("Скопированы к экстрактору: {0}" -f (Join-Path $ExtractorDir 'tokens_1.tok'))
            Invoke-Test | Out-Null
            return
        }
    }
    Write-Host ''
    Write-Host 'Файл токенов не обновился за отведённое время.' -ForegroundColor Yellow
    Write-Host 'Проверьте, что в консоли действительно выполнен oos_dump.' -ForegroundColor Yellow
}

$save = Show-State
switch ($Mode) {
    'check' { }
    'test' { Invoke-Test -Save $save | Out-Null }
    'get' { Invoke-Get }
}
