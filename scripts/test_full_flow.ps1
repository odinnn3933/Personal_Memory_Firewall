$ErrorActionPreference = "Stop"

function Run-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )

    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    & $Command
    Write-Host "PASS: $Name" -ForegroundColor Green
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Run-Step "Backend pytest" {
    python -m pytest -q
}

Run-Step "End-to-end product flow demo" {
    python examples\full_system_flow_demo.py
}

Run-Step "Relationship memory demo" {
    python examples\relationship_memory_demo.py
}

Run-Step "Agent request flow demo" {
    python examples\agent_request_flow_demo.py
}

Run-Step "Project share pack demo" {
    python examples\project_share_demo.py
}

Run-Step "Desktop TypeScript/Vite build" {
    Push-Location apps\desktop
    try {
        npm run build
    }
    finally {
        Pop-Location
    }
}

Run-Step "Tauri cargo check" {
    Push-Location apps\desktop\src-tauri
    try {
        cargo check
    }
    finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "FULL FLOW CHECK PASS" -ForegroundColor Green
