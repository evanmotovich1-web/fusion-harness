#!/usr/bin/env python3
"""
Excel Agent Tool - Integration Test Suite

Comprehensive tests for all tools without requiring LibreOffice.
Run with: pytest test_tools.py -v
"""

import pytest
import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List


# ============================================================================
# TEST UTILITIES
# ============================================================================

class ToolRunner:
    """Helper class for running tools and parsing JSON responses."""
    
    def __init__(self, tools_dir: Path):
        self.tools_dir = tools_dir
    
    def run(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Run tool and return parsed JSON response."""
        cmd = ['python', str(self.tools_dir / tool_name), '--json']
        
        for key, value in args.items():
            if isinstance(value, bool):
                if value:
                    cmd.append(f'--{key}')
            else:
                cmd.extend([f'--{key}', str(value)])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.tools_dir.parent
        )
        
        try:
            return {
                'returncode': result.returncode,
                'data': json.loads(result.stdout) if result.stdout else {},
                'stderr': result.stderr
            }
        except json.JSONDecodeError:
            return {
                'returncode': result.returncode,
                'data': {},
                'stderr': result.stderr,
                'stdout': result.stdout
            }


@pytest.fixture
def tools_dir():
    """Get tools directory path."""
    return Path(__file__).parent / 'tools'


@pytest.fixture
def runner(tools_dir):
    """Get ToolRunner instance."""
    return ToolRunner(tools_dir)


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path, ignore_errors=True)


# ============================================================================
# CREATION TOOLS TESTS
# ============================================================================

class TestCreationTools:
    """Test workbook creation tools."""
    
    def test_create_new_basic(self, runner, temp_dir):
        """Test basic workbook creation."""
        output = temp_dir / 'test.xlsx'
        
        result = runner.run('excel_create_new.py', {
            'output': output,
            'sheets': 'Sheet1,Sheet2,Sheet3'
        })
        
        assert result['returncode'] == 0
        assert result['data']['status'] == 'success'
        assert output.exists()
        assert result['data']['sheet_count'] == 3
        assert 'Sheet1' in result['data']['sheets']
    
    def test_create_new_invalid_sheet_names(self, runner, temp_dir):
        """Test creation with invalid sheet names."""
        output = temp_dir / 'test.xlsx'
        
        # Sheet names with invalid characters should be sanitized
        result = runner.run('excel_create_new.py', {
            'output': output,
            'sheets': 'Valid,Invalid:Name,Another/Bad'
        })
        
        # Should succeed with warnings
        assert result['returncode'] == 0
        assert len(result['data'].get('warnings', [])) > 0
    
    def test_create_new_dry_run(self, runner, temp_dir):
        """Test dry run mode."""
        output = temp_dir / 'test.xlsx'
        
        result = runner.run('excel_create_new.py', {
            'output': output,
            'sheets': 'Sheet1',
            'dry-run': True
        })
        
        assert result['returncode'] == 0
        assert result['data']['status'] == 'dry_run'
        assert not output.exists()
    
    def test_create_from_structure_basic(self, runner, temp_dir):
        """Test creation from structure."""
        output = temp_dir / 'model.xlsx'
        structure_file = temp_dir / 'structure.json'
        
        structure = {
            "sheets": ["Sheet1", "Sheet2"],
            "cells": [
                {"sheet": "Sheet1", "cell": "A1", "value": "Header"},
                {"sheet": "Sheet1", "cell": "B2", "formula": "=1+1"}
            ]
        }
        
        structure_file.write_text(json.dumps(structure))
        
        result = runner.run('excel_create_from_structure.py', {
            'output': output,
            'structure': structure_file
        })
        
        assert result['returncode'] == 0
        assert result['data']['status'] == 'success'
        assert output.exists()
        assert result['data']['sheets_created'] == 2
    
    def test_create_from_structure_with_inputs(self, runner, temp_dir):
        """Test creation with financial inputs."""
        output = temp_dir / 'model.xlsx'
        structure_file = temp_dir / 'structure.json'
        
        structure = {
            "sheets": ["Assumptions"],
            "inputs": [
                {
                    "sheet": "Assumptions",
                    "cell": "B2",
                    "value": 0.15,
                    "comment": "Growth rate"
                }
            ],
            "assumptions": [
                {
                    "sheet": "Assumptions",
                    "cell": "B3",
                    "value": 1000000,
                    "description": "Revenue baseline"
                }
            ]
        }
        
        structure_file.write_text(json.dumps(structure))
        
        result = runner.run('excel_create_from_structure.py', {
            'output': output,
            'structure': structure_file
        })
        
        assert result['returncode'] == 0
        assert result['data']['inputs_added'] == 1
        assert result['data']['assumptions_added'] == 1
    
    def test_clone_template(self, runner, temp_dir):
        """Test template cloning."""
        # First create a source file
        source = temp_dir / 'source.xlsx'
        runner.run('excel_create_new.py', {
            'output': source,
            'sheets': 'Sheet1'
        })
        
        # Clone it
        output = temp_dir / 'clone.xlsx'
        result = runner.run('excel_clone_template.py', {
            'source': source,
            'output': output,
            'preserve-formatting': True
        })
        
        assert result['returncode'] == 0
        assert result['data']['status'] == 'success'
        assert output.exists()


# ============================================================================
# CELL OPERATIONS TESTS
# ============================================================================

class TestCellOperations:
    """Test cell manipulation tools."""
    
    @pytest.fixture
    def sample_file(self, runner, temp_dir):
        """Create sample file for testing."""
        filepath = temp_dir / 'sample.xlsx'
        runner.run('excel_create_new.py', {
            'output': filepath,
            'sheets': 'Sheet1,Assumptions'
        })
        return filepath
    
    def test_set_value_string(self, runner, sample_file):
        """Test setting string value."""
        result = runner.run('excel_set_value.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'cell': 'A1',
            'value': 'Test String',
            'type': 'string'
        })
        
        assert result['returncode'] == 0
        assert result['data']['status'] == 'success'
        assert result['data']['cell'] == 'A1'
    
    def test_set_value_number(self, runner, sample_file):
        """Test setting numeric value."""
        result = runner.run('excel_set_value.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'cell': 'B2',
            'value': '12345',
            'type': 'number'
        })
        
        assert result['returncode'] == 0
        assert result['data']['type'] == 'float'
    
    def test_add_formula_valid(self, runner, sample_file):
        """Test adding valid formula."""
        result = runner.run('excel_add_formula.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'cell': 'C3',
            'formula': '=SUM(A1:A10)'
        })
        
        assert result['returncode'] == 0
        assert result['data']['status'] == 'success'
        assert result['data']['formula'].startswith('=')
    
    def test_add_formula_cross_sheet(self, runner, sample_file):
        """Test cross-sheet formula."""
        result = runner.run('excel_add_formula.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'cell': 'D4',
            'formula': '=Assumptions!B2*2'
        })
        
        assert result['returncode'] == 0
        assert 'Assumptions!B2' in result['data']['formula']
    
    def test_add_formula_invalid_sheet_reference(self, runner, sample_file):
        """Test formula with invalid sheet reference."""
        result = runner.run('excel_add_formula.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'cell': 'E5',
            'formula': '=InvalidSheet!A1'
        })
        
        assert result['returncode'] == 1
        assert 'error' in result['data']
    
    def test_add_formula_security_error(self, runner, sample_file):
        """Test formula security blocking."""
        result = runner.run('excel_add_formula.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'cell': 'F6',
            'formula': '=WEBSERVICE("http://example.com")'
        })
        
        assert result['returncode'] == 2
        assert result['data']['status'] == 'security_error'
    
    def test_add_financial_input(self, runner, sample_file):
        """Test adding financial input."""
        result = runner.run('excel_add_financial_input.py', {
            'file': sample_file,
            'sheet': 'Assumptions',
            'cell': 'B2',
            'value': 0.15,
            'comment': 'Growth rate - Source: 10-K',
            'format': 'percent'
        })
        
        assert result['returncode'] == 0
        assert result['data']['status'] == 'success'
        assert result['data']['value'] == 0.15
    
    def test_add_assumption(self, runner, sample_file):
        """Test adding assumption."""
        result = runner.run('excel_add_assumption.py', {
            'file': sample_file,
            'sheet': 'Assumptions',
            'cell': 'B3',
            'value': 1000000,
            'description': 'Revenue baseline',
            'format': 'currency',
            'decimals': 0
        })
        
        assert result['returncode'] == 0
        assert result['data']['status'] == 'success'
    
    def test_get_value(self, runner, sample_file):
        """Test reading cell value."""
        # First set a value
        runner.run('excel_set_value.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'cell': 'A1',
            'value': 'Test',
            'type': 'string'
        })
        
        # Then read it
        result = runner.run('excel_get_value.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'cell': 'A1'
        })
        
        assert result['returncode'] == 0
        assert result['data']['value'] == 'Test'
    
    def test_get_value_formula(self, runner, sample_file):
        """Test reading formula."""
        # Add formula
        runner.run('excel_add_formula.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'cell': 'B1',
            'formula': '=SUM(A1:A10)'
        })
        
        # Read it
        result = runner.run('excel_get_value.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'cell': 'B1',
            'get-both': True
        })
        
        assert result['returncode'] == 0
        assert result['data']['is_formula'] == True
        assert 'SUM' in result['data']['formula']


# ============================================================================
# RANGE OPERATIONS TESTS
# ============================================================================

class TestRangeOperations:
    """Test range manipulation tools."""
    
    @pytest.fixture
    def sample_file(self, runner, temp_dir):
        """Create sample file."""
        filepath = temp_dir / 'sample.xlsx'
        runner.run('excel_create_new.py', {
            'output': filepath,
            'sheets': 'Sheet1'
        })
        return filepath
    
    def test_apply_range_formula(self, runner, sample_file):
        """Test applying formula to range."""
        result = runner.run('excel_apply_range_formula.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'range': 'B2:B10',
            'formula': '=A{row}*2'
        })
        
        assert result['returncode'] == 0
        assert result['data']['cells_modified'] == 9
        assert 'sample_formulas' in result['data']
    
    def test_format_range_currency(self, runner, sample_file):
        """Test formatting range as currency."""
        result = runner.run('excel_format_range.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'range': 'C2:C10',
            'format': 'currency',
            'decimals': 0
        })
        
        assert result['returncode'] == 0
        assert result['data']['cells_formatted'] == 9
    
    def test_format_range_custom(self, runner, sample_file):
        """Test custom format."""
        result = runner.run('excel_format_range.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'range': 'D1:D5',
            'custom-format': '#,##0.00'
        })
        
        assert result['returncode'] == 0
        assert result['data']['format_type'] == 'custom'


# ============================================================================
# SHEET MANAGEMENT TESTS
# ============================================================================

class TestSheetManagement:
    """Test sheet manipulation tools."""
    
    @pytest.fixture
    def sample_file(self, runner, temp_dir):
        """Create sample file."""
        filepath = temp_dir / 'sample.xlsx'
        runner.run('excel_create_new.py', {
            'output': filepath,
            'sheets': 'Sheet1'
        })
        return filepath
    
    def test_add_sheet(self, runner, sample_file):
        """Test adding new sheet."""
        result = runner.run('excel_add_sheet.py', {
            'file': sample_file,
            'sheet': 'NewSheet'
        })
        
        assert result['returncode'] == 0
        assert 'NewSheet' in result['data']['all_sheets']
    
    def test_add_sheet_at_index(self, runner, sample_file):
        """Test adding sheet at specific position."""
        result = runner.run('excel_add_sheet.py', {
            'file': sample_file,
            'sheet': 'FirstSheet',
            'index': 0
        })
        
        assert result['returncode'] == 0
        assert result['data']['index'] == 0
    
    def test_export_sheet_csv(self, runner, sample_file, temp_dir):
        """Test exporting to CSV."""
        # Add some data first
        runner.run('excel_set_value.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'cell': 'A1',
            'value': 'Header',
            'type': 'string'
        })
        
        output = temp_dir / 'export.csv'
        result = runner.run('excel_export_sheet.py', {
            'file': sample_file,
            'sheet': 'Sheet1',
            'output': output,
            'format': 'csv'
        })
        
        assert result['returncode'] == 0
        assert output.exists()
        assert result['data']['format'] == 'csv'


# ============================================================================
# VALIDATION & QUALITY TESTS
# ============================================================================

class TestValidationTools:
    """Test validation and repair tools."""
    
    @pytest.fixture
    def model_with_formulas(self, runner, temp_dir):
        """Create model with some formulas."""
        filepath = temp_dir / 'model.xlsx'
        
        structure = {
            "sheets": ["Sheet1"],
            "cells": [
                {"sheet": "Sheet1", "cell": "A1", "value": 10},
                {"sheet": "Sheet1", "cell": "A2", "value": 20},
                {"sheet": "Sheet1", "cell": "B1", "formula": "=SUM(A1:A2)"}
            ]
        }
        
        structure_file = temp_dir / 'structure.json'
        structure_file.write_text(json.dumps(structure))
        
        runner.run('excel_create_from_structure.py', {
            'output': filepath,
            'structure': structure_file
        })
        
        return filepath
    
    def test_validate_formulas_success(self, runner, model_with_formulas):
        """Test validation of valid formulas."""
        result = runner.run('excel_validate_formulas.py', {
            'file': model_with_formulas,
            'method': 'python'
        })
        
        assert result['returncode'] == 0
        assert result['data']['total_formulas'] >= 1
    
    def test_get_info(self, runner, model_with_formulas):
        """Test getting workbook info."""
        result = runner.run('excel_get_info.py', {
            'file': model_with_formulas,
            'detailed': True,
            'include-sheets': True
        })
        
        assert result['returncode'] == 0
        assert result['data']['status'] == 'success'
        assert 'sheets' in result['data']
        assert result['data']['sheet_count'] >= 1
    
    def test_repair_dry_run(self, runner, model_with_formulas):
        """Test repair in dry-run mode."""
        result = runner.run('excel_repair_errors.py', {
            'file': model_with_formulas,
            'dry-run': True
        })
        
        assert result['returncode'] == 0
        assert result['data']['dry_run'] == True


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_file_not_found(self, runner, temp_dir):
        """Test handling of missing file."""
        result = runner.run('excel_get_info.py', {
            'file': temp_dir / 'nonexistent.xlsx'
        })
        
        assert result['returncode'] == 1
        assert result['data']['status'] == 'error'
        assert 'not found' in result['data']['error'].lower()
    
    def test_invalid_sheet_name(self, runner, temp_dir):
        """Test handling of invalid sheet reference."""
        filepath = temp_dir / 'test.xlsx'
        runner.run('excel_create_new.py', {
            'output': filepath,
            'sheets': 'Sheet1'
        })
        
        result = runner.run('excel_set_value.py', {
            'file': filepath,
            'sheet': 'InvalidSheet',
            'cell': 'A1',
            'value': 'test',
            'type': 'string'
        })
        
        assert result['returncode'] == 1
        assert 'not found' in result['data']['error'].lower()
    
    def test_invalid_cell_reference(self, runner, temp_dir):
        """Test handling of invalid cell reference."""
        filepath = temp_dir / 'test.xlsx'
        runner.run('excel_create_new.py', {
            'output': filepath,
            'sheets': 'Sheet1'
        })
        
        result = runner.run('excel_set_value.py', {
            'file': filepath,
            'sheet': 'Sheet1',
            'cell': 'INVALID',
            'value': 'test',
            'type': 'string'
        })
        
        assert result['returncode'] == 1


# ============================================================================
# INTEGRATION WORKFLOW TESTS
# ============================================================================

class TestWorkflows:
    """Test complete workflows."""
    
    def test_create_financial_model_workflow(self, runner, temp_dir):
        """Test complete financial model creation workflow."""
        filepath = temp_dir / 'financial_model.xlsx'
        
        # Step 1: Create workbook
        result = runner.run('excel_create_new.py', {
            'output': filepath,
            'sheets': 'Assumptions,Income Statement'
        })
        assert result['returncode'] == 0
        
        # Step 2: Add assumption
        result = runner.run('excel_add_assumption.py', {
            'file': filepath,
            'sheet': 'Assumptions',
            'cell': 'B2',
            'value': 1000000,
            'description': 'Revenue baseline',
            'format': 'currency',
            'decimals': 0
        })
        assert result['returncode'] == 0
        
        # Step 3: Add formula
        result = runner.run('excel_add_formula.py', {
            'file': filepath,
            'sheet': 'Income Statement',
            'cell': 'B5',
            'formula': '=Assumptions!B2*1.15'
        })
        assert result['returncode'] == 0
        
        # Step 4: Format range
        result = runner.run('excel_format_range.py', {
            'file': filepath,
            'sheet': 'Income Statement',
            'range': 'B5:B10',
            'format': 'currency',
            'decimals': 0
        })
        assert result['returncode'] == 0
        
        # Step 5: Validate
        result = runner.run('excel_validate_formulas.py', {
            'file': filepath,
            'method': 'python'
        })
        assert result['returncode'] == 0
        
        # Step 6: Get info
        result = runner.run('excel_get_info.py', {
            'file': filepath,
            'detailed': True
        })
        assert result['returncode'] == 0
        assert result['data']['sheet_count'] == 2


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Test performance with various file sizes."""
    
    def test_large_range_formula(self, runner, temp_dir):
        """Test applying formula to large range."""
        filepath = temp_dir / 'large.xlsx'
        
        runner.run('excel_create_new.py', {
            'output': filepath,
            'sheets': 'Sheet1'
        })
        
        # Apply formula to 100 cells
        import time
        start = time.time()
        
        result = runner.run('excel_apply_range_formula.py', {
            'file': filepath,
            'sheet': 'Sheet1',
            'range': 'A1:A100',
            'formula': '={row}*2'
        })
        
        elapsed = time.time() - start
        
        assert result['returncode'] == 0
        assert result['data']['cells_modified'] == 100
        assert elapsed < 5.0  # Should complete in under 5 seconds


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
