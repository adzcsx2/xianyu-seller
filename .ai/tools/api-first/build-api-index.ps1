[CmdletBinding()]
param(
    [string]$WorkspaceRoot = (Get-Location).Path,
    [string]$OutputPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$WorkspaceRoot = [IO.Path]::GetFullPath($WorkspaceRoot)
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $WorkspaceRoot '.ai\index\backend-apis.json'
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)

$ignoredPathPattern = '(^|[\\/])(\.git|\.dart_tool|\.gradle|\.idea|\.venv|\.worktree|build|dist|example|examples|node_modules|target|third_party|vendor|venv)([\\/]|$)'
$httpMethods = @('get', 'post', 'put', 'delete', 'patch', 'head', 'options')
$routes = @{}
$inputSources = @{}
$warnings = [Collections.Generic.List[string]]::new()

function Get-RelativePath([string]$Path) {
    return [IO.Path]::GetRelativePath($WorkspaceRoot, $Path).Replace('\', '/')
}

function Normalize-RoutePath([string]$Prefix, [string]$Path) {
    $left = if ([string]::IsNullOrWhiteSpace($Prefix)) { '' } else { '/' + $Prefix.Trim('/') }
    $right = if ([string]::IsNullOrWhiteSpace($Path)) { '' } else { '/' + $Path.TrimStart('/') }
    $result = ($left + $right) -replace '/+', '/'
    if ([string]::IsNullOrWhiteSpace($result)) { return '/' }
    return $result
}

function Normalize-CatchAllPath([string]$Path, [string]$Handler) {
    # 只有已经绑定到源码 handler 的 catch-all 才去掉 FastAPI converter。
    if ([string]::IsNullOrWhiteSpace($Handler)) { return $Path }
    $match = [regex]::Match($Path, '/\{(?<name>[^}:]+):path\}$')
    if (-not $match.Success) { return $Path }
    return $Path.Substring(0, $match.Index + 1) + '{' + $match.Groups['name'].Value + '}'
}

function Get-KeywordArgument([string]$Arguments, [string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Arguments)) { return '' }
    $pattern = "(?i)(?:^|,)\s*" + [regex]::Escape($Name) + "\s*=\s*(?<value>[^,\)]+)"
    $match = [regex]::Match($Arguments, $pattern)
    if (-not $match.Success) { return '' }
    $value = $match.Groups['value'].Value.Trim()
    return $value.Trim("'").Trim('"')
}

function Get-HandlerMetadata([string[]]$Lines, [int]$RouteIndex) {
    $handler = ''
    $signature = ''
    $limit = [Math]::Min($Lines.Count - 1, $RouteIndex + 30)
    for ($candidateIndex = $RouteIndex + 1; $candidateIndex -le $limit; $candidateIndex += 1) {
        $candidate = $Lines.Item($candidateIndex).ToString()
        $trimmed = $candidate.Trim()
        if ($trimmed.StartsWith('#') -or $trimmed.StartsWith('//')) { continue }
        # 允许连续 decorator（同一 handler 暴露多个兼容路径）继续向下绑定。
        if ($trimmed.StartsWith('@')) { continue }
        if ($candidate -match '^\s*(?:async\s+)?def\s+(?<name>[A-Za-z_]\w*)\s*\(') {
            $handler = $matches.name
            $signature = $candidate
            while ($candidateIndex -lt $limit -and -not $signature.Contains('):')) {
                $candidateIndex += 1
                $nextSignatureLine = $Lines.Item($candidateIndex).ToString()
                $signature += " " + $nextSignatureLine
            }
            break
        }
    }

    $authHint = 'unknown'
    $ownerHint = 'unknown'
    $dependencyMatch = [regex]::Match($signature, '(?i)Depends\(\s*(?<name>[A-Za-z_]\w*)')
    if ($dependencyMatch.Success) {
        $dependency = $dependencyMatch.Groups['name'].Value
        if ($dependency -match '^(?:verify_admin_token|require_admin)$') {
            $authHint = 'admin'
            $ownerHint = 'current_admin'
        } elseif ($dependency -match '^(?:get_current_user|require_auth)$') {
            $authHint = 'authenticated'
            $ownerHint = 'current_user'
        } elseif ($dependency -eq 'verify_token') {
            $authHint = 'optional_authenticated'
            $ownerHint = 'current_user_or_anonymous'
        }
    }

    $requestSchemas = [Collections.Generic.List[string]]::new()
    foreach ($parameter in [regex]::Matches($signature, '(?<name>[A-Za-z_]\w*)\s*:\s*(?<type>[A-Za-z_]\w*(?:\[[^\]]+\])?)')) {
        $name = $parameter.Groups['name'].Value
        $type = $parameter.Groups['type'].Value
        if ($name -in @('self', 'request', 'credentials', 'current_user', 'user_info', 'path')) { continue }
        if ($type -match '(?i)(?:Request|Payload|Create|Update|Model|Schema)$') {
            if (-not $requestSchemas.Contains($type)) { $requestSchemas.Add($type) }
        }
    }

    return [ordered]@{
        handler = $handler
        signature = $signature
        auth_hint = $authHint
        owner_hint = $ownerHint
        request_schemas = @($requestSchemas)
    }
}

function Get-Property($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $Default }
    return $property.Value
}

function Get-SchemaName($Schema) {
    if ($null -eq $Schema) { return '' }
    $reference = Get-Property $Schema '$ref' ''
    if ($reference) { return [string]$reference }
    return [string](Get-Property $Schema 'type' '')
}

function Add-InputSource([string]$AbsolutePath) {
    $relative = Get-RelativePath $AbsolutePath
    if (-not $inputSources.ContainsKey($relative)) {
        $inputSources[$relative] = (Get-FileHash -LiteralPath $AbsolutePath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

function Add-Route {
    param(
        [string]$Method,
        [string]$Path,
        [string]$Summary = '',
        [string]$Description = '',
        [string[]]$Tags = @(),
        [string]$OperationId = '',
        [string]$Handler = '',
        [string[]]$Parameters = @(),
        [string[]]$RequestSchemas = @(),
        [string[]]$ResponseSchemas = @(),
        [string]$AuthHint = 'unknown',
        [string]$OwnerHint = 'unknown',
        [string]$SourceKind,
        [string]$SourcePath,
        [int]$SourceLine = 0
    )

    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    $normalizedMethod = $Method.ToUpperInvariant()
    $normalizedPath = Normalize-RoutePath '' $Path
    $key = "$normalizedMethod $normalizedPath"
    if (-not $routes.ContainsKey($key)) {
        $routes[$key] = [ordered]@{
            method = $normalizedMethod
            path = $normalizedPath
            summary = $Summary
            description = $Description
            tags = [Collections.Generic.List[string]]::new()
            operation_id = $OperationId
            auth_hint = $AuthHint
            owner_hint = $OwnerHint
            handler = $Handler
            parameters = [Collections.Generic.List[string]]::new()
            request_schemas = [Collections.Generic.List[string]]::new()
            response_schemas = [Collections.Generic.List[string]]::new()
            sources = [Collections.Generic.List[object]]::new()
        }
    }

    $route = $routes[$key]
    if (-not $route.summary -and $Summary) { $route.summary = $Summary }
    if (-not $route.description -and $Description) { $route.description = $Description }
    if (-not $route.operation_id -and $OperationId) { $route.operation_id = $OperationId }
    if (-not $route.handler -and $Handler) { $route.handler = $Handler }
    if ($route.auth_hint -eq 'unknown' -and $AuthHint -ne 'unknown') { $route.auth_hint = $AuthHint }
    if ($route.owner_hint -eq 'unknown' -and $OwnerHint -ne 'unknown') { $route.owner_hint = $OwnerHint }
    foreach ($value in @($Tags)) { if ($value -and -not $route.tags.Contains($value)) { $route.tags.Add($value) } }
    foreach ($value in @($Parameters)) { if ($value -and -not $route.parameters.Contains($value)) { $route.parameters.Add($value) } }
    foreach ($value in @($RequestSchemas)) { if ($value -and -not $route.request_schemas.Contains($value)) { $route.request_schemas.Add($value) } }
    foreach ($value in @($ResponseSchemas)) { if ($value -and -not $route.response_schemas.Contains($value)) { $route.response_schemas.Add($value) } }
    $sourceKey = "$SourceKind|$SourcePath|$SourceLine"
    $alreadyAdded = @($route.sources | Where-Object { "$($_.kind)|$($_.path)|$($_.line)" -eq $sourceKey }).Count -gt 0
    if (-not $alreadyAdded) {
        $route.sources.Add([ordered]@{ kind = $SourceKind; path = $SourcePath; line = $SourceLine })
    }
}

$allFiles = Get-ChildItem -LiteralPath $WorkspaceRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch $ignoredPathPattern }

$openApiFiles = @($allFiles | Where-Object {
    $_.Extension -eq '.json' -and $_.Name -match '(?i)(openapi|swagger)'
})
foreach ($file in $openApiFiles) {
    try {
        $document = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
        $paths = Get-Property $document 'paths'
        if ($null -eq $paths) { continue }
        Add-InputSource $file.FullName
        foreach ($pathProperty in $paths.PSObject.Properties) {
            foreach ($method in $httpMethods) {
                $operationProperty = $pathProperty.Value.PSObject.Properties[$method]
                if ($null -eq $operationProperty) { continue }
                $operation = $operationProperty.Value
                $parameters = [Collections.Generic.List[string]]::new()
                $requestSchemas = [Collections.Generic.List[string]]::new()
                foreach ($parameter in @(Get-Property $operation 'parameters' @())) {
                    $schema = Get-Property $parameter 'schema'
                    $schemaName = Get-SchemaName $schema
                    $location = [string](Get-Property $parameter 'in' '')
                    $name = [string](Get-Property $parameter 'name' '')
                    $parameters.Add("${location}:${name}:$schemaName")
                    if ($location -eq 'body' -and $schemaName) { $requestSchemas.Add($schemaName) }
                }
                $requestBody = Get-Property $operation 'requestBody'
                if ($null -ne $requestBody) {
                    $content = Get-Property $requestBody 'content'
                    if ($null -ne $content) {
                        foreach ($contentType in $content.PSObject.Properties) {
                            $schemaName = Get-SchemaName (Get-Property $contentType.Value 'schema')
                            if ($schemaName) { $requestSchemas.Add($schemaName) }
                        }
                    }
                }
                $responseSchemas = [Collections.Generic.List[string]]::new()
                $responses = Get-Property $operation 'responses'
                if ($null -ne $responses) {
                    foreach ($response in $responses.PSObject.Properties) {
                        $schemaName = Get-SchemaName (Get-Property $response.Value 'schema')
                        if ($schemaName) { $responseSchemas.Add("$($response.Name):$schemaName") }
                    }
                }
                Add-Route -Method $method -Path $pathProperty.Name `
                    -Summary ([string](Get-Property $operation 'summary' '')) `
                    -Description ([string](Get-Property $operation 'description' '')) `
                    -Tags @((Get-Property $operation 'tags' @())) `
                    -OperationId ([string](Get-Property $operation 'operationId' '')) `
                    -Parameters @($parameters) -RequestSchemas @($requestSchemas) -ResponseSchemas @($responseSchemas) `
                    -SourceKind 'openapi' -SourcePath (Get-RelativePath $file.FullName)
            }
        }
    } catch {
        $warnings.Add("Could not parse OpenAPI candidate $(Get-RelativePath $file.FullName): $($_.Exception.Message)")
    }
}

$routeFilePattern = '(?i)(route|router|routing|controller|handler|http[_-]?server|endpoint|api)'
$sourceExtensions = @('.go', '.js', '.jsx', '.ts', '.tsx', '.py', '.java', '.kt', '.cs')
$routeFiles = @($allFiles | Where-Object {
    $_.Extension -in $sourceExtensions -and
        (($_.FullName -match $routeFilePattern) -or $_.Name -eq 'reply_server.py') -and
        $_.BaseName -notmatch '(?i)(^test_|_test$|\.spec$|\.test$)'
})

foreach ($file in $routeFiles) {
    $lines = @(Get-Content -LiteralPath $file.FullName)
    $relative = Get-RelativePath $file.FullName
    $prefixes = @{ app = ''; router = ''; r = ''; e = '' }
    $mountPrefixes = @{}
    $classPrefix = ''
    $matchedFile = $false

    # 先收集 Python APIRouter 的自身前缀和 include_router 挂载前缀，
    # 再扫描 decorator，避免声明顺序影响最终路径。
    for ($prefixIndex = 0; $prefixIndex -lt $lines.Count; $prefixIndex += 1) {
        $prefixLine = [string]$lines[$prefixIndex]
        $trimmedPrefixLine = $prefixLine.TrimStart()
        if ($trimmedPrefixLine.StartsWith('#') -or $trimmedPrefixLine.StartsWith('//')) { continue }
        $routerDeclaration = [regex]::Match($prefixLine, '^\s*(?<name>[A-Za-z_]\w*)\s*=\s*APIRouter\((?<arguments>.*)\)\s*$')
        if ($routerDeclaration.Success) {
            $routerPrefix = Get-KeywordArgument $routerDeclaration.Groups['arguments'].Value 'prefix'
            $prefixes[$routerDeclaration.Groups['name'].Value] = Normalize-RoutePath '' $routerPrefix
        }
        $includeMatch = [regex]::Match($prefixLine, '\.include_router\(\s*(?<name>[A-Za-z_]\w*)(?<arguments>[^\)]*)\)')
        if ($includeMatch.Success) {
            $mountPrefix = Get-KeywordArgument $includeMatch.Groups['arguments'].Value 'prefix'
            $mountPrefixes[$includeMatch.Groups['name'].Value] = Normalize-RoutePath '' $mountPrefix
        }
    }

    for ($index = 0; $index -lt $lines.Count; $index += 1) {
        $line = [string]$lines[$index]
        $trimmedLine = $line.TrimStart()
        if ($trimmedLine.StartsWith('#') -or $trimmedLine.StartsWith('//')) { continue }
        if ($line -match '(?<name>[A-Za-z_]\w*)\s*:?=\s*(?<parent>[A-Za-z_]\w*)\.(?:Party|Group)\(\s*["''](?<path>[^"'']+)["'']') {
            $parentPrefix = if ($prefixes.ContainsKey($matches.parent)) { [string]$prefixes[$matches.parent] } else { '' }
            $prefixes[$matches.name] = Normalize-RoutePath $parentPrefix $matches.path
        }
        if ($line -match '@RequestMapping\(\s*(?:value\s*=\s*)?["''](?<path>[^"'']+)["'']') {
            $classPrefix = $matches.path
        }

        $routeMatch = [regex]::Match($line, '(?<receiver>[A-Za-z_]\w*)\.(?<method>Get|Post|Put|Delete|Patch|Head|Options|GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\(\s*["''](?<path>[^"'']+)["'']')
        if ($routeMatch.Success) {
            $receiver = $routeMatch.Groups['receiver'].Value
            $prefix = if ($prefixes.ContainsKey($receiver)) { [string]$prefixes[$receiver] } else { '' }
            Add-Route -Method $routeMatch.Groups['method'].Value -Path (Normalize-RoutePath $prefix $routeMatch.Groups['path'].Value) `
                -SourceKind 'code' -SourcePath $relative -SourceLine ($index + 1)
            $matchedFile = $true
            continue
        }

        $decoratorMatch = [regex]::Match($line, '@(?:app|router|blueprint)\.(?<method>get|post|put|delete|patch|head|options)\(\s*["''](?<path>[^"'']+)["'']', 'IgnoreCase')
        if ($decoratorMatch.Success) {
            $receiverMatch = [regex]::Match($line, '@(?<receiver>[A-Za-z_]\w*)\.', 'IgnoreCase')
            $receiver = if ($receiverMatch.Success) { $receiverMatch.Groups['receiver'].Value } else { '' }
            $prefix = if ($prefixes.ContainsKey($receiver)) { [string]$prefixes[$receiver] } else { '' }
            $mountPrefix = if ($mountPrefixes.ContainsKey($receiver)) { [string]$mountPrefixes[$receiver] } else { '' }
            $handlerMetadata = Get-HandlerMetadata $lines $index
            $routePath = Normalize-RoutePath (Normalize-RoutePath $mountPrefix $prefix) $decoratorMatch.Groups['path'].Value
            $routePath = Normalize-CatchAllPath $routePath $handlerMetadata.handler
            $argumentsStart = $line.IndexOf('(')
            $arguments = if ($argumentsStart -ge 0) { $line.Substring($argumentsStart + 1) } else { '' }
            $responseModel = Get-KeywordArgument $arguments 'response_model'
            $responseSchemas = if ($responseModel) { @($responseModel) } else { @() }
            Add-Route -Method $decoratorMatch.Groups['method'].Value -Path $routePath `
                -Handler $handlerMetadata.handler -RequestSchemas $handlerMetadata.request_schemas `
                -ResponseSchemas $responseSchemas -AuthHint $handlerMetadata.auth_hint `
                -OwnerHint $handlerMetadata.owner_hint -SourceKind 'code' -SourcePath $relative -SourceLine ($index + 1)
            $matchedFile = $true
            continue
        }

        $mappingMatch = [regex]::Match($line, '@(?<method>Get|Post|Put|Delete|Patch)Mapping\(\s*(?:value\s*=\s*)?["''](?<path>[^"'']+)["'']')
        if ($mappingMatch.Success) {
            Add-Route -Method $mappingMatch.Groups['method'].Value -Path (Normalize-RoutePath $classPrefix $mappingMatch.Groups['path'].Value) `
                -SourceKind 'code' -SourcePath $relative -SourceLine ($index + 1)
            $matchedFile = $true
        }
    }
    if ($matchedFile) { Add-InputSource $file.FullName }
}

# 项目中的知识内容路由由同一注册器展开，源码 decorator 使用 f-string
# 因而无法仅靠静态正则得到四类具体路径。把注册器的有限、显式 kind 集合
# 展开到索引中，仍保留同一源码行作为追踪来源，避免 API-first 漏掉真实路由。
$knowledgeRouteFile = Join-Path $WorkspaceRoot 'app/reply_server.py'
if (Test-Path -LiteralPath $knowledgeRouteFile) {
    $knowledgeLines = @(Get-Content -LiteralPath $knowledgeRouteFile)
    $registerLine = 0
    for ($i = 0; $i -lt $knowledgeLines.Count; $i += 1) {
        if ([string]$knowledgeLines[$i] -match 'def _register_content_routes') { $registerLine = $i + 1; break }
    }
    if ($registerLine -gt 0 -and (Select-String -LiteralPath $knowledgeRouteFile -Pattern '_register_content_routes\(' -Quiet)) {
        foreach ($kind in @('facts', 'sources', 'rules', 'qa-entries')) {
            foreach ($method in @('GET', 'POST', 'PUT', 'DELETE')) {
                $path = "/knowledge-bases/{base_id}/$kind"
                if ($method -in @('PUT', 'DELETE')) { $path += '/{content_id}' }
                $request = if ($method -in @('POST', 'PUT')) { @('body:KnowledgeMutationRequest') } else { @() }
                $parameters = @('path:base_id:string')
                if ($method -in @('PUT', 'DELETE')) { $parameters += 'path:content_id:string' }
                if ($method -eq 'DELETE') { $parameters += 'query:expected_version:integer' }
                Add-Route -Method $method -Path $path -Handler '_register_content_routes' -Parameters $parameters -RequestSchemas $request -AuthHint 'authenticated' -OwnerHint 'current_user' -SourceKind 'code' -SourcePath 'app/reply_server.py' -SourceLine $registerLine
            }
        }
    }
}

if ($routes.Count -eq 0) {
    $warnings.Add('No routes were indexed. Adapt this project-local builder to the repository route-registration pattern before relying on API-first search.')
}
if ($openApiFiles.Count -eq 0) {
    $warnings.Add('No OpenAPI/Swagger JSON contract was found; indexed code routes may have incomplete summaries and schemas.')
}

$sortedRoutes = @($routes.Values | ForEach-Object {
    [ordered]@{
        method = $_.method
        path = $_.path
        summary = $_.summary
        description = $_.description
        tags = @($_.tags)
        operation_id = $_.operation_id
        auth_hint = $_.auth_hint
        owner_hint = $_.owner_hint
        handler = $_.handler
        parameters = @($_.parameters)
        request_schemas = @($_.request_schemas)
        response_schemas = @($_.response_schemas)
        sources = @($_.sources)
    }
} | Sort-Object `
    @{ Expression = { $_['path'] }; Ascending = $true }, `
    @{ Expression = { $_['method'] }; Ascending = $true })

$document = [ordered]@{
    schema_version = 1
    generated_at_utc = [DateTime]::UtcNow.ToString('o')
    metadata = [ordered]@{
        route_count = $sortedRoutes.Count
        sources = @($inputSources.GetEnumerator() | Sort-Object Name | ForEach-Object {
            [ordered]@{ path = $_.Name; sha256 = $_.Value }
        })
        warnings = @($warnings)
    }
    routes = $sortedRoutes
}

[IO.Directory]::CreateDirectory((Split-Path -Parent $OutputPath)) | Out-Null
[IO.File]::WriteAllText($OutputPath, ($document | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Output "API_INDEX_BUILT routes=$($sortedRoutes.Count) sources=$($inputSources.Count) warnings=$($warnings.Count) output=$OutputPath"
