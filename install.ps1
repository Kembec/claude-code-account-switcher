<#
.SYNOPSIS
Install ccp for the current Windows user. Idempotent - safe to re-run.

.EXAMPLE
    pwsh -ExecutionPolicy Bypass -File .\install.ps1
    pwsh -ExecutionPolicy Bypass -File .\install.ps1 -BinDir D:\tools\ccp

.DESCRIPTION
Places ccp plus a ccp.cmd shim so `ccp` works from PowerShell and cmd, adds the
directory to your user PATH, defines a `claude` function in your PowerShell profile,
configures the statusline, and parks the account you are already signed in with as
slot1.

On Windows, Claude Code keeps its credential in <config dir>\.credentials.json, so no
keychain is involved. Symlinks need Developer Mode; without it ccp falls back to
directory junctions and file hardlinks, which need no privilege.
#>

[CmdletBinding()]
param(
    [string]$BinDir = (Join-Path $env:LOCALAPPDATA 'Programs\ccp'),
    [switch]$Copy
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$mark = '# >>> ccp'

Write-Host "==> installing ccp for $env:USERNAME"
Write-Host "    source: $repo"
Write-Host "    bindir: $BinDir"

# --- prerequisites ---------------------------------------------------------- #
$python = (Get-Command python3, python -ErrorAction SilentlyContinue |
           Select-Object -First 1).Source
if (-not $python) {
    Write-Error 'Python 3 was not found on PATH. Install it and re-run.'
}
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Error @'
'claude' is not on PATH. Install Claude Code first:
https://docs.claude.com/en/docs/claude-code
'@
}

# --- place the files -------------------------------------------------------- #
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
foreach ($f in 'ccp', 'ccp-statusline.py') {
    $dst = Join-Path $BinDir $f
    Remove-Item $dst -Force -ErrorAction SilentlyContinue
    if ($Copy) {
        Copy-Item (Join-Path $repo "bin\$f") $dst
    } else {
        try   { New-Item -ItemType SymbolicLink -Path $dst -Target (Join-Path $repo "bin\$f") | Out-Null }
        catch { Copy-Item (Join-Path $repo "bin\$f") $dst }   # no Developer Mode: copy
    }
}

# A .cmd shim makes `ccp` callable as a command, since ccp itself has no extension.
@"
@echo off
"$python" "%~dp0ccp" %*
"@ | Set-Content -Encoding ASCII (Join-Path $BinDir 'ccp.cmd')
Write-Host '    placed ccp, ccp.cmd and ccp-statusline.py'

# --- user PATH -------------------------------------------------------------- #
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -split ';' -notcontains $BinDir) {
    [Environment]::SetEnvironmentVariable(
        'Path', (@($BinDir) + ($userPath -split ';' | Where-Object { $_ })) -join ';', 'User')
    Write-Host '    added to user PATH (new shells pick it up)'
} else {
    Write-Host '    already on user PATH'
}
$env:Path = "$BinDir;$env:Path"

# --- PowerShell profile ----------------------------------------------------- #
# Plain `claude` must run on the live credential; that is what lets one `ccp swap`
# change the account for every open session. $env:CCP pins a single invocation.
$profilePath = $PROFILE.CurrentUserAllHosts
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $profilePath) | Out-Null
if (-not (Test-Path $profilePath)) { New-Item -ItemType File -Path $profilePath | Out-Null }

if ((Get-Content $profilePath -Raw -ErrorAction SilentlyContinue) -match [regex]::Escape($mark)) {
    Write-Host "    $profilePath : ccp block already present, left untouched"
} else {
    Add-Content $profilePath @'

# >>> ccp - Claude Code account slots >>>
function claude {
    $exe = (Get-Command claude.exe, claude.cmd -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1).Source
    if (-not $exe) { Write-Error 'claude not found on PATH'; return }
    $prev = $env:CLAUDE_CONFIG_DIR
    try {
        $slot = $env:CCP
        if ($slot) {
            $d = Join-Path $HOME ('.claude-slots\' + ($slot -replace '^slot', ''))
            if (Test-Path $d) { $env:CLAUDE_CONFIG_DIR = $d }
            else { Remove-Item Env:CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue }
        } else {
            Remove-Item Env:CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        }
        & $exe @args
    } finally {
        if ($null -ne $prev) { $env:CLAUDE_CONFIG_DIR = $prev }
        else { Remove-Item Env:CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue }
    }
}
# <<< ccp <<<
'@
    Write-Host "    $profilePath : ccp block added"
}

# --- statusline ------------------------------------------------------------- #
$settings = Join-Path $HOME '.claude\settings.json'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $settings) | Out-Null
$json = @{}
if (Test-Path $settings) {
    try { $json = Get-Content $settings -Raw | ConvertFrom-Json -AsHashtable } catch { $json = @{} }
}
$json['statusLine'] = @{
    type    = 'command'
    command = "`"$python`" `"$(Join-Path $BinDir 'ccp-statusline.py')`""
    padding = 0
}
$json | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $settings
Write-Host '    settings.json: statusLine configured'

# --- park the current login ------------------------------------------------- #
Write-Host ''
& $python (Join-Path $BinDir 'ccp') init

Write-Host @"

==> done. Open a new PowerShell window, then:

    ccp add          create the next slot
    ccp login <n>    /login another account into that slot
    ccp swap <n>     switch the account for EVERY open session
    ccp doctor       self-check

"@
