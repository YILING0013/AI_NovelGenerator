<#
    Viet Tieu Thuyet - bat/tat toan bo stack bang mot lenh.

    Duoc goi boi start-all.bat / stop-all.bat / status.bat.
    Tham so:
      start   : khoi dong MongoDB -> backend -> frontend, mo trinh duyet
      stop    : dung frontend -> backend -> MongoDB (dao nguoc)
      restart : stop roi start
      status  : in trang thai tung dich vu
      logs    : in 30 dong cuoi cua tung log
    Khi can doi cong / duong dan, setting bien moi truong:
      VT_BACKEND_PORT VT_FRONTEND_PORT VT_MONGO_HOME VT_MONGO_DATA
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "restart", "status", "logs", "build")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# ---------------------------------------------------------------- duong dan
$RepoRoot = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $RepoRoot
$RuntimeDir = Join-Path $WorkspaceRoot "runtime"
$LogDir = Join-Path $RuntimeDir "logs"
$PidDir = Join-Path $RuntimeDir "pids"

$BackendPort = if ($env:VT_BACKEND_PORT) { [int]$env:VT_BACKEND_PORT } else { 8200 }
$FrontendPort = if ($env:VT_FRONTEND_PORT) { [int]$env:VT_FRONTEND_PORT } else { 3300 }
$MongoPort = 27017
# GT trong default cua WiredTiger (~50% RAM) khien mongod 8.0 chai khi mo lai
# thu muc du lieu da su dung tren may RAM thap -> co dinh 1 GB (du dung cho dev).
$MongoCacheGB = if ($env:VT_MONGO_CACHE_GB) { $env:VT_MONGO_CACHE_GB } else { "1" }

$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$NpmCmd = if (Get-Command npm.cmd -ErrorAction SilentlyContinue) { (Get-Command npm.cmd).Source } else { "D:\nodejs\npm.cmd" }
$FrontendDir = Join-Path $RepoRoot "frontend"
$RsInitScript = Join-Path $RepoRoot "tools\rs_init.py"
$MongoStopScript = Join-Path $RepoRoot "tools\mongo_stop.py"

function Find-Mongod {
    <#
        Tra ve danh sach mongod.exe theo thu uu tien.
        May cu (Ivy Bridge, khong co AVX2) khong the chay MongoDB >= 6.0: no crash
        "illegal instruction" khi mo lai du lieu. Vi vay uu tien ban gan nhat da
        duoc chon lan truoc (runtime\mongodb-bin.txt), cac ban khac la phương án fallback.
    #>
    $list = @()
    $preferred = Join-Path $PidDir "..\mongodb-bin.txt"
    if (Test-Path $preferred) {
        $saved = (Get-Content $preferred -Raw).Trim()
        if ($saved -and (Test-Path $saved)) { $list += (Resolve-Path $saved).Path }
    }
    if ($env:VT_MONGO_HOME) { $list += (Join-Path $env:VT_MONGO_HOME "bin\mongod.exe") }
    $tools = Join-Path $WorkspaceRoot "tools"
    # Thu tu uu tien: ban 5.0 (tools\m5) truoc, roi moi den cac ban moi hon.
    # Ly do: may Intel Ivy Bridge (i7-3xxxU) khong co AVX2 -> MongoDB >= 6.0
    # crash "illegal instruction" khi MO LAI thu muc du lieu da dung, va du lieu
    # do MongoDB 8.0 tao ra khong the mo bang 5.0. Chon ban cu nhat chay on dinh
    # de toan bo vong doi du lieu nam trong mot dinh dang.
    # May moi hon: ep ban khac bang VT_MONGO_HOME=C:\...\mongodb-win32-x86_64-windows-8.0.38
    $list += (Join-Path $tools "m5\bin\mongod.exe")
    $list += (Join-Path $tools "m\bin\mongod.exe")
    Get-ChildItem $tools -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | ForEach-Object {
        $list += (Join-Path $_.FullName "bin\mongod.exe")
    }
    $list += (Join-Path $tools "mongodb\bin\mongod.exe")
    $list += "e:\laragon\bin\mongodb\bin\mongod.exe"
    return ($list | Where-Object { Test-Path $_ } | ForEach-Object { (Resolve-Path $_).Path } | Select-Object -Unique)
}

$MongodCandidates = Find-Mongod
$MongoData = if ($env:VT_MONGO_DATA) { $env:VT_MONGO_DATA } else { Join-Path $WorkspaceRoot "mongodata" }
$MongoBinMark = Join-Path $RuntimeDir "mongodb-bin.txt"

foreach ($d in @($RuntimeDir, $LogDir, $PidDir)) { if (-not (Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null } }

# ---------------------------------------------------------------- tien nghi
function Test-Port([int]$Port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        $ok = $task.Wait(800) -and $client.Connected
        $client.Close()
        return $ok
    } catch { return $false }
}

function Get-StoredPid([string]$Name) {
    $file = Join-Path $PidDir "$Name.pid"
    if (-not (Test-Path $file)) { return $null }
    $raw = (Get-Content $file -Raw).Trim()
    $p = 0
    if (-not [int]::TryParse($raw, [ref]$p)) { return $null }
    if (Get-Process -Id $p -ErrorAction SilentlyContinue) { return $p }
    return $null
}

function Start-Daemon([string]$Name, [string]$Exe, [string]$Arguments, [string]$WorkDir, [int]$Port, [string]$Label) {
    if (Test-Port $Port) {
        Write-Host ("  [OK]   {0} dang chay san o cong {1}" -f $Label, $Port)
        return $true
    }
    $log = Join-Path $LogDir "$Name.log"
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Exe
    $psi.Arguments = $Arguments
    $psi.WorkingDirectory = $WorkDir
    $psi.UseShellExecute = $true
    $psi.WindowStyle = "Hidden"
    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
    } catch {
        Write-Host ("  [LOI]  khong khoi dong duoc {0}: {1}" -f $Label, $_.Exception.Message) -ForegroundColor Red
        Write-Host ("         xem log: {0}" -f $log)
        return $false
    }
    Set-Content -Path (Join-Path $PidDir "$Name.pid") -Value $proc.Id -Encoding ascii
    $deadline = (Get-Date).AddSeconds(75)
    while ((Get-Date) -lt $deadline -and -not (Test-Port $Port)) {
        if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 800 } else { break }
    }
    if (Test-Port $Port) {
        Write-Host ("  [OK]   {0} (PID {1}, cong {2})" -f $Label, $proc.Id, $Port)
        return $true
    }
    Write-Host ("  [LOI]  {0} khong nghe o cong {1} (tien trinh {2} da chet hoac treo)" -f $Label, $Port, $proc.Id) -ForegroundColor Red
    if (Test-Path $log) { Get-Content $log -Tail 4 | ForEach-Object { Write-Host ("         " + $_.Substring(0, [Math]::Min(150, $_.Length))) } }
    return $false
}

function Start-MongoWithFallback {
    <#
        Thu lan luot tung ban mongod cho den khi cai nao mo duoc du lieu.
        Ban nao chay duoc se duoc ghi vao runtime\mongodb-bin.txt de lan sau dung ngay.
    #>
    foreach ($exe in $MongodCandidates) {
        $version = ""
        try { $version = ((& $exe --version) | Select-Object -First 1) } catch { }
        Write-Host ("  - thu: {0} [{1}]" -f $exe, $version)
        $args = "--dbpath `"$MongoData`" --replSet rs0 --bind_ip 127.0.0.1 --port $MongoPort --wiredTigerCacheSizeGB $MongoCacheGB --logpath `"$(Join-Path $LogDir 'mongod.log')`" --logappend"
        if (Start-Daemon "mongod" $exe $args $RepoRoot $MongoPort "MongoDB") {
            Set-Content -Path $MongoBinMark -Value $exe -Encoding ascii
            return $true
        }
        # dung han tien trinh con sot lai tru khi thu ban khac
        $left = Get-NetTCPConnection -LocalPort $MongoPort -State Listen -ErrorAction SilentlyContinue
        if ($left) { Stop-Process -Id ($left | Select-Object -First 1).OwningProcess -Force -ErrorAction SilentlyContinue }
        Start-Sleep 2
    }
    return $false
}

function Invoke-External([scriptblock]$Block) {
    # Chay lenh ngoài ma khong bi $ErrorActionPreference="Stop" chan khi co xuong stderr
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { ($Block.Invoke() | Out-String).Trim() }
    finally { $ErrorActionPreference = $previous }
}

function Stop-Daemon([string]$Name, [string]$Label, [int]$Port) {
    $stopped = $false
    $pidFile = Join-Path $PidDir "$Name.pid"
    # MongoDB tat bang lenh `shutdown` (tronh WiredTiger bi kiem nen -> chai lan mo lai)
    if ($Name -eq "mongod" -and (Test-Port $Port) -and (Test-Path $PythonExe)) {
        $out = Invoke-External { & $PythonExe (Join-Path $RepoRoot "tools\mongo_stop.py") --port $Port 2>&1 }
        foreach ($line in ($out -split "\r?\n" | Where-Object { $_ })) { Write-Host "         $line" }
    }
    $p = Get-StoredPid $Name
    if ($p) {
        try {
            # ket thuc ca cay qua tinh (con cua no) de khong sot lai进程 node/python
            & taskkill /PID $p /T /F 2>&1 | Out-Null
            $stopped = $true
        } catch { }
    }
    Remove-Item $pidFile -ErrorAction SilentlyContinue
    if (-not $stopped) {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            try { & taskkill /PID $c.OwningProcess /T /F 2>&1 | Out-Null; $stopped = $true } catch { }
        }
    }
    if ($stopped) { Write-Host ("  [OK]   da dung {0}" -f $Label) } else { Write-Host ("  [--]   {0} khong chay" -f $Label) }
}

# ---------------------------------------------------------------- actions
function Do-Status {
    Write-Host "Trang thai dich vu:"
    $rows = @(
        @{ N = "MongoDB (replica set rs0)"; P = $MongoPort },
        @{ N = "Backend (FastAPI)"; P = $BackendPort },
        @{ N = "Frontend (giao dien web)"; P = $FrontendPort }
    )
    foreach ($r in $rows) {
        $state = if (Test-Port $r.P) { "DANG CHAY  :$" + $r.P } else { "DUNG        :$" + $r.P }
        Write-Host ("  {0,-32} {1}" -f $r.N, $state)
    }
}

function Do-Build {
    Write-Host "Dich phan mem giao dien (lan dau mat vai phut)..."
    Push-Location $FrontendDir
    try {
        $env:NEXT_PUBLIC_API_BASE = "http://127.0.0.1:$BackendPort"
        & $NpmCmd run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build that bai (ma $LASTEXITCODE)" }
        Write-Host "  [OK]   dich xong giao dien"
    }
    finally { Pop-Location }
}

function Do-Start {
    Write-Host "=== Khoi dong Viet Tieu Thuyet ==="
    if (-not $MongodCandidates) {
        Write-Host "  [LOI]  khong tim thay mongod.exe." -ForegroundColor Red
        Write-Host "         Tai MongoDB Community (5.0.x hoac 8.0.x) roi giai nen vao $WorkspaceRoot\tools\<ten>\bin\mongod.exe"
        Write-Host "         hoac dat bien VT_MONGO_HOME tro toi thu muc MongoDB."
        return
    }
    if (-not (Test-Path $MongoData)) { New-Item -ItemType Directory -Force -Path $MongoData | Out-Null }

    Write-Host "[1/4] MongoDB..."
    if (-not (Start-MongoWithFallback)) {
        Write-Host "  [LOI]  khong co ban MongoDB (mongod.exe) nao mo duoc thu muc du lieu $MongoData." -ForegroundColor Red
        Write-Host "         May cu khong co AVX2 chi chay duoc MongoDB 5.0.x (dat trong tools\m5)."
        return
    }
    if (Test-Port $MongoPort) {
        if (Test-Path $RsInitScript) {
            $out = Invoke-External { & $PythonExe $RsInitScript --port $MongoPort 2>&1 }
            foreach ($line in ($out -split "\r?\n" | Where-Object { $_ })) { Write-Host "         $line" }
        }
    }

    Write-Host "[2/4] Backend..."
    if (-not (Test-Path $PythonExe)) {
        Write-Host "  [LOI]  thieu $PythonExe. chay lenh cai dat trong HuongDanSuDung.md" -ForegroundColor Red
        return
    }
    Start-Daemon "backend" $PythonExe "-m uvicorn backend.app:app --host 127.0.0.1 --port $BackendPort" $RepoRoot $BackendPort "Backend" | Out-Null

    Write-Host "[3/4] Frontend..."
    $distIndex = Join-Path $FrontendDir ".next\BUILD_ID"
    if (-not (Test-Path $distIndex)) { Do-Build }
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "cd /d `"$FrontendDir`" && set NEXT_PUBLIC_API_BASE=http://127.0.0.1:$BackendPort&& `"$NpmCmd`" run start -- --hostname 127.0.0.1 --port $FrontendPort > `"$(Join-Path $LogDir 'frontend.log')`" 2>&1" -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline -and -not (Test-Port $FrontendPort)) { Start-Sleep -Milliseconds 900 }
    if (Test-Port $FrontendPort) { Write-Host "  [OK]   Frontend (cong $FrontendPort)" } else { Write-Host "  [LOI]  Frontend khong len. Xem runtime\logs\frontend.log" -ForegroundColor Red }

    Write-Host "[4/4] Mo trinh duyet..."
    $url = "http://127.0.0.1:$FrontendPort"
    if (Test-Port $FrontendPort) { Start-Process $url }
    Write-Host ""
    Write-Host "  Nguon lam viec: $url  (chon 'Tiếng Việt' o goc tren ben phai)"
    Do-Status
}

function Do-Stop {
    Write-Host "=== Dung Viet Tieu Thuyet ==="
    Stop-Daemon "frontend" "Frontend" $FrontendPort
    Stop-Daemon "backend" "Backend" $BackendPort
    Stop-Daemon "mongod" "MongoDB" $MongoPort
}

switch ($Action) {
    "start" { Do-Start }
    "stop" { Do-Stop }
    "restart" { Do-Stop; Start-Sleep 3; Do-Start }
    "build" { Do-Build }
    "logs" {
        Get-ChildItem $LogDir -Filter *.log | ForEach-Object {
            Write-Host ("--- {0} ---" -f $_.Name)
            Get-Content $_.FullName -Tail 30 | ForEach-Object { Write-Host $_ }
        }
    }
    default { Do-Status }
}
