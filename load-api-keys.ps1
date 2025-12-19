# Simple script: loads API keys from api-keys into current session env vars.
# Supports simple value-only files (line order) and optional KEY=VALUE entries.
# Minimum: Line 1 TAVILY_API_KEY, Line 2 GOOGLE_API_KEY.

$apiFile = "api-keys"

if (-not (Test-Path $apiFile)) {
    Write-Error "api-keys file not found in the current directory."
    exit 1
}

$rawLines = Get-Content -Path $apiFile
if ($null -eq $rawLines) {
    Write-Error "api-keys file is empty."
    exit 1
}

$lines = @()
foreach ($line in $rawLines) {
    if ($null -eq $line) { continue }
    $trimmed = $line.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
    if ($trimmed.StartsWith('#')) { continue }
    $lines += $trimmed
}

if ($lines.Count -lt 2) {
    Write-Error "api-keys must contain at least two values (Tavily, Google)."
    exit 1
}

$kvPairs = @{}
$orderedValues = @()
foreach ($entry in $lines) {
    if ($entry -match '^([A-Za-z0-9_]+)\s*=\s*(.*)$') {
        $kvPairs[$matches[1].Trim()] = $matches[2].Trim()
    } else {
        $orderedValues += $entry
    }
}

$script:orderedIndex = 0
function Get-NextOrderedValue {
    if ($script:orderedIndex -ge $script:orderedValues.Count) {
        return $null
    }
    $value = $script:orderedValues[$script:orderedIndex]
    $script:orderedIndex++
    return $value
}

function Resolve-Value {
    param(
        [string]$Name,
        [bool]$Required = $false
    )

    if ($script:kvPairs.ContainsKey($Name)) {
        return $script:kvPairs[$Name]
    }
    $value = Get-NextOrderedValue
    if ($Required -and [string]::IsNullOrWhiteSpace($value)) {
        Write-Error "Missing value for $Name in api-keys."
        exit 1
    }
    return $value
}

$keyPlan = @(
    @{ Name = 'TAVILY_API_KEY'; Required = $true; Description = 'Research agent (Tavily)' }
    @{ Name = 'GOOGLE_API_KEY'; Required = $true; Description = 'Gemma itinerary model' }
    @{ Name = 'GEOAPIFY_API_KEY'; Required = $false; Description = 'Autocomplete & POIs' }
    @{ Name = 'TRAVELPAYOUTS_TOKEN'; Required = $false; Description = 'TravelPayouts fares' }
    @{ Name = 'IRCTC_RAPIDAPI_KEY'; Required = $false; Description = 'Indian Rail fares' }
    @{ Name = 'IRCTC_RAPIDAPI_HOST'; Required = $false; Description = 'RapidAPI host override' }
)

foreach ($entry in $keyPlan) {
    $value = Resolve-Value -Name $entry.Name -Required:$entry.Required
    if ([string]::IsNullOrWhiteSpace($value)) {
        continue
    }
    Set-Item -Path Env:$($entry.Name) -Value $value
}

Write-Host "Environment variables set for this PowerShell session:" -ForegroundColor Green
foreach ($entry in $keyPlan) {
    $current = Get-Item -Path Env:$($entry.Name) -ErrorAction SilentlyContinue
    if ($current -and $current.Value) {
        $message = "  {0} (length): {1} - {2}" -f $entry.Name, $current.Value.Length, $entry.Description
        Write-Host $message
    } elseif ($entry.Required) {
        $message = "  {0}: NOT SET (required)" -f $entry.Name
        Write-Host $message -ForegroundColor Yellow
    } else {
        $message = "  {0}: not set ({1} disabled)" -f $entry.Name, $entry.Description
        Write-Host $message
    }
}

Write-Host "Run your app in this same terminal (e.g., 'python api.py')."
