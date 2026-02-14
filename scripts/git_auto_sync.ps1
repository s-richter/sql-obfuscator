param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    $escapedArgs = @(
        $Args | ForEach-Object {
            if ($_ -match '[\s"]') {
                '"' + ($_ -replace '"', '\"') + '"'
            }
            else {
                $_
            }
        }
    )
    $argumentString = $escapedArgs -join " "

    $stdoutFile = [System.IO.Path]::GetTempFileName()
    $stderrFile = [System.IO.Path]::GetTempFileName()
    try {
        $proc = Start-Process -FilePath "git" -ArgumentList $argumentString -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        $code = $proc.ExitCode
        $stdout = if (Test-Path $stdoutFile) { Get-Content -Path $stdoutFile -ErrorAction SilentlyContinue } else { @() }
        $stderr = if (Test-Path $stderrFile) { Get-Content -Path $stderrFile -ErrorAction SilentlyContinue } else { @() }
        $output = @($stdout + $stderr | Where-Object { $_ -and $_.Trim() -ne "" })
    }
    finally {
        if (Test-Path $stdoutFile) { Remove-Item -Force $stdoutFile -ErrorAction SilentlyContinue }
        if (Test-Path $stderrFile) { Remove-Item -Force $stderrFile -ErrorAction SilentlyContinue }
    }

    if ($code -ne 0) {
        $joined = $Args -join " "
        throw "git $joined failed with exit code $code.`n$output"
    }
    return $output
}

function Get-CommitStyle {
    param(
        [string[]]$RecentMessages
    )

    $conventional = 0
    foreach ($msg in $RecentMessages) {
        if ($msg -match '^[a-z]+(\([^)]+\))?: ') {
            $conventional++
        }
    }
    if ($conventional -ge 3) {
        return "conventional"
    }
    return "plain"
}

function Get-ChangeType {
    param(
        [string[]]$Paths
    )

    if ($Paths.Count -eq 0) {
        return "chore"
    }

    $allDocs = $true
    $allTests = $true
    $hasSrc = $false

    foreach ($p in $Paths) {
        $isDoc = $p -match '(^|/)(README|CHANGELOG|docs?/)' -or $p -match '\.md$'
        $isTest = $p -match '(^|/)tests?/' -or $p -match '^test_.*\.py$'
        $isSrc = $p -match '^src/' -or $p -match '^obfuscator\.py$'

        if (-not $isDoc) { $allDocs = $false }
        if (-not $isTest) { $allTests = $false }
        if ($isSrc) { $hasSrc = $true }
    }

    if ($allDocs) { return "docs" }
    if ($allTests) { return "test" }
    if ($hasSrc) { return "feat" }
    return "chore"
}

function Get-AreaSummary {
    param(
        [string[]]$Paths
    )

    if ($Paths.Count -eq 0) {
        return "repository"
    }

    $areas = New-Object System.Collections.Generic.HashSet[string]
    foreach ($p in $Paths) {
        if ($p -match '^src/sql_obfuscator/') {
            [void]$areas.Add("core")
        } elseif ($p -match '^tests/') {
            [void]$areas.Add("tests")
        } elseif ($p -match '^scripts/') {
            [void]$areas.Add("scripts")
        } elseif ($p -match '\.md$') {
            [void]$areas.Add("docs")
        } elseif ($p -match '^pyproject\.toml$') {
            [void]$areas.Add("packaging")
        } else {
            [void]$areas.Add("repo")
        }
    }

    $areaList = @($areas)
    [Array]::Sort($areaList)
    if ($areaList.Count -le 2) {
        return ($areaList -join " and ")
    }
    return "$(($areaList -join ', '))"
}

function New-CommitMessage {
    param(
        [string[]]$RecentMessages,
        [string[]]$ChangedPaths
    )

    $style = Get-CommitStyle -RecentMessages $RecentMessages
    $type = Get-ChangeType -Paths $ChangedPaths
    $area = Get-AreaSummary -Paths $ChangedPaths
    $count = $ChangedPaths.Count

    if ($style -eq "conventional") {
        return "${type}: update $area ($count files)"
    }
    return "Update $area ($count files)"
}

try {
    $inside = (Invoke-Git -Args @("rev-parse", "--is-inside-work-tree")).Trim()
    if ($inside -ne "true") {
        throw "Current directory is not inside a git working tree."
    }

    $status = Invoke-Git -Args @("status", "--porcelain")
    $status = @($status | Where-Object { $_ -and $_.Trim() -ne "" })

    if ($status.Count -eq 0) {
        Write-Host "No untracked or uncommitted changes detected."
        exit 0
    }

    $recent = Invoke-Git -Args @("log", "-n", "5", "--pretty=format:%s")
    $recent = @($recent | Where-Object { $_ -and $_.Trim() -ne "" })

    Write-Host "Last 5 commit messages:"
    foreach ($msg in $recent) {
        Write-Host " - $msg"
    }

    $paths = @()
    foreach ($line in $status) {
        if ($line.Length -lt 4) { continue }
        $pathPart = $line.Substring(3).Trim()
        $pathPart = $pathPart -replace '\\', '/'
        if ($pathPart -match ' -> ') {
            $pathPart = ($pathPart -split ' -> ')[-1]
        }
        $paths += $pathPart
    }
    $paths = $paths | Select-Object -Unique

    $commitMessage = New-CommitMessage -RecentMessages $recent -ChangedPaths $paths
    Write-Host "Generated commit message: $commitMessage"

    if ($DryRun) {
        Write-Host "Dry run enabled. Skipping add/commit/push."
        exit 0
    }

    Invoke-Git -Args @("add", "-A") | Out-Null
    Invoke-Git -Args @("commit", "-m", $commitMessage) | Out-Null
    Invoke-Git -Args @("push") | Out-Null

    Write-Host "Changes committed and pushed successfully."
    exit 0
}
catch {
    Write-Error "git_auto_sync failed: $($_.Exception.Message)"
    exit 1
}
