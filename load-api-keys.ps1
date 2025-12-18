# Simple script: loads API keys from api-keys into current session env vars
# Line 1: TAVILY_API_KEY
# Line 2: GOOGLE_API_KEY
# Line 3 (optional): OPENTRIPMAP_API_KEY
# Line 4 (optional): ORS_API_KEY
# Line 5 (optional): GEOAPIFY_API_KEY

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
    @{ Name = 'OPENTRIPMAP_API_KEY'; Index = 2 },
    @{ Name = 'ORS_API_KEY'; Index = 3 },
    @{ Name = 'GEOAPIFY_API_KEY'; Index = 4 }
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
if ($env:OPENTRIPMAP_API_KEY) {
    Write-Host "  OPENTRIPMAP_API_KEY (length): $($env:OPENTRIPMAP_API_KEY.Length)"
} else {
    Write-Host "  OPENTRIPMAP_API_KEY: not set (map POIs will be disabled)"
}
if ($env:ORS_API_KEY) {
    Write-Host "  ORS_API_KEY (length): $($env:ORS_API_KEY.Length)"
} else {
    Write-Host "  ORS_API_KEY: not set (routing will be disabled)"
}
if ($env:GEOAPIFY_API_KEY) {
    Write-Host "  GEOAPIFY_API_KEY (length): $($env:GEOAPIFY_API_KEY.Length)"
} else {
    Write-Host "  GEOAPIFY_API_KEY: not set (live autocomplete will use fallback)"
}
Write-Host "Run your app in this same terminal (e.g., 'python api.py')."
