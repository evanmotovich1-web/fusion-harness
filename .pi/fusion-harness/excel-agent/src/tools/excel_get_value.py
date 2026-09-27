#!/usr/bin/env python3
"""
Excel Get Value Tool
Read cell value or formula (read-only operation)

Usage:
    uv python excel_get_value.py --file model.xlsx --sheet Sheet1 --cell B10 --get-both --json

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

from core.excel_agent_core import ExcelAgent, is_valid_cell_reference


def get_cell_value(
    filepath: Path,
    sheet: str,
    cell: str,
    get_formula: bool,
    get_both: bool
) -> Dict[str, Any]:
    """Get cell value and/or formula."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    if not is_valid_cell_reference(cell):
        raise ValueError(f"Invalid cell reference: {cell}")
    
    with ExcelAgent(filepath) as agent:
        agent.open(filepath, acquire_lock=False)  # Read-only
        
        if sheet not in agent.wb.sheetnames:
            raise ValueError(f"Sheet '{sheet}' not found")
        
        # Get comprehensive cell info
        cell_info = agent.get_cell_info(sheet, cell)
        
        result = {
            "status": "success",
            "file": str(filepath),
            "sheet": sheet,
            "cell": cell,
        }
        
        if get_both or not get_formula:
            result["value"] = cell_info["value"]
        
        if get_both or get_formula:
            if cell_info["is_formula"]:
                result["formula"] = cell_info["value"]
            else:
                result["formula"] = None
        
        result["data_type"] = cell_info["data_type"]
        result["number_format"] = cell_info["number_format"]
        result["is_formula"] = cell_info["is_formula"]
        
        if cell_info["comment"]:
            result["comment"] = cell_info["comment"]
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Get Excel cell value or formula (read-only)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get cell value
  uv python excel_get_value.py --file model.xlsx --sheet "Income Statement" --cell B10 --json
  
  # Get formula
  uv python excel_get_value.py --file model.xlsx --sheet Data --cell C5 --get-formula --json
  
  # Get both value and formula
  uv python excel_get_value.py --file model.xlsx --sheet Forecast --cell D8 --get-both --json

Output:
  {
    "status": "success",
    "file": "model.xlsx",
    "sheet": "Income Statement",
    "cell": "B10",
    "value": 150000,
    "formula": "=SUM(B2:B9)",
    "data_type": "f",
    "number_format": "$#,##0",
    "is_formula": true
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
        '--cell',
        required=True,
        help='Cell reference'
    )
    
    parser.add_argument(
        '--get-formula',
        action='store_true',
        help='Return formula instead of value'
    )
    
    parser.add_argument(
        '--get-both',
        action='store_true',
        help='Return both value and formula'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        default=True,  # Default to JSON for this tool
        help='Output JSON response (default: true)'
    )
    
    args = parser.parse_args()
    
    try:
        result = get_cell_value(
            filepath=args.file,
            sheet=args.sheet,
            cell=args.cell,
            get_formula=args.get_formula,
            get_both=args.get_both
        )
        
        print(json.dumps(result, indent=2))
        sys.exit(0)
        
    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }
        
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
