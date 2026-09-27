#!/usr/bin/env python3
"""
Excel Export Sheet Tool
Export worksheet to CSV or JSON

Usage:
    uv python excel_export_sheet.py --file model.xlsx --sheet "Income Statement" --output forecast.csv --format csv --json

Exit Codes:
    0: Success
    1: Error occurred
"""

import sys
import json
import argparse
import csv
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.excel_agent_core import ExcelAgent, export_sheet_to_csv, is_valid_range_reference


def export_sheet_to_json(
    filepath: Path,
    sheet: str,
    output: Path,
    range_ref: str,
    include_formulas: bool
) -> int:
    """Export sheet to JSON."""
    with ExcelAgent(filepath) as agent:
        agent.open(filepath, acquire_lock=False)
        ws = agent.get_sheet(sheet)
        
        data = []
        
        if range_ref:
            from core.excel_agent_core import parse_range, get_cell_coordinates
            start_cell, end_cell = parse_range(range_ref)
            start_row, start_col = get_cell_coordinates(start_cell)
            end_row, end_col = get_cell_coordinates(end_cell)
            rows = ws.iter_rows(min_row=start_row, max_row=end_row,
                               min_col=start_col, max_col=end_col)
        else:
            rows = ws.iter_rows()
        
        for row in rows:
            row_data = []
            for cell in row:
                if include_formulas and cell.data_type == 'f':
                    row_data.append({
                        "formula": cell.value,
                        "value": None  # Formulas don't have cached values in write mode
                    })
                else:
                    row_data.append(cell.value)
            data.append(row_data)
        
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        
        return len(data)


def export_sheet(
    filepath: Path,
    sheet: str,
    output: Path,
    format_type: str,
    range_ref: str,
    include_formulas: bool
) -> Dict[str, Any]:
    """Export sheet to file."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    if range_ref and not is_valid_range_reference(range_ref):
        raise ValueError(f"Invalid range reference: {range_ref}")
    
    # Auto-detect format from extension
    if format_type == "auto":
        ext = output.suffix.lower()
        if ext == ".csv":
            format_type = "csv"
        elif ext == ".json":
            format_type = "json"
        else:
            raise ValueError(f"Cannot auto-detect format from extension: {ext}")
    
    # Export
    if format_type == "csv":
        row_count = export_sheet_to_csv(filepath, sheet, output, range_ref)
    elif format_type == "json":
        row_count = export_sheet_to_json(filepath, sheet, output, range_ref, include_formulas)
    else:
        raise ValueError(f"Unknown format: {format_type}")
    
    file_size = output.stat().st_size
    
    return {
        "status": "success",
        "source_file": str(filepath),
        "sheet": sheet,
        "output_file": str(output),
        "format": format_type,
        "rows_exported": row_count,
        "file_size_bytes": file_size,
        "range": range_ref,
        "included_formulas": include_formulas
    }


def main():
    parser = argparse.ArgumentParser(
        description="Export Excel worksheet to CSV or JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export entire sheet to CSV
  uv python excel_export_sheet.py --file model.xlsx --sheet "Income Statement" --output forecast.csv --json
  
  # Export range to JSON
  uv python excel_export_sheet.py --file model.xlsx --sheet Data --output data.json --range A1:D100 --json
  
  # Export with formulas
  uv python excel_export_sheet.py --file model.xlsx --sheet Calculations --output calcs.json --format json --include-formulas --json
  
  # Auto-detect format from extension
  uv python excel_export_sheet.py --file model.xlsx --sheet Summary --output summary.csv --format auto --json
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
        help='Sheet name to export'
    )
    
    parser.add_argument(
        '--output',
        required=True,
        type=Path,
        help='Output file path'
    )
    
    parser.add_argument(
        '--format',
        choices=['csv', 'json', 'auto'],
        default='auto',
        help='Output format (default: auto-detect from extension)'
    )
    
    parser.add_argument(
        '--range',
        help='Optional range to export (e.g., A1:D100)'
    )
    
    parser.add_argument(
        '--include-formulas',
        action='store_true',
        help='Export formulas instead of values (JSON only)'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON response'
    )
    
    args = parser.parse_args()
    
    try:
        result = export_sheet(
            filepath=args.file,
            sheet=args.sheet,
            output=args.output,
            format_type=args.format,
            range_ref=args.range,
            include_formulas=args.include_formulas
        )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Exported {result['rows_exported']} rows to {args.output}")
            print(f"   Format: {result['format']}")
            print(f"   Size: {result['file_size_bytes']} bytes")
        
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
