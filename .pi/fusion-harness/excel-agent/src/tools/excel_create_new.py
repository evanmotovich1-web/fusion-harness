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
