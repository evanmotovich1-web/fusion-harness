#!/usr/bin/env python3
"""
Excel Get Info Tool
Get workbook metadata and statistics (read-only)

Usage:
    uv python excel_get_info.py --file model.xlsx --detailed --include-sheets --json

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

from core.excel_agent_core import ExcelAgent


def get_workbook_info(
    filepath: Path,
    detailed: bool,
    include_sheets: bool
) -> Dict[str, Any]:
    """Get workbook information."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    with ExcelAgent(filepath) as agent:
        agent.open(filepath, acquire_lock=False)
        
        info = agent.get_workbook_info()
        
        # Add file stats
        stat = filepath.stat()
        info["file_size_human"] = f"{stat.st_size / 1024:.1f} KB"
        
        # Add detailed sheet info if requested
        if include_sheets:
            sheet_details = {}
            
            for sheet_name in agent.wb.sheetnames:
                ws = agent.get_sheet(sheet_name)
                
                sheet_info = {
                    "max_row": ws.max_row,
                    "max_column": ws.max_column,
                }
                
                if detailed:
                    # Count formulas and data cells
                    formulas = 0
                    data_cells = 0
                    
                    for row in ws.iter_rows(max_row=min(ws.max_row or 1, 1000)):  # Sample first 1000 rows
                        for cell in row:
                            if cell.value is not None:
                                data_cells += 1
                                if cell.data_type == 'f':
                                    formulas += 1
                    
                    sheet_info["formulas_sampled"] = formulas
                    sheet_info["data_cells_sampled"] = data_cells
                
                sheet_details[sheet_name] = sheet_info
            
            info["sheet_details"] = sheet_details
    
    return info


def main():
    parser = argparse.ArgumentParser(
        description="Get Excel workbook metadata and statistics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic info
  uv python excel_get_info.py --file model.xlsx --json
  
  # Detailed info with sheet breakdown
  uv python excel_get_info.py --file model.xlsx --detailed --include-sheets --json
  
  # Quick sheet list
  uv python excel_get_info.py --file model.xlsx --json

Output:
  {
    "status": "success",
    "file": "model.xlsx",
    "file_size_bytes": 45678,
    "file_size_human": "44.6 KB",
    "modified": "2024-01-15T14:25:00",
    "sheets": ["Assumptions", "Income Statement", "Balance Sheet"],
    "sheet_count": 3,
    "total_formulas": 156,
    "total_cells_with_data": 342,
    "sheet_details": {
      "Income Statement": {
        "max_row": 50,
        "max_column": 8,
        "formulas_sampled": 45,
        "data_cells_sampled": 120
      }
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
        '--detailed',
        action='store_true',
        help='Include detailed statistics (slower for large files)'
    )
    
    parser.add_argument(
        '--include-sheets',
        action='store_true',
        help='Include per-sheet information'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        default=True,
        help='Output JSON response (default: true)'
    )
    
    args = parser.parse_args()
    
    try:
        result = get_workbook_info(
            filepath=args.file,
            detailed=args.detailed,
            include_sheets=args.include_sheets
        )
        
        result["status"] = "success"
        
        print(json.dumps(result, indent=2, default=str))
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
