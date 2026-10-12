# Pondside screen capture helper.
#
# The window is borderless and drawn entirely on a Tk canvas, so the only way
# to see what a person sees is to grab the screen. Used to verify UI work.
#
#   powershell -File tools\shot.ps1 -Out shot.png
#   powershell -File tools\shot.ps1 -X 1340 -Y 315 -W 120 -H 40 -Out band.png -Count 120
#
# With -Count > 1 the frames are written as band_000.png, band_001.png, ...

param(
    [int]$X = 1092,          # window origin, left
    [int]$Y = 80,            # window origin, top
    [int]$W = 760,           # window is 760x940
    [int]$H = 940,
    [string]$Out = "shot.png",
    [int]$Count = 1,
    [int]$DelayMs = 0
)

Add-Type -AssemblyName System.Drawing

$dir = Split-Path -Parent $Out
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
$stem = [System.IO.Path]::GetFileNameWithoutExtension($Out)
$ext  = [System.IO.Path]::GetExtension($Out)
$base = Split-Path -Parent $Out
if (-not $base) { $base = "." }

for ($i = 0; $i -lt $Count; $i++) {
    $bmp = New-Object System.Drawing.Bitmap $W, $H
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($X, $Y, 0, 0, $bmp.Size)
    $g.Dispose()
    if ($Count -eq 1) {
        $path = $Out
    } else {
        $path = Join-Path $base ("{0}_{1:d3}{2}" -f $stem, $i, $ext)
    }
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    if ($DelayMs -gt 0) { Start-Sleep -Milliseconds $DelayMs }
}
Write-Output "wrote $Count frame(s) to $base"
