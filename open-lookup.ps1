# Start local server and open IRM lookup UI in default browser.
#
# Usage:
#   .\open-lookup.ps1           # Just for you (localhost only)
#   .\open-lookup.ps1 -Share    # Teammates on same VPN/Wi-Fi can connect
param(
    [switch]$Share
)

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir

$port = 8765

# Stop any existing server on this port (best effort)
Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

if ($Share) {
    Start-Process py -ArgumentList "-m", "http.server", $port, "--bind", "0.0.0.0", "--directory", $dir -WindowStyle Hidden
    $ip = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.InterfaceAlias -notmatch 'Loopback' -and $_.IPAddress -notmatch '^169\.254\.' } |
        Select-Object -First 1).IPAddress
    $url = "http://localhost:$port/lookup.html"
    $shareUrl = if ($ip) { "http://${ip}:$port/lookup.html" } else { "(could not detect IP - use ipconfig)" }
    Start-Sleep -Seconds 1
    Start-Process $url
    Write-Host ""
    Write-Host "Opened for you:     $url"
    Write-Host "Share with others:  $shareUrl"
    Write-Host ""
    Write-Host "Teammates must be on the same VPN or office network."
    Write-Host "Your PC must stay on and this server running."
    Write-Host "If the link does not work, allow Python through Windows Firewall when prompted."
} else {
    Start-Process py -ArgumentList "-m", "http.server", $port, "--directory", $dir -WindowStyle Hidden
    $url = "http://localhost:$port/lookup.html"
    Start-Sleep -Seconds 1
    Start-Process $url
    Write-Host "Opened $url"
    Write-Host ""
    Write-Host "To share with teammates on the same network, run:"
    Write-Host "  .\open-lookup.ps1 -Share"
}

Write-Host ""
Write-Host "Keep this window open while using the tool. Close it or stop Python to shut down the server."
