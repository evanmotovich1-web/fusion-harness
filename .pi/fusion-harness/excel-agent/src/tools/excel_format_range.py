#!/usr/bin/env python3
"""
Excel Format Range Tool
Apply number formatting to range

Usage:
    uv python excel_format_range.py --file model.xlsx --sheet "Income Statement" --range C2:H20 --format currency --decimals 0 --json

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
    ExcelAgent, is_valid_range_reference, get_number_format
)


def format_range(
    filepath: Path,
    sheet: str,
    range_ref: str,
    format_type: str,
    custom_format: str,
    decimals: int
) -> Dict[str, Any]:
    """Apply number format to range."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    if not is_valid_range_reference(range_ref):
        raise ValueError(f"Invalid range reference: {range_ref}")
    
    # Get format string
    if custom_format:
        number_format = custom_format
    else:
        number_format = get_number_format(format_type, decimals)
    
    with ExcelAgent(filepath) as agent:
        agent.open(filepath)
        
        if sheet not in agent.wb.sheetnames:
            raise ValueError(f"Sheet '{sheet}' not found")
        
        cells_formatted = agent.format_range(
            sheet=sheet,
            range_ref=range_ref,
            number_format=number_format
        )
        
        agent.save()
    
    return {
        "status": "success",
        "file": str(filepath),
        "sheet": sheet,
        "range": range_ref,
        "cells_formatted": cells_formatted,
        "format_type": format_type or "custom",
        "format_string": number_format
    }


def main():
    parser = argparse.ArgumentParser(
        description="Apply number formatting to Excel range",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Format Types:
  - currency    : $#,##0.00 with red negatives
  - percent     : 0.0%
  - number      : #,##0.00
  - accounting  : Accounting format with alignment
  - date        : mm/dd/yyyy

Examples:
  # Currency with no decimals
  uv python excel_format_range.py --file model.xlsx --sheet "Income Statement" --range C2:H20 --format currency --decimals 0 --json
  
  # Percentage with 1 decimal
  uv python excel_format_range.py --file model.xlsx --sheet Analysis --range D2:D50 --format percent --decimals 1 --json
  
  # Custom format
  uv python excel_format_range.py --file model.xlsx --sheet Data --range A1:A100 --custom-format "0.00%" --json
  
  # Date format
  uv python excel_format_range.py --file model.xlsx --sheet Timeline --range B1:B365 --format date --json
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
        help='Target range (e.g., C2:H20)'
    )
    
    parser.add_argument(
        '--format',
        choices=['currency', 'percent', 'number', 'accounting', 'date'],
        help='Format type'
    )
    
    parser.add_argument(
        '--custom-format',
        help='Custom Excel format string (overrides --format)'
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
        if not args.format and not args.custom_format:
            raise ValueError("Either --format or --custom-format required")
        
        result = format_range(
            filepath=args.file,
            sheet=args.sheet,
            range_ref=args.range,
            format_type=args.format,
            custom_format=args.custom_format,
            decimals=args.decimals
        )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Formatted {result['cells_formatted']} cells in {args.range}")
            print(f"   Format: {result['format_string']}")
        
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
