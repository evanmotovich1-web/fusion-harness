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
