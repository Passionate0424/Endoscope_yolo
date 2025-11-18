Param(
    [Parameter(Mandatory = $false)]
    [string]$WeightsPath = ".\yolov5_project\runs\train\endoscope_polyp_detection5\weights\best.pt",
    [Parameter(Mandatory = $false)]
    [int]$ImgSize = 640,
    [Parameter(Mandatory = $false)]
    [string]$OutputDir = ".\build\k230",
    [Parameter(Mandatory = $false)]
    [int]$CalibCount = 100,
    [Parameter(Mandatory = $false)]
    [string]$CalibSource = ".\datasheet\Kvasir-SEG-YOLO\images\val"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-Directory {
    Param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

Write-Host "==> Exporting YOLOv5 to ONNX and preparing K230 compilation assets..."

# 1) Resolve output folders
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$OnnxDir = Join-Path $OutputDir "onnx"
$CalibDir = Join-Path $OutputDir "calib"
New-Directory $OutputDir
New-Directory $OnnxDir
New-Directory $CalibDir

# 2) Verify weights
if (-not (Test-Path -LiteralPath $WeightsPath)) {
    Write-Error "Weights not found: $WeightsPath"
}
$WeightsPath = [System.IO.Path]::GetFullPath($WeightsPath)
Write-Host "Weights: $WeightsPath"

# 3) Export ONNX using yolov5/export.py
Write-Host "==> Running ONNX export..."
$python = "python"
$yoloExport = ".\yolov5\export.py"
if (-not (Test-Path -LiteralPath $yoloExport)) {
    Write-Error "Export script not found: $yoloExport"
}

& $python $yoloExport `
    --weights $WeightsPath `
    --include onnx `
    --imgsz $ImgSize `
    --opset 12 `
| Write-Host

# 4) Locate produced ONNX (Ultralytics names like weights.onnx beside weights or in CWD)
$producedOnnx = Get-ChildItem -Recurse -Filter "*.onnx" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $producedOnnx) {
    Write-Error "ONNX export failed or ONNX file not found."
}
Write-Host "ONNX found: $($producedOnnx.FullName)"

$onnxName = [System.IO.Path]::GetFileNameWithoutExtension($producedOnnx.Name)
$destOnnx = Join-Path $OnnxDir ($onnxName + ".onnx")
Copy-Item -LiteralPath $producedOnnx.FullName -Destination $destOnnx -Force
Write-Host "ONNX copied to: $destOnnx"

# 5) Prepare calibration dataset (copy first N images)
Write-Host "==> Preparing calibration dataset ($CalibCount images) from: $CalibSource"
if (-not (Test-Path -LiteralPath $CalibSource)) {
    Write-Error "Calibration source not found: $CalibSource"
}

$images = Get-ChildItem -LiteralPath $CalibSource -Include *.jpg, *.jpeg, *.png -Recurse | Select-Object -First $CalibCount
if (-not $images -or $images.Count -eq 0) {
    Write-Error "No images found under $CalibSource"
}
foreach ($img in $images) {
    Copy-Item -LiteralPath $img.FullName -Destination (Join-Path $CalibDir $img.Name) -Force
}
Write-Host "Calibration images prepared at: $CalibDir"

# 6) Write an nncase config YAML template
$configPath = Join-Path $OutputDir "k230_yolov5_ncc_config.yaml"
@"
target: k230
quantize:
  dataset: "$CalibDir"
  method: "ptq"
  calibration_samples: $CalibCount
preprocess:
  - input_index: 0
    input_layout: "NCHW"
    mean: [0.0, 0.0, 0.0]
    std: [255.0, 255.0, 255.0]
    model_input_shape: [1, 3, $ImgSize, $ImgSize]
    keep_aspect_ratio: true
    letterbox_value: 114
    resize_mode: "bilinear"
"@ | Set-Content -LiteralPath $configPath -Encoding UTF8

Write-Host "nncase config written: $configPath"

# 7) Print next-step commands for the user
Write-Host ""
Write-Host "==> NEXT STEPS (run locally):"
Write-Host "1) Ensure nncase is installed and on PATH:"
Write-Host "   pip install nncase"
Write-Host "   ncc --version"
Write-Host ""
Write-Host "2) Compile to kmodel (config-based):"
Write-Host "   ncc compile `"$destOnnx`" `"$OutputDir\model.kmodel`" --config `"$configPath`""
Write-Host ""
Write-Host "   Or use a flags-only variant (if your ncc version supports these flags):"
Write-Host "   ncc compile `"$destOnnx`" `"$OutputDir\model.kmodel`" --target k230 --dataset `"$CalibDir`" --input-layout NCHW --input-mean 0 0 0 --input-std 255 255 255 --quantize"
Write-Host ""
Write-Host "Artifacts:"
Write-Host " - ONNX: $destOnnx"
Write-Host " - Calib: $CalibDir"
Write-Host " - Config: $configPath"
Write-Host " - KMODEL (after compile): $OutputDir\model.kmodel"
Write-Host ""
Write-Host "Done."


