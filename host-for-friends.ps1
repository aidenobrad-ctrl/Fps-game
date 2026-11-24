# Hosts Recoil on this PC so friends anywhere can play with you: the backend (accounts,
# Find Match, friends, parties) and two matchmaking game servers, reachable from the internet,
# and a zip of the game that already knows where your backend is, to send them.
# Double-click host-for-friends.bat to run it. Leave its window open while you play;
# press Enter in it to stop hosting.

# Not 'Stop': Windows PowerShell 5.1 turns anything docker or git print as progress into an error.
$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot

$BackendPort = 5080
$ServerPorts = @(7777, 7778)
$Game = Join-Path $PSScriptRoot 'Builds\Recoil'
$Exe = Join-Path $Game 'Recoil.exe'
$Compose = Join-Path $PSScriptRoot 'backend\docker-compose.yml'
$Api = Join-Path $PSScriptRoot 'backend\src\Recoil.Api'

function Say([string]$text) { Write-Host $text }
function Stop-Here([string]$text) {
    Write-Host ''
    Write-Host $text -ForegroundColor Yellow
    Write-Host ''
    Read-Host 'Press Enter to close' | Out-Null
    exit 1
}

Say 'Recoil: hosting for friends'
Say ''

# ------------------------------------------------------------------ what it needs

if (-not (Test-Path $Exe)) {
    Stop-Here 'Build the game first: close Unity, double-click build.bat, wait for it to finish, then run this again.'
}
if (-not (Test-Path (Join-Path $Api 'Recoil.Api.csproj'))) {
    Say 'Getting the backend folder from GitHub...'
    git sparse-checkout add backend
    if (-not (Test-Path (Join-Path $Api 'Recoil.Api.csproj'))) {
        Stop-Here 'Could not get the backend folder. In the recoil folder run:  git sparse-checkout add backend'
    }
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Stop-Here ("Docker Desktop is not installed. Install it with:`n    winget install -e --id Docker.DockerDesktop`n" +
               "then restart the PC, start Docker Desktop, and run this again.")
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Stop-Here 'Docker Desktop is not running. Start it from the Start menu, wait until it says Engine running, and run this again.'
}
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue) -or -not (dotnet --list-sdks | Where-Object { $_ -match '^10\.' })) {
    Stop-Here ("The .NET 10 SDK is not installed. Install it with:`n    winget install -e --id Microsoft.DotNet.SDK.10`n" +
               "then open a new window and run this again.")
}

# ------------------------------------------------------------------ secret keys

# Made once, kept on this PC only (never in the repository, which is public, unlike the
# development keys in its settings). Anyone with them could sign in as anyone on your backend.
$KeyFolder = Join-Path $env:LOCALAPPDATA 'Recoil'
$KeyFile = Join-Path $KeyFolder 'host-keys.json'
function New-Key {
    $bytes = New-Object byte[] 48
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $random.GetBytes($bytes)
    $random.Dispose()
    return [Convert]::ToBase64String($bytes)
}
if (Test-Path $KeyFile) {
    $Keys = Get-Content $KeyFile -Raw | ConvertFrom-Json
} else {
    New-Item -ItemType Directory -Force -Path $KeyFolder | Out-Null
    $Keys = [pscustomobject]@{ jwt = (New-Key); ticket = (New-Key); fleet = (New-Key) }
    $Keys | ConvertTo-Json | Set-Content -Path $KeyFile -Encoding ASCII
}

# ------------------------------------------------------------------ addresses

Say 'Finding this network''s addresses...'
$Public = ''
foreach ($lookup in @('https://api.ipify.org', 'https://ifconfig.me/ip', 'https://icanhazip.com')) {
    try {
        $answer = (Invoke-RestMethod -Uri $lookup -TimeoutSec 10).ToString().Trim()
        if ($answer -match '^\d{1,3}(\.\d{1,3}){3}$') { $Public = $answer; break }
    } catch { }
}
if (-not $Public) {
    $Public = (Read-Host 'Could not look up your public address. Search "what is my ip" in a browser and type it here').Trim()
}
$Lan = ''
try {
    $config = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1
    if ($config) { $Lan = @($config.IPv4Address)[0].IPAddress }
} catch { }
Say "  public address (what friends connect to): $Public"
Say "  this PC on your network: $Lan"

# ------------------------------------------------------------------ router and firewall

# Ask the router to forward the ports (UPnP). Many home routers allow it; if this one does
# not, the ports have to be forwarded by hand in its settings.
$Opened = @()
$RouterAddress = ''
if ($Lan) {
    try {
        $nat = New-Object -ComObject HNetCfg.NATUPnP
        $mappings = $nat.StaticPortMappingCollection
        if ($mappings -ne $null) {
            $wanted = @(@{ Port = $BackendPort; Protocol = 'TCP'; Name = 'Recoil backend' })
            foreach ($port in $ServerPorts) { $wanted += @{ Port = $port; Protocol = 'UDP'; Name = 'Recoil game server' } }
            foreach ($w in $wanted) {
                try { $mappings.Remove($w.Port, $w.Protocol) } catch { }
                $mapping = $mappings.Add($w.Port, $w.Protocol, $w.Port, $Lan, $true, $w.Name)
                if ($mapping -ne $null) {
                    $Opened += "$($w.Protocol) $($w.Port)"
                    $RouterAddress = $mapping.ExternalIPAddress
                }
            }
        }
    } catch { }
}

# Let them through Windows Firewall: once, with a Yes/No box from Windows.
$Udp = "$($ServerPorts[0])-$($ServerPorts[-1])"
if (-not (Get-NetFirewallRule -DisplayName "Recoil backend (TCP $BackendPort)" -ErrorAction SilentlyContinue)) {
    Say ''
    Say 'Windows will ask (Yes/No) to let friends through its firewall: choose Yes.'
    $rules = "New-NetFirewallRule -DisplayName 'Recoil backend (TCP $BackendPort)' -Direction Inbound -Protocol TCP -LocalPort $BackendPort -Action Allow -Profile Any | Out-Null; " +
             "New-NetFirewallRule -DisplayName 'Recoil game servers (UDP $Udp)' -Direction Inbound -Protocol UDP -LocalPort $Udp -Action Allow -Profile Any | Out-Null"
    try {
        Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile', '-Command', $rules
    } catch {
        Say '  (Not allowed, so friends may be blocked by the firewall. Run this again and choose Yes.)'
    }
}

# ------------------------------------------------------------------ the copy for friends

Say ''
Say 'Making the copy of the game for your friends...'
$Stage = Join-Path $PSScriptRoot 'Builds\ForFriends\Recoil'
$Zip = Join-Path $PSScriptRoot 'Builds\Recoil-for-friends.zip'
if (Test-Path (Split-Path $Stage)) { Remove-Item (Split-Path $Stage) -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Split-Path $Stage) | Out-Null
Copy-Item -Path $Game -Destination $Stage -Recurse
Remove-Item -Path (Join-Path $Stage 'Start matchmaking server.bat') -ErrorAction SilentlyContinue
Get-ChildItem -Path $Stage -Filter '*.log' | Remove-Item -ErrorAction SilentlyContinue
$friendsBackend = "http://$($Public):$BackendPort"
Set-Content -Path (Join-Path $Stage 'backend.txt') -Encoding ASCII -Value @(
    $friendsBackend,
    '# Where this copy of the game finds its backend: your friend''s PC. If they say their',
    '# address changed, put the new one on the first line.')
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path $Stage -DestinationPath $Zip
Remove-Item (Split-Path $Stage) -Recurse -Force

# ------------------------------------------------------------------ the backend

Say 'Starting the database and Redis in Docker...'
docker compose -f $Compose up -d --wait
if ($LASTEXITCODE -ne 0) { Stop-Here 'Docker could not start the database and Redis. The lines above say why.' }

Say 'Starting the backend (the first time it builds itself, which takes a minute or two)...'
$env:ASPNETCORE_ENVIRONMENT = 'Production'
$env:ASPNETCORE_URLS = "http://0.0.0.0:$BackendPort"
$env:ConnectionStrings__Postgres = 'Host=localhost;Port=5432;Database=recoil;Username=recoil;Password=recoil_dev'
$env:ConnectionStrings__Redis = 'localhost:6379'
$env:Database__MigrateOnStartup = 'true'
$env:Auth__JwtSigningKey = $Keys.jwt
$env:Game__TicketSigningKey = $Keys.ticket
$env:Matchmaking__FleetKey = $Keys.fleet
$env:Matchmaking__LocalAddressesForLocalPlayers = 'true'
$env:Email__PublicBaseUrl = $friendsBackend
$Backend = Start-Process cmd -PassThru -ArgumentList '/k', "title Recoil backend - leave open while hosting && dotnet run --project `"$Api`" -c Release --no-launch-profile"
$ready = $false
$deadline = (Get-Date).AddMinutes(5)
while (-not $ready -and (Get-Date) -lt $deadline -and -not $Backend.HasExited) {
    Start-Sleep -Seconds 2
    try { $ready = (Invoke-WebRequest -Uri "http://localhost:$BackendPort/health/ready" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { }
}
if (-not $ready) { Stop-Here 'The backend did not start. Its window says why.' }

# ------------------------------------------------------------------ the game servers

Say 'Starting the matchmaking game servers...'
$env:RECOIL_FLEET_KEY = $Keys.fleet
$env:RECOIL_TICKET_KEY = $Keys.ticket
$Servers = @()
foreach ($port in $ServerPorts) {
    $Servers += Start-Process -FilePath $Exe -WorkingDirectory $Game -PassThru -ArgumentList @(
        '-batchmode', '-nographics', '-server', '-fleet', "http://localhost:$BackendPort",
        '-public-address', $Public, '-port', "$port", '-logFile', "server-$port.log")
}

# ------------------------------------------------------------------ done

Say ''
Write-Host '=====================================================================' -ForegroundColor Green
Write-Host ' Hosting. Leave this window (and the backend''s) open while you play.' -ForegroundColor Green
Write-Host '=====================================================================' -ForegroundColor Green
Say ''
Say " For your friends: send them  Builds\Recoil-for-friends.zip"
Say '   They unzip it and double-click Recoil.exe. Nothing else to install.'
Say ' For you: play with  Builds\Recoil\Recoil.exe  as usual.'
Say ''
if ($Opened.Count -gt 0) {
    Say (" Your router opened the ports by itself: " + ($Opened -join ', ') + '.')
} else {
    Write-Host ' Your router did not open the ports by itself. In its settings (usually http://192.168.1.1 or' -ForegroundColor Yellow
    Write-Host " http://192.168.0.1), forward these to this PC ($Lan):  TCP $BackendPort  and  UDP $Udp." -ForegroundColor Yellow
}
if ($RouterAddress -and $RouterAddress -ne $Public) {
    Write-Host " Your router's own address ($RouterAddress) is not your public address ($Public): your internet" -ForegroundColor Yellow
    Write-Host ' provider probably shares one address between many homes (CGNAT), and friends cannot reach' -ForegroundColor Yellow
    Write-Host ' you directly. Private matches through a tunnel service (such as playit.gg) still work.' -ForegroundColor Yellow
}
Say ''
Say ' Codes for verifying email and resetting passwords appear in the backend''s window.'
Say ' Passwords travel unencrypted to your backend: tell friends not to reuse a real password.'
Say " If your public address changes (it can after a router restart), run this again and send the new zip."
Say ''
Read-Host 'Press Enter here to stop hosting' | Out-Null

Say 'Stopping...'
foreach ($server in $Servers) { if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue } }
if (-not $Backend.HasExited) { taskkill /T /F /PID $Backend.Id *> $null }
docker compose -f $Compose stop *> $null
Say 'Stopped.'
