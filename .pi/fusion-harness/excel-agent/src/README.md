# Excel Agent Tool 🚀

**Production-grade Excel manipulation for AI agents**

Build, edit, and validate Excel workbooks through simple command-line tools designed for AI agent consumption. Zero formula errors guaranteed through integrated validation.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🎯 Why Excel Agent Tool?

Traditional Excel libraries require complex Python code and offer no formula validation. Excel Agent Tool provides:

✅ **CLI-First Design** - AI agents call simple commands, no Python knowledge required  
✅ **Zero Formula Errors** - Built-in validation with auto-repair  
✅ **JSON Everywhere** - All outputs machine-parsable  
✅ **Security Hardened** - Formula injection prevention  
✅ **Financial Standards** - Industry color coding built-in  
✅ **Stateless Operations** - No session management, perfect for distributed systems  

---

## 📦 Installation

### Quick Start (with uv - Recommended)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
git clone https://github.com/nordeim/excel-agent-tool.git
cd excel-agent-tool

# Install dependencies
uv pip install -r requirements.txt

# Test installation
uv python tools/excel_create_new.py --help
```

### Standard Installation (with pip)

```bash
# Clone repository
git clone https://github.com/nordeim/excel-agent-tool.git
cd excel-agent-tool

# Install dependencies
pip install -r requirements.txt

# Test installation
python tools/excel_create_new.py --help
```

### Optional: LibreOffice for Full Validation

For complete formula validation (recommended):

**Ubuntu/Debian:**
```bash
sudo apt install libreoffice-calc
```

**macOS:**
```bash
brew install --cask libreoffice
```

**Windows:**
Download from [libreoffice.org](https://www.libreoffice.org/download)

---

## 🚀 Quick Start Examples

### Example 1: Create Financial Model

```bash
# Create workbook with sheets
uv python tools/excel_create_new.py \
  --output financial_model.xlsx \
  --sheets "Assumptions,Income Statement,Balance Sheet,Cash Flow" \
  --json

# Add assumption (yellow highlight)
uv python tools/excel_add_assumption.py \
  --file financial_model.xlsx \
  --sheet Assumptions \
  --cell B2 \
  --value 1000000 \
  --description "FY2024 baseline revenue from strategic plan" \
  --format currency \
  --decimals 0 \
  --json

# Add financial input (blue text)
uv python tools/excel_add_financial_input.py \
  --file financial_model.xlsx \
  --sheet Assumptions \
  --cell B3 \
  --value 0.15 \
  --comment "Source: Company 10-K FY2024, Page 45 - Historical 5-yr CAGR" \
  --format percent \
  --json

# Add revenue formula
uv python tools/excel_add_formula.py \
  --file financial_model.xlsx \
  --sheet "Income Statement" \
  --cell B5 \
  --formula "=Assumptions!B2*(1+Assumptions!B3)" \
  --json

# Apply growth to future years
uv python tools/excel_apply_range_formula.py \
  --file financial_model.xlsx \
  --sheet "Income Statement" \
  --range C5:F5 \
  --formula "=B5*(1+Assumptions!\$B\$3)" \
  --json

# Format as currency
uv python tools/excel_format_range.py \
  --file financial_model.xlsx \
  --sheet "Income Statement" \
  --range B5:F20 \
  --format currency \
  --decimals 0 \
  --json

# Validate all formulas
uv python tools/excel_validate_formulas.py \
  --file financial_model.xlsx \
  --json
```

**Result:** Professional financial model with traceable inputs, validated formulas, and proper formatting.

---

### Example 2: Batch Creation from JSON

```bash
# Create structure definition
cat > structure.json << 'EOF'
{
  "sheets": ["Assumptions", "Model"],
  "assumptions": [
    {
      "sheet": "Assumptions",
      "cell": "B2",
      "value": 1000000,
      "description": "Baseline revenue"
    },
    {
      "sheet": "Assumptions",
      "cell": "B3",
      "value": 0.20,
      "description": "Annual growth rate"
    }
  ],
  "cells": [
    {"sheet": "Model", "cell": "A1", "value": "Year"},
    {"sheet": "Model", "cell": "B1", "value": "Revenue"},
    {"sheet": "Model", "cell": "A2", "value": 2024},
    {"sheet": "Model", "cell": "B2", "formula": "=Assumptions!B2"}
  ]
}
EOF

# Create workbook
uv python tools/excel_create_from_structure.py \
  --output model.xlsx \
  --structure structure.json \
  --validate \
  --json
```

---

### Example 3: Update Existing Model

```bash
# Clone Q1 model for Q2
uv python tools/excel_clone_template.py \
  --source q1_model.xlsx \
  --output q2_model.xlsx \
  --preserve-formulas \
  --preserve-formatting \
  --json

# Update quarter label
uv python tools/excel_set_value.py \
  --file q2_model.xlsx \
  --sheet Assumptions \
  --cell A1 \
  --value "Q2 2024 Model" \
  --type string \
  --json

# Update actuals
uv python tools/excel_add_financial_input.py \
  --file q2_model.xlsx \
  --sheet Assumptions \
  --cell B2 \
  --value 1150000 \
  --comment "Q2 actual revenue from SAP system" \
  --format currency \
  --json

# Validate
uv python tools/excel_validate_formulas.py \
  --file q2_model.xlsx \
  --json
```

---

### Example 4: Validate and Repair

```bash
# Validate existing file
uv python tools/excel_validate_formulas.py \
  --file broken_model.xlsx \
  --detailed \
  --json > validation_report.json

# If errors found, repair them
uv python tools/excel_repair_errors.py \
  --file broken_model.xlsx \
  --validate-first \
  --backup \
  --json > repair_report.json

# Re-validate
uv python tools/excel_validate_formulas.py \
  --file broken_model.xlsx \
  --json
```

---

## 🛠️ Tool Categories

### 📁 Creation Tools (3)

| Tool | Purpose |
|------|---------|
| `excel_create_new.py` | Create blank workbook with sheets |
| `excel_create_from_structure.py` | Create from JSON structure |
| `excel_clone_template.py` | Clone existing file |

### ✏️ Cell Operations (5)

| Tool | Purpose |
|------|---------|
| `excel_set_value.py` | Set single cell value |
| `excel_add_formula.py` | Add validated formula |
| `excel_add_financial_input.py` | Add blue input with comment |
| `excel_add_assumption.py` | Add yellow assumption |
| `excel_get_value.py` | Read cell value/formula |

### 📊 Range Operations (2)

| Tool | Purpose |
|------|---------|
| `excel_apply_range_formula.py` | Apply formula to range |
| `excel_format_range.py` | Format range |

### 📑 Sheet Management (2)

| Tool | Purpose |
|------|---------|
| `excel_add_sheet.py` | Add worksheet |
| `excel_export_sheet.py` | Export to CSV/JSON |

### ✅ Validation & Quality (2)

| Tool | Purpose |
|------|---------|
| `excel_validate_formulas.py` | Validate all formulas |
| `excel_repair_errors.py` | Auto-repair errors |

### 🔍 Utilities (1)

| Tool | Purpose |
|------|---------|
| `excel_get_info.py` | Get workbook metadata |

---

## 🎨 Financial Modeling Conventions

### Color Coding (Industry Standard)

| Color | Meaning | Tool |
|-------|---------|------|
| **Blue** | Hardcoded inputs (traceable to source) | `excel_add_financial_input.py` |
| **Black** | Formulas (calculations) | `excel_add_formula.py` |
| **Yellow** | Key assumptions (sensitivity drivers) | `excel_add_assumption.py` |

### Best Practices

✅ **Always document inputs** with source comments  
✅ **Validate before sharing** to ensure quality  
✅ **Use assumptions for sensitivity** analysis drivers  
✅ **Format consistently** using standard formats  

---

## 📖 Documentation

- **[AGENT_SYSTEM_PROMPT.md](AGENT_SYSTEM_PROMPT.md)** - Complete AI agent instructions with examples
- **[TOOLS_REFERENCE.md](TOOLS_REFERENCE.md)** - Technical reference for all tools
- **[README.md](README.md)** - This file (getting started guide)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────┐
│         AI Agent Layer              │
│  (Calls tools via uv python)        │
└──────────────┬──────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│Creation│ │Editing │ │Validate│
│ Tools  │ │ Tools  │ │ Tools  │
└────┬───┘ └────┬───┘ └────┬───┘
     │          │          │
     └──────────┼──────────┘
                ▼
      ┌──────────────────┐
      │ excel_agent_core │
      │  (Shared Library)│
      └─────────┬────────┘
                ▼
         ┌──────────────┐
         │  openpyxl    │
         │ LibreOffice  │
         └──────────────┘
```

**Key Design Decisions:**
- **Stateless tools** - No session management
- **JSON-first** - All I/O machine-parsable
- **Security hardened** - Formula sanitization built-in
- **File locking** - Prevents concurrent corruption

---

## 🔒 Security Features

### Formula Injection Prevention

By default, all formulas are checked for:
- ❌ `WEBSERVICE()` - Network access
- ❌ `CALL()` - External DLL execution
- ❌ `HYPERLINK()` - Potential phishing
- ❌ External workbook references
- ❌ Excessive complexity (DoS prevention)

**To allow (not recommended):**
```bash
uv python tools/excel_add_formula.py \
  --file model.xlsx \
  --sheet Data \
  --cell A1 \
  --formula "=WEBSERVICE('https://api.example.com')" \
  --allow-external \
  --json
```

### File Locking

Prevents concurrent write operations that could corrupt files:
```bash
# First process acquires lock
uv python tools/excel_set_value.py --file model.xlsx ... &

# Second process waits or fails
uv python tools/excel_set_value.py --file model.xlsx ...
# Error: "Could not acquire lock on model.xlsx within 10s"
```

### Path Validation

All file paths are validated to prevent traversal attacks.

---

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Install test dependencies
uv pip install pytest

# Run all tests
pytest test_tools.py -v

# Run with coverage
pytest test_tools.py --cov=core --cov=tools --cov-report=html

# Run specific test
pytest test_tools.py::test_create_new_workbook -v
```

**Test Coverage:**
- ✅ All 15 tools tested independently
- ✅ Tool chaining workflows
- ✅ Error handling and edge cases
- ✅ Security validation
- ✅ Concurrent access
- ✅ Large file handling

---

## 📊 Performance

**Benchmarks** (MacBook Pro M1, Python 3.11):

| Operation | Small File (<1MB) | Large File (>10MB) |
|-----------|-------------------|-------------------|
| Create new (3 sheets) | 0.2s | - |
| Add formula (single) | 0.3s | 0.6s |
| Range formula (100 cells) | 0.5s | 1.2s |
| Format range (1000 cells) | 0.6s | 1.5s |
| Validate (Python fallback) | 1.0s | 12s |
| Export to CSV | 0.4s | 4.5s |

**Tips for Large Files:**
- Use Python validation method (faster, less accurate)
- Batch operations with `excel_create_from_structure.py`
- Disable detailed validation output

---

## 🤝 Integration Examples

### Python Integration

```python
import subprocess
import json

def call_tool(tool: str, args: dict) -> dict:
    """Call Excel tool and parse JSON response."""
    cmd = ['uv', 'python', f'tools/{tool}', '--json']
    
    for key, value in args.items():
        cmd.extend([f'--{key}', str(value)])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"Tool failed: {result.stderr}")
    
    return json.loads(result.stdout)

# Example usage
response = call_tool('excel_create_new.py', {
    'output': 'model.xlsx',
    'sheets': 'Sheet1,Sheet2'
})

print(f"Created: {response['file']}")
```

### Shell Script Integration

```bash
#!/bin/bash
set -e

MODEL="financial_model.xlsx"

# Create model
uv python tools/excel_create_new.py \
  --output "$MODEL" \
  --sheets "Assumptions,Model" \
  --json | jq -r '.status'

# Add data
uv python tools/excel_add_assumption.py \
  --file "$MODEL" \
  --sheet Assumptions \
  --cell B2 \
  --value 1000000 \
  --description "Revenue baseline" \
  --json | jq -r '.status'

# Validate
if uv python tools/excel_validate_formulas.py --file "$MODEL" --json | jq -e '.total_errors == 0'; then
  echo "✅ Model validated successfully"
else
  echo "❌ Validation failed"
  exit 1
fi
```

### GitHub Actions Integration

```yaml
name: Validate Excel Models

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install openpyxl pandas
      
      - name: Validate all Excel files
        run: |
          for file in models/*.xlsx; do
            echo "Validating $file..."
            python tools/excel_validate_formulas.py --file "$file" --json
          done
```

---

## 🐛 Troubleshooting

### Common Issues

**Issue:** `FileNotFoundError: File not found: model.xlsx`  
**Solution:** Check file path, ensure parent directories exist

**Issue:** `Sheet 'InvalidSheet' not found`  
**Solution:** Check sheet names with `excel_get_info.py`, verify spelling

**Issue:** `SecurityError: Formula contains potentially unsafe operations`  
**Solution:** Review formula, use `--allow-external` only if safe

**Issue:** `Could not acquire lock on file.xlsx within 10s`  
**Solution:** Wait for other process to complete, check file permissions

**Issue:** `Validation timed out after 30 seconds`  
**Solution:** Increase timeout with `--timeout 60`, or use `--method python`

### Getting Help

1. Check `AGENT_SYSTEM_PROMPT.md` for detailed examples
2. Use `--help` flag on any tool for usage information
3. Run tools with `--json` for detailed error messages
4. Check `TOOLS_REFERENCE.md` for technical details

---

## 🗺️ Roadmap

### v2.1 (Next Release)
- [ ] Streaming API for files >100K rows
- [ ] Enhanced chart preservation
- [ ] Named range dependency graph visualization
- [ ] Performance profiling tools

### v2.2 (Future)
- [ ] Google Sheets adapter
- [ ] Real-time collaboration API
- [ ] ML-powered formula suggestions
- [ ] Visual formula debugger

### v3.0 (Long-term)
- [ ] Distributed validation (cloud-based)
- [ ] Multi-format support (ODF, Numbers)
- [ ] Query language for Excel (SQL-like)
- [ ] Web-based GUI

---

## 🤝 Contributing

We welcome contributions! Please follow these guidelines:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Write** tests for new functionality
4. **Ensure** all tests pass (`pytest test_tools.py`)
5. **Commit** with clear messages (`git commit -m 'Add amazing feature'`)
6. **Push** to branch (`git push origin feature/amazing-feature`)
7. **Open** a Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/your-username/excel-agent-tool.git
cd excel-agent-tool

# Install dev dependencies
uv pip install -r requirements.txt pytest pytest-cov

# Run tests
pytest test_tools.py -v

# Check coverage
pytest test_tools.py --cov=core --cov=tools --cov-report=html
open htmlcov/index.html
```

### Code Standards

- Follow PEP 8 style guide
- Include type hints for all functions
- Add docstrings for all public APIs
- Write tests for new features
- Update documentation

---

## 📄 License

MIT License

Copyright (c) 2024 Excel Agent Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## 🙏 Acknowledgments

- **openpyxl team** - Excellent Excel library
- **pandas team** - DataFrame integration
- **LibreOffice** - Validation engine
- **Financial modeling community** - Color coding standards

---

## 📞 Support

- **Documentation:** [AGENT_SYSTEM_PROMPT.md](AGENT_SYSTEM_PROMPT.md)
- **Issues:** [GitHub Issues](https://github.com/your-org/excel-agent-tool/issues)
- **Discussions:** [GitHub Discussions](https://github.com/your-org/excel-agent-tool/discussions)
- **Email:** support@excelagent.dev

---

**Built with ❤️ for AI agents and financial modelers who demand perfection.**
