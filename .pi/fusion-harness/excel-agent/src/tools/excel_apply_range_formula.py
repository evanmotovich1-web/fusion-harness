#!/usr/bin/env python3
"""
Excel Apply Range Formula Tool
Apply formula template to entire range with auto-adjustment

Usage:
    uv python excel_apply_range_formula.py --file model.xlsx --sheet Forecast --range B2:B10 --formula "=A{row}*1.15" --json

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
    ExcelAgent, is_valid_range_reference, parse_range, get_cell_coordinates
)


def apply_range_formula(
    filepath: Path,
    sheet: str,
    range_ref: str,
    formula_template: str
) -> Dict[str, Any]:
    """Apply formula to range."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    if not is_valid_range_reference(range_ref):
        raise ValueError(f"Invalid range reference: {range_ref}")
    
    with ExcelAgent(filepath) as agent:
        agent.open(filepath)
        
        if sheet not in agent.wb.sheetnames:
            raise ValueError(f"Sheet '{sheet}' not found")
        
        # Apply formula
        cells_modified = agent.apply_range_formula(
            sheet=sheet,
            range_ref=range_ref,
            formula_template=formula_template
        )
        
        # Get sample formulas
        start_cell, end_cell = parse_range(range_ref)
        start_row, start_col = get_cell_coordinates(start_cell)
        end_row, end_col = get_cell_coordinates(end_cell)
        
        ws = agent.get_sheet(sheet)
        sample_formulas = {}
        
        # Sample first, middle, and last
        if start_row == end_row and start_col == end_col:
            # Single cell
            sample_formulas[start_cell] = ws[start_cell].value
        else:
            sample_formulas[start_cell] = ws[start_cell].value
            sample_formulas[end_cell] = ws[end_cell].value
        
        agent.save()
    
    return {
        "status": "success",
        "file": str(filepath),
        "sheet": sheet,
        "range": range_ref,
        "cells_modified": cells_modified,
        "formula_template": formula_template,
        "sample_formulas": sample_formulas
    }


def main():
    parser = argparse.ArgumentParser(
        description="Apply formula to Excel range with auto-adjustment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Formula Templates:
  Use placeholders that will be replaced for each cell:
  - {row}  : Current row number
  - {col}  : Current column letter
  - {cell} : Current cell reference (e.g., B5)

Examples:
  # Apply growth formula to column
  uv python excel_apply_range_formula.py --file model.xlsx --sheet Forecast --range B2:B10 --formula "=A{row}*(1+$C$1)" --json
  
  # Percentage of total
  uv python excel_apply_range_formula.py --file model.xlsx --sheet Analysis --range D2:D20 --formula "=C{row}/C$21" --json
  
  # Year-over-year growth
  uv python excel_apply_range_formula.py --file model.xlsx --sheet Data --range C2:C50 --formula "=(B{row}-A{row})/A{row}" --json
  
  # Column sum references
  uv python excel_apply_range_formula.py --file model.xlsx --sheet Summary --range A10:Z10 --formula "=SUM({col}2:{col}9)" --json

Output:
  {
    "status": "success",
    "cells_modified": 9,
    "range": "B2:B10",
    "sample_formulas": {
      "B2": "=A2*(1+$C$1)",
      "B10": "=A10*(1+$C$1)"
    }
  }
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
        '--range',
        required=True,
        help='Target range (e.g., B2:B10, A1:C5)'
    )
    
    parser.add_argument(
        '--formula',
        required=True,
        help='Formula template with {row}, {col}, or {cell} placeholders'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON response'
    )
    
    args = parser.parse_args()
    
    try:
        result = apply_range_formula(
            filepath=args.file,
            sheet=args.sheet,
            range_ref=args.range,
            formula_template=args.formula
        )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Applied formula to {result['cells_modified']} cells in {args.range}")
            print(f"   Template: {args.formula}")
            print(f"   Sample: {list(result['sample_formulas'].values())[0]}")
        
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
