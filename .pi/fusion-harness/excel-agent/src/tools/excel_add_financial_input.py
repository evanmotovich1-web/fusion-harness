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
