param(
    [string]$ProjectDirectory = (Split-Path $PSScriptRoot -Parent),
    [string]$StateDirectory = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'TutorIA'),
    [string]$BuildCertificate = ''
)
$ErrorActionPreference = 'Stop'
$windows = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
function Run-Docker([string[]]$Arguments) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & docker @Arguments
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    if ($code -ne 0) { throw 'Docker fallo. Revisa el mensaje anterior antes de continuar.' }
}
function Inspect-Docker([string[]]$Arguments) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & docker @Arguments 2>$null
        return @{ Output=$output; Code=$LASTEXITCODE }
    } finally { $ErrorActionPreference = $previousPreference }
}
function Ensure-Resource([string]$Kind, [string]$Name) {
    $inspection = Inspect-Docker -Arguments @($Kind,'inspect','--format','{{index .Labels "pe.tutoria.local"}}',$Name)
    if ($inspection.Code -eq 0) {
        if ($inspection.Output -ne 'demo-api') { throw "El recurso $Name ya existe y no pertenece a este inicio local; se conservo intacto." }
    } else {
        Run-Docker -Arguments @($Kind,'create','--label','pe.tutoria.local=demo-api',$Name) | Out-Null
    }
}
$engine = Inspect-Docker -Arguments @('info','--format','{{.ServerVersion}}')
if ($engine.Code -ne 0) { throw 'Abre Docker Desktop y vuelve a intentarlo.' }
$editor = Inspect-Docker -Arguments @('inspect','--format','{{.Id}}','tutoria-n8n-local')
if ($editor.Code -ne 0) { throw 'No se encuentra tutoria-n8n-local. Este inicio necesita el n8n que ya creaste.' }
[IO.Directory]::CreateDirectory($StateDirectory) | Out-Null
$envFile = Join-Path $StateDirectory 'api.env'
$existingApi = Inspect-Docker -Arguments @('inspect','--format','{{index .Config.Labels "pe.tutoria.local"}}','tutoria-api-local')
$hasApi = $existingApi.Code -eq 0
if ($hasApi -and $existingApi.Output -ne 'demo-api') { throw 'El contenedor tutoria-api-local no pertenece a este inicio; se conservo intacto.' }
if ($hasApi -and !(Test-Path $envFile)) { throw 'Existe una API pero falta su configuracion privada. Se conservo el contenedor para evitar cambiar sus claves.' }
if (!(Test-Path $envFile)) {
    $handle = [IO.File]::Open($envFile, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $handle.Dispose()
    if ($windows) {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $acl = [Security.AccessControl.FileSecurity]::new()
        $acl.SetAccessRuleProtection($true, $false)
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identity, 'FullControl', 'Allow'))
        Set-Acl -LiteralPath $envFile -AclObject $acl
    } else {
        & chmod 600 $envFile
        if ($LASTEXITCODE -ne 0) { throw 'No fue posible proteger el archivo privado.' }
    }
    $lines = @()
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        foreach ($name in @('OPERATOR_TOKEN','REVIEWER_TOKEN','MOBILE_TOKEN')) {
            $randomBytes = [byte[]]::new(32)
            $rng.GetBytes($randomBytes)
            $token = [Convert]::ToBase64String($randomBytes).Replace('+','-').Replace('/','_').TrimEnd('=')
            $lines += "$name=$token"
        }
    } finally { $rng.Dispose() }
    [IO.File]::WriteAllLines($envFile, $lines, [Text.UTF8Encoding]::new($false))
}
$settings = @{}
foreach ($line in [IO.File]::ReadAllLines($envFile)) {
    $pair = $line.Split([char]'=', 2)
    if ($pair.Length -eq 2) { $settings[$pair[0]] = $pair[1] }
}
$roles = @('OPERATOR_TOKEN','REVIEWER_TOKEN','MOBILE_TOKEN')
foreach ($role in $roles) { if (!$settings[$role]) { throw 'El archivo privado esta incompleto. No lo compartas por el chat.' } }
if (@($roles | ForEach-Object { $settings[$_] } | Select-Object -Unique).Count -ne 3) { throw 'Las claves de los roles deben ser diferentes.' }
$build = @('build','-f',(Join-Path $ProjectDirectory 'Dockerfile.local'),'-t','tutoria-api-local:demo')
if ($BuildCertificate) { $build += @('--secret',"id=proxy_ca,src=$BuildCertificate") }
$build += $ProjectDirectory
Run-Docker -Arguments $build
Ensure-Resource 'network' 'tutoria-local'
Ensure-Resource 'volume' 'tutoria_api_local'
if (!$hasApi) {
    Run-Docker -Arguments @('run','-d','--name','tutoria-api-local','--label','pe.tutoria.local=demo-api',
        '--network','tutoria-local','--network-alias','api','-p','127.0.0.1:8000:8000',
        '--env-file',$envFile,'-v','tutoria_api_local:/app/data','tutoria-api-local:demo') | Out-Null
} else {
    Run-Docker -Arguments @('start','tutoria-api-local') | Out-Null
}
$attached = Inspect-Docker -Arguments @('inspect','--format','{{if index .NetworkSettings.Networks "tutoria-local"}}yes{{end}}','tutoria-n8n-local')
if ($attached.Code -ne 0) { throw 'No se pudo comprobar la red de n8n.' }
if ($attached.Output -ne 'yes') { Run-Docker -Arguments @('network','connect','tutoria-local','tutoria-n8n-local') | Out-Null }
$healthy = $false
for ($i=0; $i -lt 90; $i++) {
    try {
        $response = Invoke-RestMethod -Uri 'http://localhost:8000/health' -TimeoutSec 3
        if ($response.status -eq 'ok') { $healthy = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if (!$healthy) { throw 'La API no arranco. Ejecuta: docker logs --tail 40 tutoria-api-local' }
$headers = @{ Authorization = 'Bearer ' + $settings['OPERATOR_TOKEN'] }
$result = Invoke-RestMethod -Uri 'http://localhost:8000/sources/sqlite/run' -Method Post -Headers $headers -ContentType 'application/json' -Body '{"import_id":"pc-setup-check"}' -TimeoutSec 90
if ($result.cases -ne 30 -or $result.status -ne 'pending') { throw 'La comprobacion funcional de la API no devolvio los casos esperados.' }
Run-Docker -Arguments @('exec','tutoria-n8n-local','node','-e',"fetch('http://api:8000/health').then(r=>{if(!r.ok)process.exit(1);console.log('Conexion n8n -> API: OK')}).catch(()=>process.exit(1))")
Write-Host 'API lista: http://localhost:8000/docs'
Write-Host 'Comprobacion correcta: 30 casos sinteticos pendientes de revision.'
if ($windows) {
    Set-Clipboard -Value ('Bearer ' + $settings['OPERATOR_TOKEN'])
    Write-Host 'La clave de operador esta en el portapapeles para pegarla en la credencial Header Auth de n8n.'
}
Write-Host 'Tu cuenta, los workflows y el volumen de n8n se conservaron.'
