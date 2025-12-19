# Simple script: loads API keys from api-keys into current session env vars
# Line 1: TAVILY_API_KEY
# Line 2: GOOGLE_API_KEY
# Line 3 (optional): GEOAPIFY_API_KEY

$apiFile = "api-keys"

if (-not (Test-Path $apiFile)) {
    Write-Error "api-keys file not found in the current directory."
    exit 1
}

# Read entire file (need at least TAVILY + GOOGLE)
$lines = Get-Content -Path $apiFile
if ($null -eq $lines -or $lines.Count -lt 2) {
    Write-Error "api-keys must contain at least two lines: first TAVILY, second GOOGLE."
    exit 1
}

$env:TAVILY_API_KEY = $lines[0].Trim()
$env:GOOGLE_API_KEY = $lines[1].Trim()

$optionalKeys = @(
    @{ Name = 'GEOAPIFY_API_KEY'; Index = 2 }
)

foreach ($entry in $optionalKeys) {
    if ($lines.Count -gt $entry.Index -and $lines[$entry.Index].Trim()) {
        $value = $lines[$entry.Index].Trim()
        Set-Item -Path Env:$($entry.Name) -Value $value
    }
}

Write-Host "Environment variables set for this PowerShell session:" -ForegroundColor Green
Write-Host "  TAVILY_API_KEY (length): $($env:TAVILY_API_KEY.Length)"
Write-Host "  GOOGLE_API_KEY (length): $($env:GOOGLE_API_KEY.Length)"
if ($env:GEOAPIFY_API_KEY) {
    Write-Host "  GEOAPIFY_API_KEY (length): $($env:GEOAPIFY_API_KEY.Length)"
} else {
    Write-Host "  GEOAPIFY_API_KEY: not set (autocomplete + curated POIs will fall back)"
}
Write-Host "Run your app in this same terminal (e.g., 'python api.py')."
