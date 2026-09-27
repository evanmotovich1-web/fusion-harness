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
