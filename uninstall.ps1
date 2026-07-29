<#
.SYNOPSIS
Remove ccp for the current Windows user.

.EXAMPLE
    pwsh -ExecutionPolicy Bypass -File .\uninstall.ps1
    pwsh -ExecutionPolicy Bypass -File .\uninstall.ps1 -Purge

.DESCRIPTION
Takes out the command, the PowerShell profile block, the statusline and the user PATH
entry. Neither mode ever touches the LIVE credential, so you stay signed in to whichever
account is live right now. -Purge also deletes the slot directories and their parked
credentials, which means the accounts in those slots will need a normal /login again.
#>

[CmdletBinding()]
param(
    [string]$BinDir = (Join-Path $env:LOCALAPPDATA 'Programs\ccp'),
    [switch]$Purge
)

$ErrorActionPreference = 'Stop'
$markOpen  = '# >>> ccp'
$markClose = '# <<< ccp <<<'

Write-Host "==> removing ccp for $env:USERNAME"

$ccp = (Get-Command ccp -ErrorAction SilentlyContinue).Source
if (-not $ccp -and (Test-Path (Join-Path $BinDir 'ccp.cmd'))) {
    $ccp = Join-Path $BinDir 'ccp.cmd'
}
if ($ccp) {
    $live = & $ccp live 2>$null
    if ($live) { Write-Host "    live account stays signed in: $live" }
}

# --- optional purge, while ccp is still callable ----------------------------- #
# `ccp rm --purge` refuses the live slot, which is exactly the guarantee we want.
if ($Purge) {
    $reg = Join-Path $HOME '.claude-profiles'
    if ($ccp -and (Test-Path $reg)) {
        Get-ChildItem (Join-Path $reg 'slot*.dir') -ErrorAction SilentlyContinue |
            ForEach-Object {
                $n = $_.BaseName -replace '^slot', ''
                & $ccp rm $n --purge *>$null
                if ($LASTEXITCODE -eq 0) { Write-Host "    slot$n purged" }
            }
    } elseif (-not $ccp) {
        Write-Host '    ! ccp not callable; deleting slot dirs without clearing stores'
    }
    foreach ($d in (Join-Path $HOME '.claude-slots'), (Join-Path $HOME '.claude-profiles')) {
        if (Test-Path $d) { Remove-Item $d -Recurse -Force }
    }
    Write-Host '    removed ~\.claude-slots and ~\.claude-profiles'
    Write-Host '    NOTE: the live credential was left intact - you are still signed in.'
}

# --- PowerShell profile ----------------------------------------------------- #
$profilePath = $PROFILE.CurrentUserAllHosts
if (Test-Path $profilePath) {
    $lines = Get-Content $profilePath
    if ($lines -match [regex]::Escape($markOpen)) {
        $out = [System.Collections.Generic.List[string]]::new()
        $skip = $false
        foreach ($ln in $lines) {
            if (-not $skip -and $ln.TrimStart().StartsWith($markOpen)) { $skip = $true; continue }
            if ($skip) { if ($ln.Trim() -eq $markClose) { $skip = $false }; continue }
            $out.Add($ln)
        }
        Set-Content -Path $profilePath -Value $out
        Write-Host "    $profilePath : ccp block removed"
    } else {
        Write-Host "    $profilePath : no ccp block found"
    }
} else {
    Write-Host '    no PowerShell profile found'
}

# --- statusline ------------------------------------------------------------- #
$settings = Join-Path $HOME '.claude\settings.json'
if (Test-Path $settings) {
    try {
        $json = Get-Content $settings -Raw | ConvertFrom-Json -AsHashtable
        if ("$($json['statusLine'].command)" -like '*ccp-statusline*') {
            $json.Remove('statusLine')
            $json | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $settings
            Write-Host '    settings.json: statusLine removed'
        } else {
            Write-Host "    settings.json: statusLine is not ccp's, left alone"
        }
    } catch {
        Write-Host '    settings.json: could not be parsed, left alone'
    }
}

# --- the command itself ----------------------------------------------------- #
foreach ($f in 'ccp', 'ccp.cmd', 'ccp-statusline.py') {
    $p = Join-Path $BinDir $f
    if (Test-Path $p) { Remove-Item $p -Force; Write-Host "    removed $p" }
}
if ((Test-Path $BinDir) -and -not (Get-ChildItem $BinDir -Force)) {
    Remove-Item $BinDir -Force
    Write-Host "    removed empty $BinDir"
}

# --- user PATH -------------------------------------------------------------- #
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -and ($userPath -split ';' -contains $BinDir)) {
    $kept = $userPath -split ';' | Where-Object { $_ -and $_ -ne $BinDir }
    [Environment]::SetEnvironmentVariable('Path', ($kept -join ';'), 'User')
    Write-Host '    removed from user PATH'
}

Write-Host @'

==> done. Open a new PowerShell window so the claude function goes away.
    ~\.claude was never modified beyond the statusLine setting.

'@
