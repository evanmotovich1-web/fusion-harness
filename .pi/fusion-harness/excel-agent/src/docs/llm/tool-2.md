# 🚀 Continuing Implementation - Tool Scripts (Files 2-16)

---

## **File 2/20: `tools/excel_create_new.py`**

```python
#!/usr/bin/env python3
"""
Excel Create New Tool
Create a new Excel workbook with specified sheets

Usage:
    uv python excel_create_new.py --output model.xlsx --sheets "Sheet1,Sheet2,Sheet3" --json

Exit Codes:
    0: Success
    1: Error occurred
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path for core import
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.excel_agent_core import (
    ExcelAgent, ExcelAgentError, is_valid_sheet_name, sanitize_sheet_name
)


def create_new_workbook(
    output: Path,
    sheets: list,
    template: Path = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """Create new workbook with specified sheets."""
    
    # Validate sheet names
    validated_sheets = []
    warnings = []
    
    for sheet_name in sheets:
        if not is_valid_sheet_name(sheet_name):
            sanitized = sanitize_sheet_name(sheet_name)
            warnings.append(f"Sheet name '{sheet_name}' invalid, using '{sanitized}'")
            sheet_name = sanitized
        validated_sheets.append(sheet_name)
    
    # Check for duplicates
    if len(validated_sheets) != len(set(validated_sheets)):
        raise ValueError("Duplicate sheet names detected")
    
    if dry_run:
        return {
            "status": "dry_run",
            "output": str(output),
            "sheets": validated_sheets,
            "warnings": warnings
        }
    
    # Create workbook
    with ExcelAgent() as agent:
        agent.create_new(validated_sheets)
        
        # Apply template if specified
        if template:
            # Template application would be done here
            # For now, we just note it
            warnings.append("Template application not yet implemented")
        
        agent.save(output)
    
    # Get file info
    file_size = output.stat().st_size if output.exists() else 0
    
    return {
        "status": "success",
        "file": str(output),
        "sheets": validated_sheets,
        "sheet_count": len(validated_sheets),
        "file_size_bytes": file_size,
        "warnings": warnings
    }


def main():
    parser = argparse.ArgumentParser(
        description="Create new Excel workbook with specified sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create workbook with 3 sheets
  uv python excel_create_new.py --output model.xlsx --sheets "Assumptions,Income Statement,Balance Sheet" --json
  
  # Create with single sheet
  uv python excel_create_new.py --output data.xlsx --sheets "Data" --json
  
  # Dry run to validate names
  uv python excel_create_new.py --output test.xlsx --sheets "Sheet1,Sheet2" --dry-run --json
        """
    )
    
    parser.add_argument(
        '--output',
        required=True,
        type=Path,
        help='Output Excel file path'
    )
    
    parser.add_argument(
        '--sheets',
        required=True,
        help='Comma-separated list of sheet names'
    )
    
    parser.add_argument(
        '--template',
        type=Path,
        help='Optional template file to copy formatting from'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate inputs without creating file'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON response'
    )
    
    args = parser.parse_args()
    
    try:
        # Parse sheets
        sheets = [s.strip() for s in args.sheets.split(',') if s.strip()]
        
        if not sheets:
            raise ValueError("At least one sheet name required")
        
        # Validate template if specified
        if args.template and not args.template.exists():
            raise FileNotFoundError(f"Template file not found: {args.template}")
        
        # Create workbook
        result = create_new_workbook(
            output=args.output,
            sheets=sheets,
            template=args.template,
            dry_run=args.dry_run
        )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Created workbook: {result['file']}")
            print(f"   Sheets: {', '.join(result['sheets'])}")
            if result.get('warnings'):
                for warning in result['warnings']:
                    print(f"   ⚠️  {warning}")
        
        sys.exit(0)
        
    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }
        
        if args.json:
            print(json.dumps(error_result, indent=2))
        else:
            print(f"❌ Error: {e}", file=sys.stderr)
        
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## **File 3/20: `tools/excel_create_from_structure.py`**

```python
#!/usr/bin/env python3
"""
Excel Create From Structure Tool
Create Excel workbook from JSON structure definition

Usage:
    uv python excel_create_from_structure.py --output model.xlsx --structure structure.json --validate --json

Exit Codes:
    0: Success
    1: Error occurred
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.excel_agent_core import (
    create_workbook_from_structure, ExcelAgentError, validate_workbook
)


def validate_structure(structure: Dict[str, Any]) -> None:
    """Validate structure dictionary schema."""
    
    # Check required keys
    if "sheets" not in structure or not structure["sheets"]:
        raise ValueError("Structure must contain 'sheets' key with at least one sheet")
    
    if not isinstance(structure["sheets"], list):
        raise ValueError("'sheets' must be a list")
    
    # Validate cells
    for cell_def in structure.get("cells", []):
        if "sheet" not in cell_def or "cell" not in cell_def:
            raise ValueError("Each cell definition must have 'sheet' and 'cell' keys")
        
        if "value" not in cell_def and "formula" not in cell_def:
            raise ValueError("Each cell definition must have either 'value' or 'formula'")
    
    # Validate inputs
    for input_def in structure.get("inputs", []):
        required = ["sheet", "cell", "value"]
        if not all(k in input_def for k in required):
            raise ValueError(f"Input definition must have: {required}")
    
    # Validate assumptions
    for assumption_def in structure.get("assumptions", []):
        required = ["sheet", "cell", "value", "description"]
        if not all(k in assumption_def for k in required):
            raise ValueError(f"Assumption definition must have: {required}")


def main():
    parser = argparse.ArgumentParser(
        description="Create Excel workbook from JSON structure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Structure JSON Format:
{
  "sheets": ["Sheet1", "Sheet2"],
  "cells": [
    {"sheet": "Sheet1", "cell": "A1", "value": "Header"},
    {"sheet": "Sheet1", "cell": "B2", "formula": "=SUM(B3:B10)"}
  ],
  "inputs": [
    {"sheet": "Assumptions", "cell": "B2", "value": 0.05, "comment": "Growth rate", "number_format": "0.0%"}
  ],
  "assumptions": [
    {"sheet": "Assumptions", "cell": "B3", "value": 1000000, "description": "Base revenue"}
  ]
}

Examples:
  # Create from file
  uv python excel_create_from_structure.py --output model.xlsx --structure structure.json --json
  
  # Create from inline JSON
  uv python excel_create_from_structure.py --output model.xlsx --structure-string '{"sheets":["Data"]}' --json
  
  # Create and validate
  uv python excel_create_from_structure.py --output model.xlsx --structure structure.json --validate --json
        """
    )
    
    parser.add_argument(
        '--output',
        required=True,
        type=Path,
        help='Output Excel file path'
    )
    
    parser.add_argument(
        '--structure',
        type=Path,
        help='JSON file with structure definition'
    )
    
    parser.add_argument(
        '--structure-string',
        help='Inline JSON structure string'
    )
    
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate formulas after creation'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON response'
    )
    
    args = parser.parse_args()
    
    try:
        # Load structure
        if args.structure:
            if not args.structure.exists():
                raise FileNotFoundError(f"Structure file not found: {args.structure}")
            with open(args.structure, 'r') as f:
                structure = json.load(f)
        elif args.structure_string:
            structure = json.loads(args.structure_string)
        else:
            raise ValueError("Either --structure or --structure-string required")
        
        # Validate structure
        validate_structure(structure)
        
        # Create workbook
        result = create_workbook_from_structure(
            output=args.output,
            structure=structure,
            validate=args.validate
        )
        
        result["status"] = "success"
        result["file"] = str(args.output)
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Created workbook: {args.output}")
            print(f"   Sheets: {result['sheets_created']}")
            print(f"   Formulas: {result['formulas_added']}")
            print(f"   Inputs: {result['inputs_added']}")
            print(f"   Assumptions: {result['assumptions_added']}")
            
            if args.validate and "validation_result" in result:
                val = result["validation_result"]
                if val.get("status") == "success":
                    print(f"   ✅ Validation passed ({val['total_formulas']} formulas)")
                else:
                    print(f"   ❌ Validation found {val['total_errors']} errors")
        
        sys.exit(0)
        
    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }
        
        if args.json:
            print(json.dumps(error_result, indent=2))
        else:
            print(f"❌ Error: {e}", file=sys.stderr)
        
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## **File 4/20: `tools/excel_clone_template.py`**

```python
#!/usr/bin/env python3
"""
Excel Clone Template Tool
Clone existing Excel file with optional value/formula preservation

Usage:
    uv python excel_clone_template.py --source template.xlsx --output new.xlsx --preserve-formatting --json

Exit Codes:
    0: Success
    1: Error occurred
"""

import sys
import json
import argparse
import shutil
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.excel_agent_core import ExcelAgent, ExcelAgentError


def clone_template(
    source: Path,
    output: Path,
    preserve_values: bool,
    preserve_formulas: bool,
    preserve_formatting: bool
) -> Dict[str, Any]:
    """Clone template file."""
    
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    
    # If preserving everything, just copy
    if preserve_values and preserve_formulas and preserve_formatting:
        shutil.copy2(source, output)
        return {
            "status": "success",
            "method": "full_copy",
            "source": str(source),
            "output": str(output),
            "file_size_bytes": output.stat().st_size
        }
    
    # Otherwise, selective copy
    with ExcelAgent(source) as agent:
        agent.open(source, acquire_lock=False)
        
        # Get workbook info
        info = agent.get_workbook_info()
        
        # Clear values/formulas if requested
        if not preserve_values or not preserve_formulas:
            for sheet_name in agent.wb.sheetnames:
                ws = agent.get_sheet(sheet_name)
                
                for row in ws.iter_rows():
                    for cell in row:
                        if not preserve_values and cell.data_type != 'f':
                            cell.value = None
                        
                        if not preserve_formulas and cell.data_type == 'f':
                            cell.value = None
        
        # Save to new location
        agent.save(output)
    
    return {
        "status": "success",
        "method": "selective_copy",
        "source": str(source),
        "output": str(output),
        "sheets": info["sheets"],
        "preserved": {
            "values": preserve_values,
            "formulas": preserve_formulas,
            "formatting": preserve_formatting
        },
        "file_size_bytes": output.stat().st_size
    }


def main():
    parser = argparse.ArgumentParser(
        description="Clone Excel template file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Clone with formatting only (blank template)
  uv python excel_clone_template.py --source template.xlsx --output new.xlsx --preserve-formatting --json
  
  # Clone everything
  uv python excel_clone_template.py --source template.xlsx --output copy.xlsx --preserve-values --preserve-formulas --preserve-formatting --json
  
  # Clone formulas and formatting only
  uv python excel_clone_template.py --source template.xlsx --output model.xlsx --preserve-formulas --preserve-formatting --json
        """
    )
    
    parser.add_argument(
        '--source',
        required=True,
        type=Path,
        help='Source template file'
    )
    
    parser.add_argument(
        '--output',
        required=True,
        type=Path,
        help='Output file path'
    )
    
    parser.add_argument(
        '--preserve-values',
        action='store_true',
        help='Keep existing cell values'
    )
    
    parser.add_argument(
        '--preserve-formulas',
        action='store_true',
        help='Keep existing formulas'
    )
    
    parser.add_argument(
        '--preserve-formatting',
        action='store_true',
        default=True,
        help='Keep formatting (default: true)'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON response'
    )
    
    args = parser.parse_args()
    
    try:
        result = clone_template(
            source=args.source,
            output=args.output,
            preserve_values=args.preserve_values,
            preserve_formulas=args.preserve_formulas,
            preserve_formatting=args.preserve_formatting
        )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Cloned template: {result['output']}")
            print(f"   Source: {result['source']}")
            print(f"   Method: {result['method']}")
            if 'sheets' in result:
                print(f"   Sheets: {', '.join(result['sheets'])}")
        
        sys.exit(0)
        
    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }
        
        if args.json:
            print(json.dumps(error_result, indent=2))
        else:
            print(f"❌ Error: {e}", file=sys.stderr)
        
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## **File 5/20: `tools/excel_set_value.py`**

```python
#!/usr/bin/env python3
"""
Excel Set Value Tool
Set a single cell value with optional styling

Usage:
    uv python excel_set_value.py --file model.xlsx --sheet Sheet1 --cell A1 --value "Revenue" --type string --json

Exit Codes:
    0: Success
    1: Error occurred
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Union
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.excel_agent_core import (
    ExcelAgent, ExcelAgentError, is_valid_cell_reference
)


def parse_value(value_str: str, value_type: str) -> Union[str, int, float, datetime]:
    """Parse value according to type."""
    
    if value_type == "auto":
        # Try to auto-detect
        try:
            if '.' in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            return value_str
    
    elif value_type == "string":
        return value_str
    
    elif value_type == "number":
        return float(value_str)
    
    elif value_type == "integer":
        return int(value_str)
    
    elif value_type == "date":
        return datetime.fromisoformat(value_str)
    
    else:
        raise ValueError(f"Unknown value type: {value_type}")


def set_cell_value(
    filepath: Path,
    sheet: str,
    cell: str,
    value: Any,
    style: str = None,
    number_format: str = None
) -> Dict[str, Any]:
    """Set cell value."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    if not is_valid_cell_reference(cell):
        raise ValueError(f"Invalid cell reference: {cell}")
    
    with ExcelAgent(filepath) as agent:
        agent.open(filepath)
        
        # Verify sheet exists
        if sheet not in agent.wb.sheetnames:
            raise ValueError(f"Sheet '{sheet}' not found. Available: {agent.wb.sheetnames}")
        
        # Set value
        agent.set_cell_value(
            sheet=sheet,
            cell=cell,
            value=value,
            style=style,
            number_format=number_format
        )
        
        agent.save()
    
    return {
        "status": "success",
        "file": str(filepath),
        "sheet": sheet,
        "cell": cell,
        "value": str(value),
        "type": type(value).__name__,
        "style": style,
        "number_format": number_format
    }


def main():
    parser = argparse.ArgumentParser(
        description="Set Excel cell value",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Set string value
  uv python excel_set_value.py --file model.xlsx --sheet "Income Statement" --cell A1 --value "Revenue" --type string --json
  
  # Set number with auto-detect
  uv python excel_set_value.py --file model.xlsx --sheet Data --cell B2 --value "1500000" --type auto --json
  
  # Set with custom format
  uv python excel_set_value.py --file model.xlsx --sheet Data --cell C3 --value "0.15" --type number --format "0.0%" --json
        """
    )
    
    parser.add_argument(
        '--file',
        required=True,
        type=Path,
        help='Excel file path'
    )
    
    parser.add_argument(
        '--sheet',
        required=True,
        help='Sheet name'
    )
    
    parser.add_argument(
        '--cell',
        required=True,
        help='Cell reference (e.g., A1, B10)'
    )
    
    parser.add_argument(
        '--value',
        required=True,
        help='Value to set'
    )
    
    parser.add_argument(
        '--type',
        default='auto',
        choices=['auto', 'string', 'number', 'integer', 'date'],
        help='Value type (default: auto)'
    )
    
    parser.add_argument(
        '--style',
        help='Named style to apply'
    )
    
    parser.add_argument(
        '--format',
        help='Number format string'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON response'
    )
    
    args = parser.parse_args()
    
    try:
        # Parse value
        parsed_value = parse_value(args.value, args.type)
        
        # Set value
        result = set_cell_value(
            filepath=args.file,
            sheet=args.sheet,
            cell=args.cell,
            value=parsed_value,
            style=args.style,
            number_format=args.format
        )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Set {args.sheet}!{args.cell} = {parsed_value}")
        
        sys.exit(0)
        
    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }
        
        if args.json:
            print(json.dumps(error_result, indent=2))
        else:
            print(f"❌ Error: {e}", file=sys.stderr)
        
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## **File 6/20: `tools/excel_add_formula.py`**

```python
#!/usr/bin/env python3
"""
Excel Add Formula Tool
Add validated formula to cell with security checks

Usage:
    uv python excel_add_formula.py --file model.xlsx --sheet Sheet1 --cell B10 --formula "=SUM(B2:B9)" --json

Exit Codes:
    0: Success
    1: Error occurred
    2: Security error (dangerous formula)
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.excel_agent_core import (
    ExcelAgent, FormulaError, SecurityError, is_valid_cell_reference
)


def add_formula(
    filepath: Path,
    sheet: str,
    cell: str,
    formula: str,
    validate_refs: bool,
    allow_external: bool,
    style: str = None
) -> Dict[str, Any]:
    """Add formula to cell."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    if not is_valid_cell_reference(cell):
        raise ValueError(f"Invalid cell reference: {cell}")
    
    with ExcelAgent(filepath) as agent:
        agent.open(filepath)
        
        # Verify sheet exists
        if sheet not in agent.wb.sheetnames:
            raise ValueError(f"Sheet '{sheet}' not found")
        
        # Add formula (this will do security checks)
        agent.add_formula(
            sheet=sheet,
            cell=cell,
            formula=formula,
            validate_refs=validate_refs,
            allow_external=allow_external
        )
        
        agent.save()
    
    return {
        "status": "success",
        "file": str(filepath),
        "sheet": sheet,
        "cell": cell,
        "formula": formula if formula.startswith('=') else f'={formula}',
        "security_checks": {
            "validate_refs": validate_refs,
            "allow_external": allow_external
        }
    }


def main():
    parser = argparse.ArgumentParser(
        description="Add validated formula to Excel cell",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Security:
  By default, formulas are checked for:
  - Invalid sheet references
  - External workbook links
  - Dangerous functions (WEBSERVICE, CALL, etc.)
  - Excessive complexity
  
  Use --allow-external to permit external references (not recommended for untrusted sources)

Examples:
  # Simple SUM formula
  uv python excel_add_formula.py --file model.xlsx --sheet "Income Statement" --cell B10 --formula "=SUM(B2:B9)" --json
  
  # Cross-sheet reference
  uv python excel_add_formula.py --file model.xlsx --sheet Forecast --cell C5 --formula "=Assumptions!B2*C4" --json
  
  # With external reference (requires explicit permission)
  uv python excel_add_formula.py --file model.xlsx --sheet Data --cell A1 --formula "=WEBSERVICE('https://api.example.com')" --allow-external --json
        """
    )
    
    parser.add_argument(
        '--file',
        required=True,
        type=Path,
        help='Excel file path'
    )
    
    parser.add_argument(
        '--sheet',
        required=True,
        help='Sheet name'
    )
    
    parser.add_argument(
        '--cell',
        required=True,
        help='Target cell reference'
    )
    
    parser.add_argument(
        '--formula',
        required=True,
        help='Formula (with or without leading =)'
    )
    
    parser.add_argument(
        '--validate-refs',
        action='store_true',
        default=True,
        help='Validate sheet references (default: true)'
    )
    
    parser.add_argument(
        '--no-validate-refs',
        dest='validate_refs',
        action='store_false',
        help='Skip reference validation'
    )
    
    parser.add_argument(
        '--allow-external',
        action='store_true',
        help='Allow external references (SECURITY RISK)'
    )
    
    parser.add_argument(
        '--style',
        help='Named style to apply'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON response'
    )
    
    args = parser.parse_args()
    
    try:
        result = add_formula(
            filepath=args.file,
            sheet=args.sheet,
            cell=args.cell,
            formula=args.formula,
            validate_refs=args.validate_refs,
            allow_external=args.allow_external,
            style=args.style
        )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Added formula to {args.sheet}!{args.cell}")
            print(f"   {result['formula']}")
        
        sys.exit(0)
        
    except SecurityError as e:
        error_result = {
            "status": "security_error",
            "error": str(e),
            "error_type": "SecurityError",
            "hint": "Use --allow-external to explicitly permit dangerous operations"
        }
        
        if args.json:
            print(json.dumps(error_result, indent=2))
        else:
            print(f"🔒 Security Error: {e}", file=sys.stderr)
            print("   Use --allow-external to override (not recommended)", file=sys.stderr)
        
        sys.exit(2)
        
    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }
        
        if args.json:
            print(json.dumps(error_result, indent=2))
        else:
            print(f"❌ Error: {e}", file=sys.stderr)
        
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## **File 7/20: `tools/excel_add_financial_input.py`**

```python
#!/usr/bin/env python3
"""
Excel Add Financial Input Tool
Add blue-styled financial input with source comment

Usage:
    uv python excel_add_financial_input.py --file model.xlsx --sheet Assumptions --cell B2 --value 0.15 --comment "Source: 10-K" --format percent --json

Exit Codes:
    0: Success
    1: Error occurred
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.excel_agent_core import (
    ExcelAgent, is_valid_cell_reference, get_number_format
)


def add_financial_input(
    filepath: Path,
    sheet: str,
    cell: str,
    value: float,
    comment: str,
    format_type: str,
    decimals: int
) -> Dict[str, Any]:
    """Add financial input with blue style."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    if not is_valid_cell_reference(cell):
        raise ValueError(f"Invalid cell reference: {cell}")
    
    # Get number format
    number_format = None
    if format_type:
        number_format = get_number_format(format_type, decimals)
    
    with ExcelAgent(filepath) as agent:
        agent.open(filepath)
        
        if sheet not in agent.wb.sheetnames:
            raise ValueError(f"Sheet '{sheet}' not found")
        
        agent.add_financial_input(
            sheet=sheet,
            cell=cell,
            value=value,
            comment=comment,
            number_format=number_format
        )
        
        agent.save()
    
    return {
        "status": "success",
        "file": str(filepath),
        "sheet": sheet,
        "cell": cell,
        "value": value,
        "comment": comment,
        "format": format_type,
        "style": "FinancialInput (blue)"
    }


def main():
    parser = argparse.ArgumentParser(
        description="Add financial input to Excel (blue style)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Financial Input Convention:
  Blue text indicates hardcoded inputs that should be traceable to source documents.
  Always include a comment with the source attribution.

Examples:
  # Growth rate from 10-K
  uv python excel_add_financial_input.py --file model.xlsx --sheet Assumptions --cell B2 --value 0.15 --comment "Source: Company 10-K FY2024, Page 45" --format percent --json
  
  # Revenue base
  uv python excel_add_financial_input.py --file model.xlsx --sheet Assumptions --cell B3 --value 1500000 --comment "Source: Q4 2023 earnings release" --format currency --json
  
  # Multiple (no decimal format)
  uv python excel_add_financial_input.py --file model.xlsx --sheet Assumptions --cell B4 --value 12.5 --comment "Industry average P/E" --format number --decimals 1 --json
        """
    )
    
    parser.add_argument(
        '--file',
        required=True,
        type=Path,
        help='Excel file path'
    )
    
    parser.add_argument(
        '--sheet',
        required=True,
        help='Sheet name'
    )
    
    parser.add_argument(
        '--cell',
        required=True,
        help='Cell reference'
    )
    
    parser.add_argument(
        '--value',
        required=True,
        type=float,
        help='Numeric value'
    )
    
    parser.add_argument(
        '--comment',
        help='Source attribution comment'
    )
    
    parser.add_argument(
        '--format',
        choices=['currency', 'percent', 'number', 'accounting'],
        help='Number format type'
    )
    
    parser.add_argument(
        '--decimals',
        type=int,
        default=2,
        help='Decimal places (default: 2)'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON response'
    )
    
    args = parser.parse_args()
    
    try:
        result = add_financial_input(
            filepath=args.file,
            sheet=args.sheet,
            cell=args.cell,
            value=args.value,
            comment=args.comment,
            format_type=args.format,
            decimals=args.decimals
        )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Added financial input: {args.sheet}!{args.cell} = {args.value}")
            if args.comment:
                print(f"   Comment: {args.comment}")
        
        sys.exit(0)
        
    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }
        
        if args.json:
            print(json.dumps(error_result, indent=2))
        else:
            print(f"❌ Error: {e}", file=sys.stderr)
        
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## **File 8/20: `tools/excel_add_assumption.py`**

```python
#!/usr/bin/env python3
"""
Excel Add Assumption Tool
Add yellow-highlighted assumption with description

Usage:
    uv python excel_add_assumption.py --file model.xlsx --sheet Assumptions --cell B3 --value 1000000 --description "FY2024 baseline revenue" --json

Exit Codes:
    0: Success
    1: Error occurred
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Union

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.excel_agent_core import (
    ExcelAgent, is_valid_cell_reference, get_number_format
)


def add_assumption(
    filepath: Path,
    sheet: str,
    cell: str,
    value: Union[str, float, int],
    description: str,
    format_type: str,
    decimals: int
) -> Dict[str, Any]:
    """Add assumption with yellow highlight."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    if not is_valid_cell_reference(cell):
        raise ValueError(f"Invalid cell reference: {cell}")
    
    # Get number format
    number_format = None
    if format_type:
        number_format = get_number_format(format_type, decimals)
    
    with ExcelAgent(filepath) as agent:
        agent.open(filepath)
        
        if sheet not in agent.wb.sheetnames:
            raise ValueError(f"Sheet '{sheet}' not found")
        
        agent.add_assumption(
            sheet=sheet,
            cell=cell,
            value=value,
            description=description,
            number_format=number_format
        )
        
        agent.save()
    
    return {
        "status": "success",
        "file": str(filepath),
        "sheet": sheet,
        "cell": cell,
        "value": value,
        "description": description,
        "format": format_type,
        "style": "FinancialAssumption (yellow highlight)"
    }


def main():
    parser = argparse.ArgumentParser(
        description="Add key assumption to Excel (yellow highlight)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Assumption Convention:
  Yellow background indicates key assumptions that drive the model.
  These should be clearly documented and subject to sensitivity analysis.

Examples:
  # Revenue baseline assumption
  uv python excel_add_assumption.py --file model.xlsx --sheet Assumptions --cell B3 --value 1000000 --description "FY2024 baseline revenue from business plan" --format currency --json
  
  # Growth rate assumption
  uv python excel_add_assumption.py --file model.xlsx --sheet Assumptions --cell B4 --value 0.20 --description "Annual growth rate based on market analysis" --format percent --json
  
  # Text assumption
  uv python excel_add_assumption.py --file model.xlsx --sheet Assumptions --cell B5 --value "Conservative" --description "Revenue recognition policy assumption" --json
        """
    )
    
    parser.add_argument(
        '--file',
        required=True,
        type=Path,
        help='Excel file path'
    )
    
    parser.add_argument(
        '--sheet',
        required=True,
        help='Sheet name'
    )
    
    parser.add_argument(
        '--cell',
        required=True,
        help='Cell reference'
    )
    
    parser.add_argument(
        '--value',
        required=True,
        help='Assumption value'
    )
    
    parser.add_argument(
        '--description',
        required=True,
        help='Description of what is being assumed'
    )
    
    parser.add_argument(
        '--format',
        choices=['currency', 'percent', 'number', 'accounting'],
        help='Number format type'
    )
    
    parser.add_argument(
        '--decimals',
        type=int,
        default=2,
        help='Decimal places (default: 2)'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON response'
    )
    
    args = parser.parse_args()
    
    try:
        # Try to parse as number
        try:
            value = float(args.value)
        except ValueError:
            value = args.value
        
        result = add_assumption(
            filepath=args.file,
            sheet=args.sheet,
            cell=args.cell,
            value=value,
            description=args.description,
            format_type=args.format,
            decimals=args.decimals
        )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Added assumption: {args.sheet}!{args.cell} = {value}")
            print(f"   Description: {args.description}")
        
        sys.exit(0)
        
    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }
        
        if args.json:
            print(json.dumps(error_result, indent=2))
        else:
            print(f"❌ Error: {e}", file=sys.stderr)
        
        sys.exit(1)


if __name__ == "__main__":
    main()
```

