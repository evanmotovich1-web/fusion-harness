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
