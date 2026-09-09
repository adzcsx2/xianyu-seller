[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Query,
    [ValidateRange(1, 50)]
    [int]$Top = 10,
    [string]$WorkspaceRoot = (Get-Location).Path,
    [string]$IndexPath,
    [switch]$AsJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$WorkspaceRoot = [IO.Path]::GetFullPath($WorkspaceRoot)
if ([string]::IsNullOrWhiteSpace($IndexPath)) {
    $IndexPath = Join-Path $WorkspaceRoot '.ai\index\backend-apis.json'
}
$IndexPath = [IO.Path]::GetFullPath($IndexPath)
if (-not (Test-Path -LiteralPath $IndexPath -PathType Leaf)) {
    throw "API index is missing. Run build-api-index.ps1 first: $IndexPath"
}

function Add-Token([Collections.Generic.HashSet[string]]$Tokens, [string]$Value) {
    $normalized = $Value.Trim().ToLowerInvariant()
    if ($normalized.Length -lt 2 -or $normalized -in @('是否', '可以', '这个', '一下', '帮我', '需要', 'the', 'and', 'for', 'with')) { return }
    $null = $Tokens.Add($normalized)
}

$index = Get-Content -LiteralPath $IndexPath -Raw | ConvertFrom-Json
$staleSources = [Collections.Generic.List[string]]::new()
foreach ($source in @($index.metadata.sources)) {
    $sourcePath = Join-Path $WorkspaceRoot ([string]$source.path)
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        $staleSources.Add("$($source.path):missing")
        continue
    }
    $actualHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne [string]$source.sha256) { $staleSources.Add("$($source.path):changed") }
}
if ($staleSources.Count -gt 0) {
    Write-Warning "API index is stale ($($staleSources -join ', ')). Rebuild it before relying on results."
}

$tokens = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($part in ($Query -split '[\s,，;；/|]+')) { Add-Token $tokens $part }
foreach ($match in [regex]::Matches($Query, '[A-Za-z][A-Za-z0-9_-]+')) { Add-Token $tokens $match.Value }
foreach ($match in [regex]::Matches($Query, '[\u4e00-\u9fff]{2,}')) {
    $sequence = $match.Value
    Add-Token $tokens $sequence
    for ($length = 2; $length -le [Math]::Min(4, $sequence.Length); $length += 1) {
        for ($offset = 0; $offset + $length -le $sequence.Length; $offset += 1) {
            Add-Token $tokens $sequence.Substring($offset, $length)
        }
    }
}
if ($tokens.Count -eq 0) { throw 'Query must contain at least one meaningful token.' }

$scored = foreach ($route in @($index.routes)) {
    $path = ([string]$route.path).ToLowerInvariant()
    $summary = ([string]$route.summary).ToLowerInvariant()
    $description = ([string]$route.description).ToLowerInvariant()
    $tags = (@($route.tags) -join ' ').ToLowerInvariant()
    $handler = (([string]$route.handler) + ' ' + ([string]$route.operation_id)).ToLowerInvariant()
    $contract = ((@($route.parameters) + @($route.request_schemas) + @($route.response_schemas)) -join ' ').ToLowerInvariant()
    $score = 0
    $matched = [Collections.Generic.List[string]]::new()
    foreach ($token in $tokens) {
        $tokenScore = 0
        if ($path.Contains($token)) { $tokenScore += 9 }
        if ($summary.Contains($token)) { $tokenScore += 7 }
        if ($tags.Contains($token)) { $tokenScore += 6 }
        if ($handler.Contains($token)) { $tokenScore += 5 }
        if ($contract.Contains($token)) { $tokenScore += 3 }
        if ($description.Contains($token)) { $tokenScore += 2 }
        if ($tokenScore -gt 0) { $score += $tokenScore; $matched.Add($token) }
    }
    if ($score -gt 0) {
        $primarySource = @($route.sources | Select-Object -First 1)
        [pscustomobject][ordered]@{
            score = $score
            method = $route.method
            path = $route.path
            auth_hint = $route.auth_hint
            handler = $route.handler
            summary = $route.summary
            matched_tokens = @($matched | Select-Object -Unique)
            source = if ($primarySource.Count -gt 0) { "$($primarySource[0].path):$($primarySource[0].line)" } else { '' }
        }
    }
}

$results = @($scored | Sort-Object @{ Expression = 'score'; Descending = $true }, path, method | Select-Object -First $Top)
$payload = [ordered]@{
    query = $Query
    tokens = @($tokens | Sort-Object)
    stale = $staleSources.Count -gt 0
    results = $results
}
if ($AsJson) { $payload | ConvertTo-Json -Depth 8; exit 0 }

Write-Output "API_INDEX_SEARCH query=$Query candidates=$($results.Count) stale=$($staleSources.Count -gt 0)"
if ($results.Count -eq 0) {
    Write-Output 'No indexed candidate matched. Verify with direct route/controller searches before proposing a new endpoint.'
    exit 0
}
$results | Format-Table score, method, path, auth_hint, handler, summary, source -Wrap -AutoSize
