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
