# Godot Dynamic Harness - Automated Setup Script
# https://github.com/KowaiiRuju/Godot-Dynamic-Harness

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   🎮 Initializing Godot Dynamic Harness Environment...    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Install Graphify (Knowledge Graph generator)
Write-Host "`n[1/4] Checking Graphify installation..." -ForegroundColor Yellow
if (Get-Command pip -ErrorAction SilentlyContinue) {
    pip install graphifyy --quiet
    if (Get-Command graphify -ErrorAction SilentlyContinue) {
        graphify install
        Write-Host "  ✓ Graphify ready." -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Graphify installed via pip. Ensure Python Scripts directory is in your PATH." -ForegroundColor DarkYellow
    }
} else {
    Write-Host "  ⚠ pip not found. Please install Python to use Graphify." -ForegroundColor Red
}

# 2. Prepare .agents/skills directory
Write-Host "`n[2/4] Setting up .agents/skills/ directory..." -ForegroundColor Yellow
$SkillsDir = Join-Path (Get-Location) ".agents\skills"
New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null

# 3. Clone Ponytail (Anti-bloat & YAGNI rules)
Write-Host "`n[3/4] Pulling Ponytail & Prompt Master..." -ForegroundColor Yellow
$PonytailPath = Join-Path $SkillsDir "ponytail"
if (-not (Test-Path $PonytailPath)) {
    git clone https://github.com/DietrichGebert/ponytail.git $PonytailPath --quiet
    Write-Host "  ✓ Ponytail installed." -ForegroundColor Green
} else {
    Write-Host "  ✓ Ponytail already present." -ForegroundColor Green
}

# Clone Prompt Master
$PromptMasterPath = Join-Path $SkillsDir "prompt-master"
if (-not (Test-Path $PromptMasterPath)) {
    git clone https://github.com/nidhinjs/prompt-master.git $PromptMasterPath --quiet
    Write-Host "  ✓ Prompt Master installed." -ForegroundColor Green
} else {
    Write-Host "  ✓ Prompt Master already present." -ForegroundColor Green
}

# 4. Clone GD-Agentic-Skills
Write-Host "`n[4/4] Pulling 44 Godot Domain Skills..." -ForegroundColor Yellow
$GdSkillsPath = Join-Path $SkillsDir "gd-agentic-skills"
if (-not (Test-Path $GdSkillsPath)) {
    git clone https://github.com/thedivergentai/GD-Agentic-Skills.git $GdSkillsPath --quiet
    Write-Host "  ✓ GD-Agentic-Skills installed (44 domain skills ready for curation)." -ForegroundColor Green
} else {
    Write-Host "  ✓ GD-Agentic-Skills already present." -ForegroundColor Green
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  ✅ Setup complete! Paste Godot_Dynamic_Harness_Prompt.txt " -ForegroundColor Green
Write-Host "     into your AI agent to curate skills and build rules!   " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
