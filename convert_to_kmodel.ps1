# YOLOv5模型转换为K230 kmodel脚本
# 使用官方 test_yolov5/detect/to_kmodel.py 进行转换

Param(
    [Parameter(Mandatory = $false)]
    [string]$OnnxPath = ".\build\k230_pytorch_env\onnx\best.onnx",
    [Parameter(Mandatory = $false)]
    [string]$CalibDir = ".\build\k230_pytorch_env\calib",
    [Parameter(Mandatory = $false)]
    [int]$InputWidth = 640,
    [Parameter(Mandatory = $false)]
    [int]$InputHeight = 640,
    [Parameter(Mandatory = $false)]
    [string]$OutputDir = ".\build\k230_pytorch_env",
    [Parameter(Mandatory = $false)]
    [int]$PtqOption = 3,
    [Parameter(Mandatory = $false)]
    [string]$Target = "k230"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "==> Converting ONNX model to K230 kmodel..."
Write-Host "ONNX: $OnnxPath"
Write-Host "Calibration dataset: $CalibDir"
Write-Host "Input size: ${InputWidth}x${InputHeight}"
Write-Host "PTQ option: $PtqOption (Kld calibration, uint8 quant)"
Write-Host ""

# 验证文件存在
if (-not (Test-Path -LiteralPath $OnnxPath)) {
    Write-Error "ONNX file not found: $OnnxPath"
}

if (-not (Test-Path -LiteralPath $CalibDir)) {
    Write-Error "Calibration directory not found: $CalibDir"
}

# 运行转换脚本
$python = "python"
$convertScript = ".\test_yolov5\detect\to_kmodel.py"

if (-not (Test-Path -LiteralPath $convertScript)) {
    Write-Error "Conversion script not found: $convertScript"
}

Write-Host "Running conversion script..."
& $python $convertScript `
    --target $Target `
    --model $OnnxPath `
    --dataset $CalibDir `
    --input_width $InputWidth `
    --input_height $InputHeight `
    --ptq_option $PtqOption

if ($LASTEXITCODE -ne 0) {
    Write-Error "Conversion failed with exit code $LASTEXITCODE"
}

# 查找生成的kmodel文件（脚本会在ONNX同目录生成）
$onnxDir = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($OnnxPath))
$onnxBaseName = [System.IO.Path]::GetFileNameWithoutExtension($OnnxPath)
$generatedKmodel = Join-Path $onnxDir ($onnxBaseName + ".kmodel")

if (Test-Path -LiteralPath $generatedKmodel) {
    # 移动到输出目录
    $outputKmodel = Join-Path $OutputDir "model.kmodel"
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    Move-Item -Path $generatedKmodel -Destination $outputKmodel -Force
    Write-Host ""
    Write-Host "==> Conversion successful!"
    Write-Host "Kmodel saved to: $outputKmodel"
    $fileInfo = Get-Item $outputKmodel
    Write-Host "File size: $([math]::Round($fileInfo.Length / 1MB, 2)) MB"
}
else {
    Write-Error "Kmodel file not found: $generatedKmodel"
}

Write-Host ""
Write-Host "==> Next steps:"
Write-Host "1. Copy the kmodel file to your K230/CanMV device"
Write-Host "2. Use the model in your inference code on the device"
Write-Host "3. Ensure input preprocessing matches: NCHW, uint8, 640x640"
Write-Host ""




