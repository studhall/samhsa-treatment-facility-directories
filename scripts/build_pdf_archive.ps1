param(
  [Parameter(Mandatory = $true)]
  [string]$PdfDir,
  [string]$AuditPath = "release/source_rights_audit.json",
  [string]$OutputZip = "release/samhsa_directory_pdfs.zip"
)

$audit = Get-Content -Raw -LiteralPath $AuditPath | ConvertFrom-Json
$blocked = @($audit | Where-Object { -not $_.archive_eligible })
if ($blocked.Count -gt 0) {
  throw "Source-rights audit has blocked years: $($blocked.directory_year -join ', ')"
}

$files = @($audit | ForEach-Object { Join-Path $PdfDir $_.filename })
$missing = @($files | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($missing.Count -gt 0) {
  throw "Missing source PDFs: $($missing -join ', ')"
}

$outputParent = Split-Path -Parent $OutputZip
if ($outputParent) {
  New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
}
Compress-Archive -LiteralPath $files -DestinationPath $OutputZip -Force
Write-Host "Wrote $OutputZip"

