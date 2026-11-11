# Godot Dynamic Harness - Automated Setup Script
# https://github.com/KowaiiRuju/Godot-Dynamic-Harness

param(
    [string]$TargetProject = (Get-Location).Path
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   🎮 Initializing Godot Dynamic Harness Environment...    " -ForegroundColor Cyan
Write-Host "   Target: $TargetProject" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Install Graphify (Knowledge Graph generator)
Write-Host "`n[1/6] Checking Graphify installation..." -ForegroundColor Yellow
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

# 2. Prepare project directories
Write-Host "`n[2/6] Setting up project directories..." -ForegroundColor Yellow
$SkillsDir = Join-Path $TargetProject ".agents\skills"
$RulesDir = Join-Path $TargetProject ".agents\rules"
$WorkflowsDir = Join-Path $TargetProject ".agents\workflows"
$ToolsDir = Join-Path $TargetProject "tools"
$CoreToolsDir = Join-Path $TargetProject "core\tools"
$AgentStateLogsDir = Join-Path $TargetProject ".agent-state\logs"
$HarnessDir = Join-Path $TargetProject ".harness"
$TestsDir = Join-Path $TargetProject "tests"

$DirsToCreate = @($SkillsDir, $RulesDir, $WorkflowsDir, $ToolsDir, $CoreToolsDir, $AgentStateLogsDir, $HarnessDir, $TestsDir)
foreach ($d in $DirsToCreate) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Force -Path $d | Out-Null
    }
}
Write-Host "  ✓ Target directories created (.agents, tools, core/tools, .agent-state/logs, .harness, tests)." -ForegroundColor Green

# 3. Deploy templates and CLI tools
Write-Host "`n[3/6] Deploying harness templates and CLI tools..." -ForegroundColor Yellow
$LocalTemplatesDir = Join-Path $PSScriptRoot "templates"
$HasLocalTemplates = Test-Path $LocalTemplatesDir

if ($HasLocalTemplates) {
    # Copy tools
    $SrcTools = Join-Path $LocalTemplatesDir "tools"
    if (Test-Path $SrcTools) {
        Copy-Item -Path (Join-Path $SrcTools "*") -Destination $ToolsDir -Force -Recurse
        Write-Host "  ✓ tools/* deployed (skill_router.py, agent_lock.py)." -ForegroundColor Green
    }
    # Copy core/tools
    $SrcCoreTools = Join-Path $LocalTemplatesDir "core\tools"
    if (Test-Path $SrcCoreTools) {
        Copy-Item -Path (Join-Path $SrcCoreTools "*") -Destination $CoreToolsDir -Force -Recurse
        Write-Host "  ✓ core/tools/* deployed." -ForegroundColor Green
    }
    # Copy rules
    $SrcRules = Join-Path $LocalTemplatesDir ".agents\rules"
    if (Test-Path $SrcRules) {
        Copy-Item -Path (Join-Path $SrcRules "*") -Destination $RulesDir -Force -Recurse
        Write-Host "  ✓ .agents/rules/* deployed (godot-harness.md)." -ForegroundColor Green
    }
    # Copy workflows
    $SrcWorkflows = Join-Path $LocalTemplatesDir ".agents\workflows"
    if (Test-Path $SrcWorkflows) {
        Copy-Item -Path (Join-Path $SrcWorkflows "*") -Destination $WorkflowsDir -Force -Recurse
        Write-Host "  ✓ .agents/workflows/* deployed (godot-harness.md)." -ForegroundColor Green
    }
    # Copy game.py
    $SrcGamePy = Join-Path $LocalTemplatesDir "game.py"
    if (Test-Path $SrcGamePy) {
        $DestGamePy = Join-Path $TargetProject "game.py"
        if (-not (Test-Path $DestGamePy)) {
            Copy-Item -Path $SrcGamePy -Destination $DestGamePy -Force
            Write-Host "  ✓ game.py deployed to project root." -ForegroundColor Green
        } else {
            Write-Host "  ✓ game.py already present in project root." -ForegroundColor Green
        }
    }
    # Copy AGENTS.md, AGENTS_HARNESS.md, etc.
    foreach ($doc in @("AGENTS.md", "AGENTS_HARNESS.md", "CLAUDE.md", "GEMINI.md")) {
        $SrcDoc = Join-Path $LocalTemplatesDir $doc
        if (Test-Path $SrcDoc) {
            $DestDoc = Join-Path $TargetProject $doc
            if (-not (Test-Path $DestDoc)) {
                Copy-Item -Path $SrcDoc -Destination $DestDoc -Force
                Write-Host "  ✓ $doc deployed to project root." -ForegroundColor Green
            } else {
                Write-Host "  ✓ $doc already present in project root." -ForegroundColor Green
            }
        }
    }
    # Copy test_smoke.gd
    $SrcSmoke = Join-Path $LocalTemplatesDir "tests\test_smoke.gd"
    if (Test-Path $SrcSmoke) {
        $DestSmoke = Join-Path $TestsDir "test_smoke.gd"
        if (-not (Test-Path $DestSmoke)) {
            Copy-Item -Path $SrcSmoke -Destination $DestSmoke -Force
            Write-Host "  ✓ tests/test_smoke.gd deployed." -ForegroundColor Green
        }
    }
} else {
    Write-Host "  ℹ Running in standalone remote mode. Generating baseline rules..." -ForegroundColor Cyan
}

# Ensure graphify.md rule is created
$GraphifyRulePath = Join-Path $RulesDir "graphify.md"
if (-not (Test-Path $GraphifyRulePath)) {
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
}

# 4. Clone Ponytail (Anti-bloat & YAGNI rules)
Write-Host "`n[4/6] Pulling Ponytail & Prompt Master..." -ForegroundColor Yellow
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

# 5. Clone GD-Agentic-Skills
Write-Host "`n[5/6] Pulling 44 Godot Domain Skills..." -ForegroundColor Yellow
$GdSkillsPath = Join-Path $SkillsDir "gd-agentic-skills"
if (-not (Test-Path $GdSkillsPath)) {
    git clone https://github.com/thedivergentai/GD-Agentic-Skills.git $GdSkillsPath --quiet
    Write-Host "  ✓ GD-Agentic-Skills installed (44 domain skills ready for curation)." -ForegroundColor Green
} else {
    Write-Host "  ✓ GD-Agentic-Skills already present." -ForegroundColor Green
}

# 6. Final verification & status
Write-Host "`n[6/6] Verifying harness readiness..." -ForegroundColor Yellow
$GamePyPath = Join-Path $TargetProject "game.py"
if (Test-Path $GamePyPath) {
    Write-Host "  ✓ game.py is ready. Run 'python game.py info' or 'python game.py route-prompt' to test." -ForegroundColor Green
} else {
    Write-Host "  ℹ Tip: Ensure game.py is at project root." -ForegroundColor DarkYellow
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  ✅ Setup complete! Paste Godot_Dynamic_Harness_Prompt.txt " -ForegroundColor Green
Write-Host "     into your AI agent to curate skills and build rules!   " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
