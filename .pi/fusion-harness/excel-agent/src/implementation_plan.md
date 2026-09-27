# 📋 Excel Agent Tool - Enhanced Architecture & Implementation Plan

## 🎯 Phase 1: Deep Analysis & Architecture Design

### Current Issues with Library-Based Design:
1. **Stateful**: Requires context managers and object lifecycle management
2. **Complex for AI**: Needs understanding of Python classes and methods
3. **Error-prone**: Shared state across operations
4. **Hard to compose**: Cannot easily chain operations from CLI

### New Vision: **CLI-First Tool Architecture**

Instead of importing a library, AI agents call **standalone tools** via:
```bash
uv python excel_add_formula.py --file model.xlsx --sheet Sheet1 --cell B10 --formula "=SUM(B2:B9)"
```

### Why This is Superior for AI Agents:

| Aspect | Library Design | Tool Design ✅ |
|--------|---------------|---------------|
| **Learning Curve** | Must understand OOP, context managers | Simple CLI arguments |
| **State Management** | Complex (open/close, save) | Stateless (one operation = one call) |
| **Error Handling** | Try/except blocks | Exit codes + JSON errors |
| **Composability** | Requires Python script | Shell pipes, JSON processing |
| **Debugging** | Stack traces | Simple command replay |
| **Parallel Execution** | Difficult (locking) | Easy (file-level locking) |

---

## 🏗️ New Architecture Design

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI Agent Layer                            │
│  (Receives tool descriptions, calls via uv python <tool>.py)    │
└────────────────────────┬────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Creation     │  │ Editing      │  │ Validation   │
│ Tools        │  │ Tools        │  │ Tools        │
│              │  │              │  │              │
│ • create_new │  │ • set_value  │  │ • validate   │
│ • from_tmpl  │  │ • add_formula│  │ • repair     │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  excel_agent_core.py │
              │  (Shared Library)    │
              │                      │
              │  • ExcelAgent class  │
              │  • Validators        │
              │  • Styles            │
              │  • Templates         │
              └──────────┬───────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │   openpyxl   │
                  │ LibreOffice  │
                  └──────────────┘
```

### Tool Categories (15 Total Tools):

#### **Category 1: Creation (3 tools)**
1. `excel_create_new.py` - Create blank workbook
2. `excel_create_from_structure.py` - Create from JSON definition
3. `excel_clone_template.py` - Clone with preservation

#### **Category 2: Cell Operations (5 tools)**
4. `excel_set_value.py` - Set single cell value
5. `excel_add_formula.py` - Add validated formula
6. `excel_add_financial_input.py` - Add blue input with comment
7. `excel_add_assumption.py` - Add yellow assumption
8. `excel_get_value.py` - Read cell value/formula

#### **Category 3: Range Operations (2 tools)**
9. `excel_apply_range_formula.py` - Apply formula to range
10. `excel_format_range.py` - Apply formatting to range

#### **Category 4: Sheet Management (2 tools)**
11. `excel_add_sheet.py` - Add new worksheet
12. `excel_export_sheet.py` - Export to CSV/JSON

#### **Category 5: Validation & Quality (2 tools)**
13. `excel_validate_formulas.py` - Validate all formulas
14. `excel_repair_errors.py` - Auto-repair errors

#### **Category 6: Utilities (1 tool)**
15. `excel_get_info.py` - Get workbook metadata

---

## 📝 Detailed Implementation Plan

### **File Structure:**
```
excel_agent_tool/
├── core/
│   ├── excel_agent_core.py      # Shared library (all business logic)
│   └── __init__.py
├── tools/
│   ├── excel_create_new.py
│   ├── excel_create_from_structure.py
│   ├── excel_clone_template.py
│   ├── excel_set_value.py
│   ├── excel_add_formula.py
│   ├── excel_add_financial_input.py
│   ├── excel_add_assumption.py
│   ├── excel_get_value.py
│   ├── excel_apply_range_formula.py
│   ├── excel_format_range.py
│   ├── excel_add_sheet.py
│   ├── excel_export_sheet.py
│   ├── excel_validate_formulas.py
│   ├── excel_repair_errors.py
│   └── excel_get_info.py
├── AGENT_SYSTEM_PROMPT.md       # AI agent instructions
├── TOOLS_REFERENCE.md            # Complete tool documentation
├── README.md                     # Human documentation
├── requirements.txt
└── test_tools.py                 # Integration tests
```

---

## ✅ Implementation Checklist

### **File 1: `core/excel_agent_core.py`** (Consolidated Core Library)
**Purpose:** All business logic from original design, optimized for tool usage

**Checklist:**
- [ ] Import all dependencies (openpyxl, pandas, etc.)
- [ ] Define all exception classes (ExcelAgentError, FormulaError, etc.)
- [ ] Implement ExcelAgent class with all methods
- [ ] Add formula sanitization (security)
- [ ] Add validation engine (LibreOffice + Python fallback)
- [ ] Add template preservation engine
- [ ] Add style constants and helpers
- [ ] Add utility functions (cell refs, coordinates)
- [ ] Add file locking mechanism for concurrent access
- [ ] Add comprehensive docstrings
- [ ] Add type hints throughout
- [ ] Optimize for stateless operation (no instance state leakage)

**Dependencies:**
- openpyxl>=3.1.5
- pandas>=2.0.0 (optional)
- Standard library: json, re, subprocess, pathlib, typing, tempfile

---

### **File 2: `tools/excel_create_new.py`**
**Purpose:** Create new Excel workbook with specified sheets

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent from core
- [ ] Define argument parser with:
  - [ ] --output (required): Output file path
  - [ ] --sheets (required): Comma-separated sheet names
  - [ ] --template (optional): Apply template file formatting
  - [ ] --json: Output JSON response
- [ ] Validate inputs:
  - [ ] Output path writable
  - [ ] Sheet names valid (no : / \ [ ] *)
  - [ ] No duplicate sheet names
- [ ] Execute operation:
  - [ ] Create workbook
  - [ ] Add sheets
  - [ ] Apply template if specified
  - [ ] Save file
- [ ] Output JSON response:
  ```json
  {
    "status": "success",
    "file": "/path/to/output.xlsx",
    "sheets": ["Sheet1", "Sheet2"],
    "file_size_bytes": 5432
  }
  ```
- [ ] Handle errors with exit code 1 and JSON error
- [ ] Add --help with examples
- [ ] Add dry-run mode (--dry-run)

**Example Usage:**
```bash
uv python excel_create_new.py --output financial_model.xlsx --sheets "Assumptions,Income Statement,Balance Sheet,Cash Flow" --json
```

---

### **File 3: `tools/excel_create_from_structure.py`**
**Purpose:** Create workbook from JSON structure definition

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent from core
- [ ] Define argument parser:
  - [ ] --output (required): Output file
  - [ ] --structure (required): JSON file with structure
  - [ ] --structure-string (alternative): Inline JSON string
  - [ ] --validate: Validate after creation
  - [ ] --json: JSON output
- [ ] Validate structure JSON schema:
  ```json
  {
    "sheets": ["Sheet1", "Sheet2"],
    "cells": [
      {"sheet": "Sheet1", "cell": "A1", "value": "Header", "style": "bold"},
      {"sheet": "Sheet1", "cell": "B2", "formula": "=SUM(B3:B10)", "style": "formula"}
    ],
    "inputs": [
      {"sheet": "Assumptions", "cell": "B2", "value": 0.05, "comment": "Growth rate"}
    ],
    "assumptions": [
      {"sheet": "Assumptions", "cell": "B3", "value": 1000000, "description": "Base revenue"}
    ],
    "named_ranges": [
      {"name": "GrowthRate", "range": "Assumptions!B2"}
    ]
  }
  ```
- [ ] Validate all references
- [ ] Create workbook
- [ ] Add all elements in order (sheets → cells → inputs → assumptions → named ranges)
- [ ] Optionally validate formulas
- [ ] Output JSON with statistics:
  ```json
  {
    "status": "success",
    "file": "model.xlsx",
    "sheets_created": 3,
    "formulas_added": 15,
    "inputs_added": 5,
    "assumptions_added": 3,
    "validation_result": {...}
  }
  ```
- [ ] Handle errors gracefully
- [ ] Add comprehensive help text

**Example Usage:**
```bash
uv python excel_create_from_structure.py --output model.xlsx --structure structure.json --validate --json
```

---

### **File 4: `tools/excel_clone_template.py`**
**Purpose:** Clone existing file with template preservation

**Checklist:**
- [ ] Import argparse, json, sys, Path, shutil
- [ ] Import ExcelAgent from core
- [ ] Define arguments:
  - [ ] --source (required): Template file
  - [ ] --output (required): New file
  - [ ] --preserve-values: Keep existing values (default: false)
  - [ ] --preserve-formulas: Keep formulas (default: false)
  - [ ] --preserve-formatting: Keep formatting (default: true)
  - [ ] --json: JSON output
- [ ] Validate source exists
- [ ] Load template with preservation
- [ ] Optionally clear values/formulas
- [ ] Save to new location
- [ ] Output JSON with metadata
- [ ] Add error handling

**Example Usage:**
```bash
uv python excel_clone_template.py --source template.xlsx --output new_model.xlsx --preserve-formatting --json
```

---

### **File 5: `tools/excel_set_value.py`**
**Purpose:** Set a single cell value

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent from core
- [ ] Define arguments:
  - [ ] --file (required): Excel file
  - [ ] --sheet (required): Sheet name
  - [ ] --cell (required): Cell reference (A1)
  - [ ] --value (required): Value to set
  - [ ] --type: Value type (auto, string, number, date)
  - [ ] --style: Named style to apply
  - [ ] --json: JSON output
- [ ] Validate file exists
- [ ] Validate sheet exists
- [ ] Validate cell reference
- [ ] Parse value according to type
- [ ] Set cell value
- [ ] Apply style if specified
- [ ] Save file
- [ ] Output JSON:
  ```json
  {
    "status": "success",
    "file": "model.xlsx",
    "sheet": "Sheet1",
    "cell": "A1",
    "value": "Revenue",
    "type": "string"
  }
  ```
- [ ] Handle errors

**Example Usage:**
```bash
uv python excel_set_value.py --file model.xlsx --sheet "Income Statement" --cell A1 --value "Revenue Forecast" --type string --json
```

---

### **File 6: `tools/excel_add_formula.py`**
**Purpose:** Add validated formula with security checks

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent from core
- [ ] Define arguments:
  - [ ] --file (required): Excel file
  - [ ] --sheet (required): Sheet name
  - [ ] --cell (required): Target cell
  - [ ] --formula (required): Formula (with or without =)
  - [ ] --validate-refs: Validate references (default: true)
  - [ ] --allow-external: Allow external refs (default: false)
  - [ ] --style: Style name (default: formula)
  - [ ] --json: JSON output
- [ ] Validate inputs
- [ ] Sanitize formula (security check)
- [ ] Validate references if enabled
- [ ] Add formula to cell
- [ ] Save file
- [ ] Output JSON with formula details
- [ ] Handle security errors separately (exit code 2)
- [ ] Add comprehensive help with security warnings

**Example Usage:**
```bash
uv python excel_add_formula.py --file model.xlsx --sheet "Income Statement" --cell B10 --formula "=SUM(B2:B9)" --json
```

---

### **File 7: `tools/excel_add_financial_input.py`**
**Purpose:** Add blue financial input with source comment

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent from core
- [ ] Define arguments:
  - [ ] --file (required): Excel file
  - [ ] --sheet (required): Sheet name
  - [ ] --cell (required): Cell reference
  - [ ] --value (required): Numeric value
  - [ ] --comment (optional): Source attribution
  - [ ] --format: Number format (currency, percent, number)
  - [ ] --json: JSON output
- [ ] Validate numeric value
- [ ] Add cell with blue style
- [ ] Add comment if provided
- [ ] Apply number format
- [ ] Save file
- [ ] Output JSON

**Example Usage:**
```bash
uv python excel_add_financial_input.py --file model.xlsx --sheet Assumptions --cell B2 --value 0.15 --comment "Source: Company 10-K, Page 45" --format percent --json
```

---

### **File 8: `tools/excel_add_assumption.py`**
**Purpose:** Add yellow-highlighted assumption

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent from core
- [ ] Define arguments:
  - [ ] --file (required): Excel file
  - [ ] --sheet (required): Sheet name
  - [ ] --cell (required): Cell reference
  - [ ] --value (required): Assumption value
  - [ ] --description (required): What this assumes
  - [ ] --format: Number format
  - [ ] --json: JSON output
- [ ] Validate inputs
- [ ] Add cell with yellow style
- [ ] Add description as comment
- [ ] Apply formatting
- [ ] Save file
- [ ] Output JSON

**Example Usage:**
```bash
uv python excel_add_assumption.py --file model.xlsx --sheet Assumptions --cell B3 --value 1000000 --description "FY2024 baseline revenue" --format currency --json
```

---

### **File 9: `tools/excel_get_value.py`**
**Purpose:** Read cell value or formula

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent from core
- [ ] Define arguments:
  - [ ] --file (required): Excel file
  - [ ] --sheet (required): Sheet name
  - [ ] --cell (required): Cell reference
  - [ ] --get-formula: Return formula instead of value
  - [ ] --get-both: Return both value and formula
  - [ ] --json: JSON output (default: true for this tool)
- [ ] Validate inputs
- [ ] Open file (read-only)
- [ ] Get cell value/formula
- [ ] Output JSON:
  ```json
  {
    "status": "success",
    "file": "model.xlsx",
    "sheet": "Sheet1",
    "cell": "B10",
    "value": 150000,
    "formula": "=SUM(B2:B9)",
    "data_type": "formula",
    "number_format": "$#,##0"
  }
  ```
- [ ] Handle empty cells gracefully
- [ ] No file modification (read-only)

**Example Usage:**
```bash
uv python excel_get_value.py --file model.xlsx --sheet "Income Statement" --cell B10 --get-both
```

---

### **File 10: `tools/excel_apply_range_formula.py`**
**Purpose:** Apply formula to entire range

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent from core
- [ ] Define arguments:
  - [ ] --file (required): Excel file
  - [ ] --sheet (required): Sheet name
  - [ ] --range (required): Range (e.g., B2:B10)
  - [ ] --formula (required): Formula template (use {cell} as placeholder)
  - [ ] --base-formula: Alternative - auto-adjust from base cell
  - [ ] --json: JSON output
- [ ] Validate range format
- [ ] Parse start and end cells
- [ ] Generate formula for each cell
- [ ] Apply formulas
- [ ] Save file
- [ ] Output JSON with cells modified:
  ```json
  {
    "status": "success",
    "cells_modified": 9,
    "range": "B2:B10",
    "sample_formulas": {
      "B2": "=A2*1.15",
      "B10": "=A10*1.15"
    }
  }
  ```

**Example Usage:**
```bash
# Growth formula: each row multiplies by growth rate
uv python excel_apply_range_formula.py --file model.xlsx --sheet "Forecast" --range B2:B10 --formula "=A{row}*(1+$C$1)" --json
```

---

### **File 11: `tools/excel_format_range.py`**
**Purpose:** Apply number formatting to range

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent from core
- [ ] Define arguments:
  - [ ] --file (required): Excel file
  - [ ] --sheet (required): Sheet name
  - [ ] --range (required): Range to format
  - [ ] --format (required): Format type (currency, percent, accounting, number, date)
  - [ ] --custom-format: Custom Excel format string
  - [ ] --decimals: Decimal places (default: 2)
  - [ ] --json: JSON output
- [ ] Validate inputs
- [ ] Map format type to Excel format string
- [ ] Apply to all cells in range
- [ ] Save file
- [ ] Output JSON

**Example Usage:**
```bash
uv python excel_format_range.py --file model.xlsx --sheet "Income Statement" --range C2:H20 --format currency --decimals 0 --json
```

---

### **File 12: `tools/excel_add_sheet.py`**
**Purpose:** Add new worksheet

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent from core
- [ ] Define arguments:
  - [ ] --file (required): Excel file
  - [ ] --sheet (required): New sheet name
  - [ ] --index: Position (0-based, default: end)
  - [ ] --copy-from: Copy existing sheet
  - [ ] --json: JSON output
- [ ] Validate sheet name
- [ ] Check for duplicates
- [ ] Add sheet
- [ ] Optionally copy content
- [ ] Save file
- [ ] Output JSON

**Example Usage:**
```bash
uv python excel_add_sheet.py --file model.xlsx --sheet "Scenario Analysis" --index 2 --json
```

---

### **File 13: `tools/excel_export_sheet.py`**
**Purpose:** Export sheet to CSV or JSON

**Checklist:**
- [ ] Import argparse, json, csv, sys, Path
- [ ] Import ExcelAgent from core
- [ ] Define arguments:
  - [ ] --file (required): Excel file
  - [ ] --sheet (required): Sheet name
  - [ ] --output (required): Output file
  - [ ] --format: Output format (csv, json, auto from extension)
  - [ ] --range: Optional range to export
  - [ ] --include-formulas: Export formulas instead of values
  - [ ] --json: JSON response
- [ ] Validate inputs
- [ ] Read sheet data
- [ ] Convert to target format
- [ ] Write output file
- [ ] Output JSON with statistics

**Example Usage:**
```bash
uv python excel_export_sheet.py --file model.xlsx --sheet "Income Statement" --output forecast.csv --format csv --json
```

---

### **File 14: `tools/excel_validate_formulas.py`**
**Purpose:** Validate all formulas in workbook

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent and validator from core
- [ ] Define arguments:
  - [ ] --file (required): Excel file
  - [ ] --timeout: Validation timeout (default: 30s)
  - [ ] --method: Validation method (auto, libreoffice, python)
  - [ ] --detailed: Include detailed error locations
  - [ ] --json: JSON output (default: true)
- [ ] Run validation
- [ ] Parse validation report
- [ ] Output comprehensive JSON:
  ```json
  {
    "status": "errors_found",
    "total_formulas": 156,
    "total_errors": 3,
    "validation_method": "libreoffice",
    "errors": {
      "#DIV/0!": {
        "count": 2,
        "locations": ["Sheet1!B5", "Sheet1!C10"]
      },
      "#REF!": {
        "count": 1,
        "locations": ["Sheet2!A1"]
      }
    },
    "summary": "3 errors found in 156 formulas (1.9% error rate)"
  }
  ```
- [ ] Exit code 0 if no errors, 1 if errors found
- [ ] Handle LibreOffice unavailable gracefully

**Example Usage:**
```bash
uv python excel_validate_formulas.py --file model.xlsx --method auto --detailed --json
```

---

### **File 15: `tools/excel_repair_errors.py`**
**Purpose:** Automatically repair formula errors

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent and repair functions from core
- [ ] Define arguments:
  - [ ] --file (required): Excel file
  - [ ] --validate-first: Run validation before repair (default: true)
  - [ ] --backup: Create backup before repair (default: true)
  - [ ] --error-types: Comma-separated errors to repair (default: all)
  - [ ] --dry-run: Show what would be repaired
  - [ ] --json: JSON output
- [ ] Optionally validate first
- [ ] Create backup if enabled
- [ ] Attempt repairs for specified error types
- [ ] Re-validate after repair
- [ ] Output JSON:
  ```json
  {
    "status": "success",
    "repairs_attempted": 3,
    "repairs_successful": 2,
    "repairs_failed": 1,
    "remaining_errors": 1,
    "backup_file": "model_backup_20240115_143022.xlsx",
    "details": {
      "#DIV/0!": {
        "attempted": 2,
        "successful": 2,
        "method": "IFERROR wrapper"
      },
      "#REF!": {
        "attempted": 1,
        "successful": 0,
        "method": "comment added"
      }
    }
  }
  ```
- [ ] Exit code 0 if all repaired, 1 if some remain

**Example Usage:**
```bash
uv python excel_repair_errors.py --file model.xlsx --validate-first --backup --json
```

---

### **File 16: `tools/excel_get_info.py`**
**Purpose:** Get workbook metadata and statistics

**Checklist:**
- [ ] Import argparse, json, sys, Path
- [ ] Import ExcelAgent from core
- [ ] Define arguments:
  - [ ] --file (required): Excel file
  - [ ] --detailed: Include detailed statistics
  - [ ] --include-sheets: Include per-sheet info
  - [ ] --json: JSON output (default: true)
- [ ] Open file (read-only)
- [ ] Collect metadata
- [ ] Output comprehensive JSON:
  ```json
  {
    "status": "success",
    "file": "model.xlsx",
    "file_size_bytes": 45678,
    "file_size_human": "44.6 KB",
    "created": "2024-01-15T10:30:00",
    "modified": "2024-01-15T14:25:00",
    "sheets": ["Assumptions", "Income Statement", "Balance Sheet"],
    "sheet_count": 3,
    "total_formulas": 156,
    "total_cells_with_data": 342,
    "named_ranges": ["GrowthRate", "BaseRevenue"],
    "has_external_links": false,
    "sheet_details": {
      "Income Statement": {
        "used_range": "A1:H50",
        "formulas": 45,
        "data_cells": 120
      }
    }
  }
  ```
- [ ] No file modification

**Example Usage:**
```bash
uv python excel_get_info.py --file model.xlsx --detailed --include-sheets --json
```

---

### **File 17: `AGENT_SYSTEM_PROMPT.md`**
**Purpose:** Complete system prompt for AI agents

**Checklist:**
- [ ] Introduction to Excel tools
- [ ] Design philosophy (stateless, composable)
- [ ] Complete tool catalog with:
  - [ ] Tool name
  - [ ] Purpose (1 sentence)
  - [ ] Required arguments
  - [ ] Optional arguments
  - [ ] Example usage
  - [ ] Expected output format
  - [ ] Common error scenarios
- [ ] Workflow patterns:
  - [ ] Creating new models
  - [ ] Editing existing files
  - [ ] Batch operations
  - [ ] Validation workflows
- [ ] Best practices:
  - [ ] Always use --json flag
  - [ ] Parse JSON responses
  - [ ] Check exit codes
  - [ ] Handle errors gracefully
  - [ ] Use validation before distribution
- [ ] Security considerations:
  - [ ] Formula injection risks
  - [ ] External reference warnings
  - [ ] File path validation
- [ ] Complete examples:
  - [ ] Build financial model from scratch
  - [ ] Update quarterly forecast
  - [ ] Validate and repair errors
  - [ ] Export to multiple formats

---

### **File 18: `TOOLS_REFERENCE.md`**
**Purpose:** Complete technical reference for all tools

**Checklist:**
- [ ] Alphabetical listing of all tools
- [ ] For each tool:
  - [ ] Full description
  - [ ] All arguments with types and defaults
  - [ ] Return value schema (JSON)
  - [ ] Exit codes and meanings
  - [ ] Error scenarios
  - [ ] Multiple usage examples
  - [ ] Related tools
- [ ] Common patterns section
- [ ] Troubleshooting guide
- [ ] Performance considerations
- [ ] Version compatibility

---

### **File 19: `README.md`**
**Purpose:** Human-readable guide

**Checklist:**
- [ ] Project overview
- [ ] Installation instructions (uv, pip)
- [ ] Quick start examples
- [ ] Architecture overview
- [ ] Tool categories
- [ ] Common workflows
- [ ] Integration examples (shell scripts, Python)
- [ ] Testing instructions
- [ ] Contributing guide
- [ ] License
- [ ] Support/contact

---

### **File 20: `test_tools.py`**
**Purpose:** Integration tests for all tools

**Checklist:**
- [ ] Test each tool independently
- [ ] Test tool chaining
- [ ] Test error handling
- [ ] Test JSON output parsing
- [ ] Test exit codes
- [ ] Test file locking
- [ ] Test concurrent operations
- [ ] Test large files
- [ ] Test Unicode handling
- [ ] Test edge cases
- [ ] Use pytest framework
- [ ] Use temporary directories
- [ ] Mock LibreOffice if unavailable
- [ ] Generate coverage report

---

## 🔍 Pre-Execution Validation

### Architecture Review:
✅ **Stateless Design**: Each tool call is independent  
✅ **JSON-First**: All outputs are machine-parsable  
✅ **Error Handling**: Exit codes + detailed error messages  
✅ **Security**: Formula sanitization, path validation  
✅ **Composability**: Tools can be chained via shell or Python  
✅ **AI-Friendly**: Simple CLI interface, clear documentation  

### Completeness Check:
✅ **Core Library**: 1 file with all business logic  
✅ **Tool Scripts**: 15 complete, standalone tools  
✅ **Documentation**: 3 files (system prompt, reference, README)  
✅ **Tests**: 1 comprehensive test file  
✅ **Total**: 20 files, all with complete implementations  

### Dependency Validation:
✅ **Required**: openpyxl, argparse, json, pathlib (all available)  
✅ **Optional**: pandas (graceful degradation)  
✅ **External**: LibreOffice (fallback validator if unavailable)  

### Security Review:
✅ **Formula Injection**: Sanitization in core library  
✅ **Path Traversal**: Path validation in all file operations  
✅ **DoS Prevention**: Formula complexity limits  
✅ **File Locking**: Prevents concurrent write conflicts  

---

## 🚀 Execution Order

I will now create all 20 files in this order:

1. **`core/excel_agent_core.py`** (Foundation - everything else depends on this)
2. **Tool scripts** (15 files, alphabetically)
3. **`AGENT_SYSTEM_PROMPT.md`** (AI agent instructions)
4. **`TOOLS_REFERENCE.md`** (Technical reference)
5. **`README.md`** (Human guide)
6. **`test_tools.py`** (Integration tests)

Each file will be **complete** with:
- No placeholder comments
- Full error handling
- Comprehensive docstrings
- Type hints
- Security validations
- JSON output formatting
- Exit code management

---

**Proceeding to implementation in next response...**
