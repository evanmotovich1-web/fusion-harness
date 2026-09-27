#!/usr/bin/env python3
"""
Excel Create From Structure Tool
Create Excel workbook from JSON structure definition

Usage:
    uv python excel_create_from_structure.py --output model.xlsx --structure structure.json --validate --json

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
    create_workbook_from_structure, ExcelAgentError, validate_workbook
)


def validate_structure(structure: Dict[str, Any]) -> None:
    """Validate structure dictionary schema."""
    
    # Check required keys
    if "sheets" not in structure or not structure["sheets"]:
        raise ValueError("Structure must contain 'sheets' key with at least one sheet")
    
    if not isinstance(structure["sheets"], list):
        raise ValueError("'sheets' must be a list")
    
    # Validate cells
    for cell_def in structure.get("cells", []):
        if "sheet" not in cell_def or "cell" not in cell_def:
            raise ValueError("Each cell definition must have 'sheet' and 'cell' keys")
        
        if "value" not in cell_def and "formula" not in cell_def:
            raise ValueError("Each cell definition must have either 'value' or 'formula'")
    
    # Validate inputs
    for input_def in structure.get("inputs", []):
        required = ["sheet", "cell", "value"]
        if not all(k in input_def for k in required):
            raise ValueError(f"Input definition must have: {required}")
    
    # Validate assumptions
    for assumption_def in structure.get("assumptions", []):
        required = ["sheet", "cell", "value", "description"]
        if not all(k in assumption_def for k in required):
            raise ValueError(f"Assumption definition must have: {required}")


def main():
    parser = argparse.ArgumentParser(
        description="Create Excel workbook from JSON structure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Structure JSON Format:
{
  "sheets": ["Sheet1", "Sheet2"],
  "cells": [
    {"sheet": "Sheet1", "cell": "A1", "value": "Header"},
    {"sheet": "Sheet1", "cell": "B2", "formula": "=SUM(B3:B10)"}
  ],
  "inputs": [
    {"sheet": "Assumptions", "cell": "B2", "value": 0.05, "comment": "Growth rate", "number_format": "0.0%"}
  ],
  "assumptions": [
    {"sheet": "Assumptions", "cell": "B3", "value": 1000000, "description": "Base revenue"}
  ]
}

Examples:
  # Create from file
  uv python excel_create_from_structure.py --output model.xlsx --structure structure.json --json
  
  # Create from inline JSON
  uv python excel_create_from_structure.py --output model.xlsx --structure-string '{"sheets":["Data"]}' --json
  
  # Create and validate
  uv python excel_create_from_structure.py --output model.xlsx --structure structure.json --validate --json
        """
    )
    
    parser.add_argument(
        '--output',
        required=True,
        type=Path,
        help='Output Excel file path'
    )
    
    parser.add_argument(
        '--structure',
        type=Path,
        help='JSON file with structure definition'
    )
    
    parser.add_argument(
        '--structure-string',
        help='Inline JSON structure string'
    )
    
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate formulas after creation'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON response'
    )
    
    args = parser.parse_args()
    
    try:
        # Load structure
        if args.structure:
            if not args.structure.exists():
                raise FileNotFoundError(f"Structure file not found: {args.structure}")
            with open(args.structure, 'r') as f:
                structure = json.load(f)
        elif args.structure_string:
            structure = json.loads(args.structure_string)
        else:
            raise ValueError("Either --structure or --structure-string required")
        
        # Validate structure
        validate_structure(structure)
        
        # Create workbook
        result = create_workbook_from_structure(
            output=args.output,
            structure=structure,
            validate=args.validate
        )
        
        result["status"] = "success"
        result["file"] = str(args.output)
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Created workbook: {args.output}")
            print(f"   Sheets: {result['sheets_created']}")
            print(f"   Formulas: {result['formulas_added']}")
            print(f"   Inputs: {result['inputs_added']}")
            print(f"   Assumptions: {result['assumptions_added']}")
            
            if args.validate and "validation_result" in result:
                val = result["validation_result"]
                if val.get("status") == "success":
                    print(f"   ✅ Validation passed ({val['total_formulas']} formulas)")
                else:
                    print(f"   ❌ Validation found {val['total_errors']} errors")
        
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
