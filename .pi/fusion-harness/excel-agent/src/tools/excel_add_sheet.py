#!/usr/bin/env python3
"""
Excel Add Sheet Tool
Add new worksheet to workbook

Usage:
    uv python excel_add_sheet.py --file model.xlsx --sheet "Scenario Analysis" --index 2 --json

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

from core.excel_agent_core import ExcelAgent, is_valid_sheet_name, sanitize_sheet_name


def add_sheet(
    filepath: Path,
    sheet_name: str,
    index: int,
    copy_from: str
) -> Dict[str, Any]:
    """Add new worksheet."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    # Validate sheet name
    if not is_valid_sheet_name(sheet_name):
        sanitized = sanitize_sheet_name(sheet_name)
        if sanitized != sheet_name:
            return {
                "status": "error",
                "error": f"Invalid sheet name: '{sheet_name}'. Suggested: '{sanitized}'"
            }
    
    with ExcelAgent(filepath) as agent:
        agent.open(filepath)
        
        # Check if sheet already exists
        if sheet_name in agent.wb.sheetnames:
            raise ValueError(f"Sheet '{sheet_name}' already exists")
        
        # Copy from existing sheet if specified
        if copy_from:
            if copy_from not in agent.wb.sheetnames:
                raise ValueError(f"Source sheet '{copy_from}' not found")
            
            source_sheet = agent.get_sheet(copy_from)
            new_sheet = agent.wb.copy_worksheet(source_sheet)
            new_sheet.title = sheet_name
            
            # Move to index if specified
            if index is not None:
                agent.wb.move_sheet(new_sheet, offset=index - agent.wb.index(new_sheet))
        else:
            # Create new blank sheet
            agent.add_sheet(sheet_name, index)
        
        all_sheets = agent.wb.sheetnames
        actual_index = all_sheets.index(sheet_name)
        
        agent.save()
    
    return {
        "status": "success",
        "file": str(filepath),
        "sheet": sheet_name,
        "index": actual_index,
        "all_sheets": all_sheets,
        "copied_from": copy_from
    }


def main():
    parser = argparse.ArgumentParser(
        description="Add new worksheet to Excel workbook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add sheet at end
  uv python excel_add_sheet.py --file model.xlsx --sheet "Scenario Analysis" --json
  
  # Add sheet at specific position
  uv python excel_add_sheet.py --file model.xlsx --sheet "Executive Summary" --index 0 --json
  
  # Copy existing sheet
  uv python excel_add_sheet.py --file model.xlsx --sheet "Q2 Forecast" --copy-from "Q1 Forecast" --json
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
        help='New sheet name'
    )
    
    parser.add_argument(
        '--index',
        type=int,
        help='Position to insert (0-based, default: end)'
    )
    
    parser.add_argument(
        '--copy-from',
        help='Copy content from existing sheet'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON response'
    )
    
    args = parser.parse_args()
    
    try:
        result = add_sheet(
            filepath=args.file,
            sheet_name=args.sheet,
            index=args.index,
            copy_from=args.copy_from
        )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Added sheet: {args.sheet}")
            print(f"   Position: {result['index']}")
            print(f"   All sheets: {', '.join(result['all_sheets'])}")
            if args.copy_from:
                print(f"   Copied from: {args.copy_from}")
        
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
