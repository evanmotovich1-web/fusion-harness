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
