<#
.SYNOPSIS
  Build the Ubuntu 24.04 .deb from a Windows (or any Docker) host.

  Uses a throwaway official ubuntu:24.04 container, so the build always
  starts from a clean, known system. Output: release\tracknet-prepper_<ver>_amd64.deb
#>
param([switch]$SkipTests, [switch]$Gpu)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$skip = if ($SkipTests) { "1" } else { "0" }
# -Gpu: expose the NVIDIA GPU incl. NVDEC/NVENC libraries ("video" capability)
$gpuArgs = if ($Gpu) { @("--gpus", "all", "-e", "NVIDIA_DRIVER_CAPABILITIES=compute,utility,video") } else { @() }
docker run --rm @gpuArgs `
  -v "${Root}:/src" `
  -e SRC=/src -e OUT=/src/release -e SKIP_TESTS=$skip `
  ubuntu:24.04 bash /src/packaging/linux/build_linux.sh
if ($LASTEXITCODE -ne 0) { Write-Error "Linux build failed ($LASTEXITCODE)"; exit 1 }
