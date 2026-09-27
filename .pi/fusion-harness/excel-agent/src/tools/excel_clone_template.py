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
