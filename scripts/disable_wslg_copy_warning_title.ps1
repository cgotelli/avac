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
    $settingLine = "WESTON_RDP_COPY_WARNING_TITLE=false"

    if (Test-Path -LiteralPath $ConfigPath) {
        $content = Get-Content -LiteralPath $ConfigPath -Raw -ErrorAction Stop
    } else {
        $content = ""
    }

    if ($content -match "(?im)^\s*WESTON_RDP_COPY_WARNING_TITLE\s*=") {
        $updated = [System.Text.RegularExpressions.Regex]::Replace(
            $content,
            "(?im)^\s*WESTON_RDP_COPY_WARNING_TITLE\s*=.*$",
            $settingLine
        )
    } else {
        if ($content -notmatch "(?im)^\s*\[system-distro-env\]\s*$") {
            if ($content -and -not $content.EndsWith("`n")) {
                $content += "`r`n"
            }
            $content += "$sectionHeader`r`n"
        } elseif ($content -and -not $content.EndsWith("`n")) {
            $content += "`r`n"
        }
        $updated = $content + "$settingLine`r`n"
    }

    Set-Content -LiteralPath $ConfigPath -Value $updated -Encoding UTF8
}

$userConfig = Join-Path $env:USERPROFILE ".wslgconfig"
Set-WslgCopyWarningFlag -ConfigPath $userConfig
Write-Host "Updated user WSLg config: $userConfig"

if ($SystemWide) {
    $systemConfig = "C:\ProgramData\Microsoft\WSL\.wslgconfig"
    Set-WslgCopyWarningFlag -ConfigPath $systemConfig
    Write-Host "Updated system WSLg config: $systemConfig"
}

Write-Host "Done. Restart WSLg so the title warning disappears:"
Write-Host "  wsl --shutdown"
Write-Host "Then launch AVAC again."
