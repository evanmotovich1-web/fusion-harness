# 🚀 Continuing Implementation - Tools 9-16 & Documentation

---

## **File 9/20: `tools/excel_get_value.py`**

```python
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
```

---

## **File 10/20: `tools/excel_apply_range_formula.py`**

```python
#!/usr/bin/env python3
"""
Excel Apply Range Formula Tool
Apply formula template to entire range with auto-adjustment

Usage:
    uv python excel_apply_range_formula.py --file model.xlsx --sheet Forecast --range B2:B10 --formula "=A{row}*1.15" --json

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
    ExcelAgent, is_valid_range_reference, parse_range, get_cell_coordinates
)


def apply_range_formula(
    filepath: Path,
    sheet: str,
    range_ref: str,
    formula_template: str
) -> Dict[str, Any]:
    """Apply formula to range."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    if not is_valid_range_reference(range_ref):
        raise ValueError(f"Invalid range reference: {range_ref}")
    
    with ExcelAgent(filepath) as agent:
        agent.open(filepath)
        
        if sheet not in agent.wb.sheetnames:
            raise ValueError(f"Sheet '{sheet}' not found")
        
        # Apply formula
        cells_modified = agent.apply_range_formula(
            sheet=sheet,
            range_ref=range_ref,
            formula_template=formula_template
        )
        
        # Get sample formulas
        start_cell, end_cell = parse_range(range_ref)
        start_row, start_col = get_cell_coordinates(start_cell)
        end_row, end_col = get_cell_coordinates(end_cell)
        
        ws = agent.get_sheet(sheet)
        sample_formulas = {}
        
        # Sample first, middle, and last
        if start_row == end_row and start_col == end_col:
            # Single cell
            sample_formulas[start_cell] = ws[start_cell].value
        else:
            sample_formulas[start_cell] = ws[start_cell].value
            sample_formulas[end_cell] = ws[end_cell].value
        
        agent.save()
    
    return {
        "status": "success",
        "file": str(filepath),
        "sheet": sheet,
        "range": range_ref,
        "cells_modified": cells_modified,
        "formula_template": formula_template,
        "sample_formulas": sample_formulas
    }


def main():
    parser = argparse.ArgumentParser(
        description="Apply formula to Excel range with auto-adjustment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Formula Templates:
  Use placeholders that will be replaced for each cell:
  - {row}  : Current row number
  - {col}  : Current column letter
  - {cell} : Current cell reference (e.g., B5)

Examples:
  # Apply growth formula to column
  uv python excel_apply_range_formula.py --file model.xlsx --sheet Forecast --range B2:B10 --formula "=A{row}*(1+$C$1)" --json
  
  # Percentage of total
  uv python excel_apply_range_formula.py --file model.xlsx --sheet Analysis --range D2:D20 --formula "=C{row}/C$21" --json
  
  # Year-over-year growth
  uv python excel_apply_range_formula.py --file model.xlsx --sheet Data --range C2:C50 --formula "=(B{row}-A{row})/A{row}" --json
  
  # Column sum references
  uv python excel_apply_range_formula.py --file model.xlsx --sheet Summary --range A10:Z10 --formula "=SUM({col}2:{col}9)" --json

Output:
  {
    "status": "success",
    "cells_modified": 9,
    "range": "B2:B10",
    "sample_formulas": {
      "B2": "=A2*(1+$C$1)",
      "B10": "=A10*(1+$C$1)"
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
        '--sheet',
        required=True,
        help='Sheet name'
    )
    
    parser.add_argument(
        '--range',
        required=True,
        help='Target range (e.g., B2:B10, A1:C5)'
    )
    
    parser.add_argument(
        '--formula',
        required=True,
        help='Formula template with {row}, {col}, or {cell} placeholders'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON response'
    )
    
    args = parser.parse_args()
    
    try:
        result = apply_range_formula(
            filepath=args.file,
            sheet=args.sheet,
            range_ref=args.range,
            formula_template=args.formula
        )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Applied formula to {result['cells_modified']} cells in {args.range}")
            print(f"   Template: {args.formula}")
            print(f"   Sample: {list(result['sample_formulas'].values())[0]}")
        
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
```

---

## **File 11/20: `tools/excel_format_range.py`**

```python
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
```

---

## **File 12/20: `tools/excel_add_sheet.py`**

```python
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
```

---

## **File 13/20: `tools/excel_export_sheet.py`**

```python
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
```

---

## **File 14/20: `tools/excel_validate_formulas.py`**

```python
#!/usr/bin/env python3
"""
Excel Validate Formulas Tool
Validate all formulas in workbook for errors

Usage:
    uv python excel_validate_formulas.py --file model.xlsx --method auto --detailed --json

Exit Codes:
    0: Success (no errors)
    1: Validation failed (errors found)
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.excel_agent_core import validate_workbook, ValidationReport


def validate_formulas(
    filepath: Path,
    method: str,
    timeout: int,
    detailed: bool
) -> Dict[str, Any]:
    """Validate workbook formulas."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    # Run validation
    report = validate_workbook(filepath, method=method, timeout=timeout)
    
    # Convert to dict
    result = report.to_dict()
    result["file"] = str(filepath)
    
    if not detailed:
        # Remove detailed locations for brevity
        for error_type, details in result.get("error_summary", {}).items():
            if isinstance(details, dict) and "locations" in details:
                details["locations"] = details["locations"][:5]  # First 5 only
                if len(details["locations"]) < details.get("count", 0):
                    details["truncated"] = True
    
    # Add summary message
    if report.has_errors():
        error_rate = (report.total_errors / report.total_formulas * 100) if report.total_formulas > 0 else 0
        result["summary"] = f"{report.total_errors} errors found in {report.total_formulas} formulas ({error_rate:.1f}% error rate)"
    else:
        result["summary"] = f"All {report.total_formulas} formulas validated successfully"
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Validate Excel workbook formulas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Validation Methods:
  - auto        : Use LibreOffice if available, fallback to Python
  - libreoffice : Use LibreOffice for full recalculation (requires LibreOffice installed)
  - python      : Use Python fallback (checks cached values only)

Examples:
  # Auto-detect best method
  uv python excel_validate_formulas.py --file model.xlsx --json
  
  # Use specific method with detailed output
  uv python excel_validate_formulas.py --file model.xlsx --method python --detailed --json
  
  # Quick validation with timeout
  uv python excel_validate_formulas.py --file large_model.xlsx --method auto --timeout 60 --json

Output:
  {
    "status": "errors_found",
    "total_formulas": 156,
    "total_errors": 3,
    "validation_method": "python_fallback",
    "errors": {
      "#DIV/0!": {
        "count": 2,
        "locations": ["Sheet1!B5", "Sheet1!C10"]
      },
      "#REF!": {
        "count": 1,
        "locations": ["Sheet2!A1"]
      }
    },
    "summary": "3 errors found in 156 formulas (1.9% error rate)"
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
        '--method',
        choices=['auto', 'libreoffice', 'python'],
        default='auto',
        help='Validation method (default: auto)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Timeout in seconds (default: 30)'
    )
    
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Include all error locations (not just first 5)'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        default=True,
        help='Output JSON response (default: true)'
    )
    
    args = parser.parse_args()
    
    try:
        result = validate_formulas(
            filepath=args.file,
            method=args.method,
            timeout=args.timeout,
            detailed=args.detailed
        )
        
        print(json.dumps(result, indent=2))
        
        # Exit code 0 if no errors, 1 if errors found
        if result["status"] == "success":
            sys.exit(0)
        else:
            sys.exit(1)
        
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
```

---

## **File 15/20: `tools/excel_repair_errors.py`**

```python
#!/usr/bin/env python3
"""
Excel Repair Errors Tool
Automatically repair formula errors

Usage:
    uv python excel_repair_errors.py --file model.xlsx --validate-first --backup --json

Exit Codes:
    0: Success (all errors repaired)
    1: Partial success (some errors remain)
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.excel_agent_core import (
    validate_workbook, repair_errors, ValidationReport
)


def repair_workbook_errors(
    filepath: Path,
    validate_first: bool,
    backup: bool,
    error_types: list,
    dry_run: bool
) -> Dict[str, Any]:
    """Repair workbook errors."""
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    result = {
        "file": str(filepath),
        "dry_run": dry_run
    }
    
    # Validate first if requested
    if validate_first:
        pre_validation = validate_workbook(filepath)
        result["pre_validation"] = pre_validation.to_dict()
        
        if not pre_validation.has_errors():
            result["status"] = "success"
            result["message"] = "No errors found, no repairs needed"
            return result
    
    if dry_run:
        result["status"] = "dry_run"
        result["message"] = "Dry run - no changes made"
        if validate_first:
            result["errors_that_would_be_repaired"] = pre_validation.total_errors
        return result
    
    # Perform repairs
    repair_result = repair_errors(
        filepath=filepath,
        error_types=error_types,
        backup=backup
    )
    
    result.update(repair_result)
    
    # Re-validate after repair
    post_validation = validate_workbook(filepath)
    result["post_validation"] = post_validation.to_dict()
    
    # Determine final status
    if post_validation.total_errors == 0:
        result["status"] = "success"
        result["message"] = f"All errors repaired successfully"
    else:
        result["status"] = "partial_success"
        result["remaining_errors"] = post_validation.total_errors
        result["message"] = f"{result['repairs_successful']} repairs made, {post_validation.total_errors} errors remain"
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Automatically repair Excel formula errors",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Repair Methods:
  #DIV/0! : Wrap formula in IFERROR(..., 0)
  #REF!   : Add comment flagging manual review needed
  #VALUE! : Flag in report (no automatic repair)
  #NAME?  : Flag in report (no automatic repair)

Examples:
  # Repair all errors with backup
  uv python excel_repair_errors.py --file model.xlsx --validate-first --backup --json
  
  # Repair specific error types only
  uv python excel_repair_errors.py --file model.xlsx --error-types "#DIV/0!" --backup --json
  
  # Dry run to see what would be repaired
  uv python excel_repair_errors.py --file model.xlsx --validate-first --dry-run --json
  
  # Quick repair without validation
  uv python excel_repair_errors.py --file model.xlsx --json

Output:
  {
    "status": "success",
    "file": "model.xlsx",
    "repairs_attempted": 3,
    "repairs_successful": 2,
    "repairs_failed": 1,
    "remaining_errors": 0,
    "backup_file": "model_backup_20240115_143022.xlsx",
    "details": {
      "#DIV/0!": {
        "attempted": 2,
        "successful": 2,
        "method": "IFERROR wrapper"
      }
    },
    "post_validation": {...}
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
        '--validate-first',
        action='store_true',
        default=True,
        help='Run validation before repair (default: true)'
    )
    
    parser.add_argument(
        '--no-validate-first',
        dest='validate_first',
        action='store_false',
        help='Skip pre-repair validation'
    )
    
    parser.add_argument(
        '--backup',
        action='store_true',
        default=True,
        help='Create backup before repair (default: true)'
    )
    
    parser.add_argument(
        '--no-backup',
        dest='backup',
        action='store_false',
        help='Skip backup creation (DANGEROUS)'
    )
    
    parser.add_argument(
        '--error-types',
        help='Comma-separated error types to repair (default: all)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be repaired without making changes'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        default=True,
        help='Output JSON response (default: true)'
    )
    
    args = parser.parse_args()
    
    try:
        # Parse error types
        error_types = None
        if args.error_types:
            error_types = [e.strip() for e in args.error_types.split(',')]
        
        result = repair_workbook_errors(
            filepath=args.file,
            validate_first=args.validate_first,
            backup=args.backup,
            error_types=error_types,
            dry_run=args.dry_run
        )
        
        print(json.dumps(result, indent=2))
        
        # Exit code based on result
        if result["status"] == "success" or result["status"] == "dry_run":
            sys.exit(0)
        else:
            sys.exit(1)
        
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
```

---

## **File 16/20: `tools/excel_get_info.py`**

```python
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
```

