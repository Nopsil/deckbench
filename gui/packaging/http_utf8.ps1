# Read an HTTP body as bytes and decode UTF-8.
# Windows PowerShell 5.1's Invoke-RestMethod / Invoke-WebRequest decode the
# body as ISO-8859-1 when Content-Type has no charset, which turns Chinese
# into mojibake. This file is pure ASCII so 5.1 can parse it without a BOM.
# Dot-source it from the other packaging scripts.

function Get-Utf8Response {
  param(
    [Parameter(Mandatory = $true)][string]$Uri,
    [ValidateSet("GET", "POST")][string]$Method = "GET",
    [byte[]]$Body,
    [string]$ContentType,
    [int]$TimeoutSec = 0
  )
  if ($PSBoundParameters.ContainsKey("Body")) {
    if (-not $ContentType) { throw "POST/GET body requires a Content-Type: $Uri" }
    $resp = Invoke-WebRequest -Uri $Uri -Method $Method -Body $Body -ContentType $ContentType -UseBasicParsing -TimeoutSec $TimeoutSec
  } else {
    $resp = Invoke-WebRequest -Uri $Uri -Method $Method -UseBasicParsing -TimeoutSec $TimeoutSec
  }
  $stream = $resp.RawContentStream
  if ($null -eq $stream) { throw "response has no byte stream: $Uri" }
  if ($stream.CanSeek) {
    $null = $stream.Seek(0, [System.IO.SeekOrigin]::Begin)
  }
  $copy = New-Object System.IO.MemoryStream
  try {
    $chunk = New-Object byte[] 8192
    while (($n = $stream.Read($chunk, 0, $chunk.Length)) -gt 0) {
      $copy.Write($chunk, 0, $n)
    }
    $bytes = $copy.ToArray()
  } finally {
    $copy.Dispose()
  }
  $strict = New-Object System.Text.UTF8Encoding $false, $true
  try {
    $text = $strict.GetString($bytes)
  } catch {
    throw "response body is not UTF-8: $Uri ($($_.Exception.Message))"
  }
  if ($text.Length -gt 0 -and [int]$text[0] -eq 0xFEFF) {
    $text = $text.Substring(1)
  }
  $candidates = @()
  if ($null -ne $resp.BaseResponse -and $resp.BaseResponse.ContentType) {
    $candidates += [string]$resp.BaseResponse.ContentType
  }
  if ($null -ne $resp.Headers -and $resp.Headers["Content-Type"]) {
    $candidates += [string]$resp.Headers["Content-Type"]
  }
  $ctype = ""
  foreach ($candidate in $candidates) {
    if ($candidate -match '(?i)charset') { $ctype = $candidate; break }
  }
  if (-not $ctype -and $candidates.Count -gt 0) { $ctype = [string]$candidates[0] }
  return [pscustomobject]@{ Text = $text; ContentType = $ctype; Bytes = $bytes.Length }
}

function ConvertFrom-Utf8Response {
  param(
    [Parameter(Mandatory = $true)]$Response,
    [Parameter(Mandatory = $true)][string]$Uri
  )
  $flat = (([string]$Response.ContentType -replace "\s", "") -replace '"', "").ToLowerInvariant()
  if (-not $flat.StartsWith("application/json")) {
    throw "expected application/json from $Uri (got $($Response.ContentType))"
  }
  if ($flat -notmatch 'charset=utf-8($|;)') {
    throw "JSON response missing charset=utf-8 ($($Response.ContentType)): $Uri"
  }
  if ([string]::IsNullOrWhiteSpace([string]$Response.Text)) {
    throw "empty JSON body: $Uri"
  }
  return ($Response.Text | ConvertFrom-Json)
}

function Invoke-Utf8Json {
  param(
    [Parameter(Mandatory = $true)][string]$Uri,
    [ValidateSet("GET", "POST")][string]$Method = "GET",
    [byte[]]$Body,
    [string]$ContentType,
    [int]$TimeoutSec = 0
  )
  if ($PSBoundParameters.ContainsKey("Body")) {
    $got = Get-Utf8Response -Uri $Uri -Method $Method -Body $Body -ContentType $ContentType -TimeoutSec $TimeoutSec
  } else {
    $got = Get-Utf8Response -Uri $Uri -Method $Method -TimeoutSec $TimeoutSec
  }
  return ConvertFrom-Utf8Response -Response $got -Uri $Uri
}
