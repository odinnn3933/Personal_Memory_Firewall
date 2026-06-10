$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$targets = @(
    "memory_gateway.db",
    ".pytest_cache",
    ".ruff_cache",
    "apps/desktop/vite-preview.err.log",
    "apps/desktop/vite-preview.out.log",
    "apps/desktop/dist",
    "apps/desktop/node_modules",
    "apps/desktop/src-tauri/target",
    "apps/desktop/src-tauri/gen/schemas"
)

foreach ($relative in $targets) {
    $path = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $path)) {
        continue
    }
    $resolved = (Resolve-Path -LiteralPath $path).Path
    if (-not $resolved.StartsWith($root)) {
        throw "Refusing to remove outside workspace: $resolved"
    }
    try {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction Stop
        Write-Host "removed $relative" -ForegroundColor Green
    }
    catch {
        Write-Host "could not remove $relative" -ForegroundColor Yellow
        Write-Host $_.Exception.Message
    }
}

Write-Host "Local artifact cleanup finished." -ForegroundColor Cyan
