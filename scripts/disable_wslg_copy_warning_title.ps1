param(
    [switch]$SystemWide
)

$ErrorActionPreference = "Stop"

function Set-WslgCopyWarningFlag {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfigPath
    )

    $dir = Split-Path -Parent $ConfigPath
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    $sectionHeader = "[system-distro-env]"
    $settingLines = @(
        "WESTON_RDP_COPY_WARNING_TITLE=false",
        "WESTON_RDP_APPEND_DISTRONAME_TITLE=false"
    )

    if (Test-Path -LiteralPath $ConfigPath) {
        $content = Get-Content -LiteralPath $ConfigPath -Raw -ErrorAction Stop
    } else {
        $content = ""
    }

    $updated = $content

    if ($updated -match "(?im)^\s*WESTON_RDP_COPY_WARNING_TITLE\s*=") {
        $updated = [System.Text.RegularExpressions.Regex]::Replace(
            $updated,
            "(?im)^\s*WESTON_RDP_COPY_WARNING_TITLE\s*=.*$",
            $settingLines[0]
        )
    }

    if ($updated -match "(?im)^\s*WESTON_RDP_APPEND_DISTRONAME_TITLE\s*=") {
        $updated = [System.Text.RegularExpressions.Regex]::Replace(
            $updated,
            "(?im)^\s*WESTON_RDP_APPEND_DISTRONAME_TITLE\s*=.*$",
            $settingLines[1]
        )
    }

    if ($updated -notmatch "(?im)^\s*\[system-distro-env\]\s*$") {
        if ($updated -and -not $updated.EndsWith("`n")) {
            $updated += "`r`n"
        }
        $updated += "$sectionHeader`r`n"
    } elseif ($updated -and -not $updated.EndsWith("`n")) {
        $updated += "`r`n"
    }

    if ($updated -notmatch "(?im)^\s*WESTON_RDP_COPY_WARNING_TITLE\s*=") {
        $updated += "$($settingLines[0])`r`n"
    }
    if ($updated -notmatch "(?im)^\s*WESTON_RDP_APPEND_DISTRONAME_TITLE\s*=") {
        $updated += "$($settingLines[1])`r`n"
    }

    # WSLg ignores some BOM-encoded files; force UTF-8 without BOM.
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($ConfigPath, $updated, $utf8NoBom)
}

$userConfig = Join-Path $env:USERPROFILE ".wslgconfig"
Set-WslgCopyWarningFlag -ConfigPath $userConfig
Write-Host "Updated user WSLg config: $userConfig"

if ($SystemWide) {
    $systemConfig = "C:\ProgramData\Microsoft\WSL\.wslgconfig"
    try {
        Set-WslgCopyWarningFlag -ConfigPath $systemConfig
        Write-Host "Updated system WSLg config: $systemConfig"
    } catch {
        Write-Warning "Could not update system-wide WSLg config. Run this script from an elevated PowerShell (Run as Administrator)."
        throw
    }
}

Write-Host "Done. Restart WSLg so the title warning disappears:"
Write-Host "  wsl --shutdown"
Write-Host "Then launch AVAC again."
