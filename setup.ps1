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

# 2. Prepare .agents/skills and .agents/rules directory
Write-Host "`n[2/4] Setting up .agents/ directories..." -ForegroundColor Yellow
$SkillsDir = Join-Path (Get-Location) ".agents\skills"
$RulesDir = Join-Path (Get-Location) ".agents\rules"
New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null
New-Item -ItemType Directory -Force -Path $RulesDir | Out-Null

$GraphifyRulePath = Join-Path $RulesDir "graphify.md"
@"
---
trigger: always_on
description: Consult the graphify knowledge graph at graphify-out/ for codebase and architecture questions.
---

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- For codebase or architecture questions, when ``graphify-out/graph.json`` exists, first run ``graphify query "<question>"`` (CLI) or ``query_graph`` (MCP). Use ``graphify path "<A>" "<B>"`` / ``shortest_path`` for relationships and ``graphify explain "<concept>"`` / ``get_node`` for focused concepts. These return a scoped subgraph, usually much smaller than ``GRAPH_REPORT.md`` or raw grep output.
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context
- After modifying code files in this session, run ``graphify update .`` to keep the graph current (AST-only, no API cost)
"@ | Out-File -FilePath $GraphifyRulePath -Encoding utf8 -Force
Write-Host "  ✓ .agents/rules/graphify.md created." -ForegroundColor Green


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
