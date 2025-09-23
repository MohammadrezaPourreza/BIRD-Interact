#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BIRD-Interact Semantic SQL Equivalence Checker

This utility allows you to check if two SQL queries are semantically equivalent
by comparing their result sets using the same evaluation logic as BIRD-Interact.

Usage Examples:
    # Basic usage
    is_equivalent = check_sql_equivalence(
        predicted_sql="SELECT name FROM users WHERE age > 25",
        ground_truth_sql="SELECT name FROM users WHERE age > 25 ORDER BY name",
        db_name="test_db"
    )
    
    # With order sensitivity
    is_equivalent = check_sql_equivalence(
        predicted_sql=["SELECT * FROM products ORDER BY price"],
        ground_truth_sql=["SELECT * FROM products ORDER BY price DESC"], 
        db_name="ecommerce_db",
        check_order=True
    )
    
    # Batch evaluation
    results = batch_check_equivalence([
        {"pred": "SELECT COUNT(*) FROM orders", "gt": "SELECT COUNT(id) FROM orders", "db": "shop"},
        {"pred": "SELECT DISTINCT category FROM products", "gt": "SELECT category FROM products GROUP BY category", "db": "shop"}
    ])
"""

import sys
import os
import logging
from typing import List, Dict, Union, Tuple, Optional

# Add the evaluation source directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
eval_src_dir = os.path.join(current_dir, '..', '..', 'evaluation', 'src')
sys.path.append(eval_src_dir)

try:
    from eval_bird_interact import test_case_default, ex_base, preprocess_results
    from postgresql_utils import execute_queries, get_connection_for_phase, reset_and_restore_database
except ImportError as e:
    print(f"❌ Error importing evaluation modules: {e}")
    print("Make sure you're running this from the BIRD-Interact project directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class SQLEquivalenceChecker:
    """
    A utility class for checking semantic equivalence between SQL queries.
    """
    
    def __init__(self, pg_password: str = "123123"):
        """
        Initialize the SQL equivalence checker.
        
        Args:
            pg_password: PostgreSQL password for database operations
        """
        self.pg_password = pg_password
        self._connections = {}
    
    def _get_connection(self, db_name: str):
        """Get or create a database connection."""
        if db_name not in self._connections:
            try:
                self._connections[db_name] = get_connection_for_phase(db_name)
                logger.info(f"✅ Connected to database: {db_name}")
            except Exception as e:
                logger.error(f"❌ Failed to connect to database {db_name}: {e}")
                raise
        return self._connections[db_name]
    
    def _ensure_list(self, sql_input: Union[str, List[str]]) -> List[str]:
        """Convert SQL input to list format."""
        if isinstance(sql_input, str):
            return [sql_input.strip()]
        elif isinstance(sql_input, list):
            return [sql.strip() for sql in sql_input if sql.strip()]
        else:
            raise ValueError("SQL input must be string or list of strings")
    
    def check_equivalence(
        self, 
        predicted_sql: Union[str, List[str]], 
        ground_truth_sql: Union[str, List[str]], 
        db_name: str,
        check_order: bool = False,
        reset_db: bool = True,
        verbose: bool = False
    ) -> Dict[str, any]:
        """
        Check if two SQL queries are semantically equivalent.
        
        Args:
            predicted_sql: The predicted SQL query(ies)
            ground_truth_sql: The ground truth SQL query(ies) 
            db_name: Database name to execute queries against
            check_order: Whether order of results matters (default: False)
            reset_db: Whether to reset database before evaluation (default: True)
            verbose: Whether to print detailed information (default: False)
            
        Returns:
            Dict with keys:
                - 'equivalent': bool - Whether queries are equivalent
                - 'predicted_result': Results from predicted query
                - 'ground_truth_result': Results from ground truth query
                - 'error': str or None - Error message if any
                - 'execution_info': Dict with execution details
        """
        
        result = {
            'equivalent': False,
            'predicted_result': None,
            'ground_truth_result': None,
            'error': None,
            'execution_info': {}
        }
        
        try:
            # Convert inputs to lists
            pred_sqls = self._ensure_list(predicted_sql)
            gt_sqls = self._ensure_list(ground_truth_sql)
            
            if verbose:
                print(f"🔍 Checking SQL equivalence on database: {db_name}")
                print(f"📝 Predicted SQL: {pred_sqls}")
                print(f"📝 Ground Truth SQL: {gt_sqls}")
                print(f"🔢 Order sensitive: {check_order}")
            
            # Reset database if requested
            if reset_db:
                if verbose:
                    print("🔄 Resetting database...")
                reset_and_restore_database(db_name, self.pg_password)
            
            # Get database connection
            conn = self._get_connection(db_name)
            
            # Execute predicted SQL
            if verbose:
                print("▶️ Executing predicted SQL...")
            pred_result, pred_err, pred_timeout = execute_queries(pred_sqls, db_name, conn)
            
            if pred_err or pred_timeout:
                result['error'] = f"Predicted SQL execution failed: {'timeout' if pred_timeout else 'error'}"
                return result
            
            # Execute ground truth SQL
            if verbose:
                print("▶️ Executing ground truth SQL...")
            gt_result, gt_err, gt_timeout = execute_queries(gt_sqls, db_name, conn)
            
            if gt_err or gt_timeout:
                result['error'] = f"Ground truth SQL execution failed: {'timeout' if gt_timeout else 'error'}"
                return result
            
            # Store raw results
            result['predicted_result'] = pred_result
            result['ground_truth_result'] = gt_result
            
            # Normalize results for comparison
            normalized_pred = preprocess_results(pred_result) if pred_result else []
            normalized_gt = preprocess_results(gt_result) if gt_result else []
            
            if verbose:
                print(f"📊 Predicted result: {len(normalized_pred)} rows")
                print(f"📊 Ground truth result: {len(normalized_gt)} rows")
            
            # Compare results
            if check_order:
                # Order matters - compare as lists
                equivalent = normalized_pred == normalized_gt
            else:
                # Order doesn't matter - compare as sets
                equivalent = set(normalized_pred) == set(normalized_gt)
            
            result['equivalent'] = equivalent
            result['execution_info'] = {
                'predicted_rows': len(normalized_pred),
                'ground_truth_rows': len(normalized_gt),
                'order_sensitive': check_order
            }
            
            if verbose:
                print(f"✅ Result: {'EQUIVALENT' if equivalent else 'NOT EQUIVALENT'}")
            
            return result
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Error during equivalence check: {e}")
            return result
    
    def batch_check_equivalence(
        self, 
        test_cases: List[Dict], 
        verbose: bool = False
    ) -> List[Dict]:
        """
        Check equivalence for multiple SQL query pairs.
        
        Args:
            test_cases: List of dicts with keys 'predicted', 'ground_truth', 'db_name'
            verbose: Whether to print progress information
            
        Returns:
            List of results from check_equivalence for each test case
        """
        
        results = []
        total_cases = len(test_cases)
        
        if verbose:
            print(f"🚀 Starting batch evaluation of {total_cases} test cases")
        
        for i, test_case in enumerate(test_cases, 1):
            if verbose:
                print(f"\n📋 Test Case {i}/{total_cases}")
            
            try:
                result = self.check_equivalence(
                    predicted_sql=test_case.get('predicted', ''),
                    ground_truth_sql=test_case.get('ground_truth', ''),
                    db_name=test_case.get('db_name', ''),
                    check_order=test_case.get('check_order', False),
                    reset_db=test_case.get('reset_db', True),
                    verbose=verbose
                )
                
                # Add test case metadata
                result['test_case_id'] = i
                result['test_case'] = test_case
                results.append(result)
                
            except Exception as e:
                error_result = {
                    'test_case_id': i,
                    'test_case': test_case,
                    'equivalent': False,
                    'error': str(e),
                    'predicted_result': None,
                    'ground_truth_result': None,
                    'execution_info': {}
                }
                results.append(error_result)
                if verbose:
                    print(f"❌ Test case {i} failed: {e}")
        
        # Summary
        if verbose:
            equivalent_count = sum(1 for r in results if r['equivalent'])
            success_rate = (equivalent_count / total_cases) * 100
            print(f"\n📈 Batch Evaluation Summary:")
            print(f"   Total test cases: {total_cases}")
            print(f"   Equivalent: {equivalent_count}")
            print(f"   Success rate: {success_rate:.2f}%")
        
        return results
    
    def close_connections(self):
        """Close all database connections."""
        for db_name, conn in self._connections.items():
            try:
                conn.close()
                logger.info(f"Closed connection to {db_name}")
            except Exception as e:
                logger.warning(f"Error closing connection to {db_name}: {e}")
        self._connections.clear()


# Convenience functions for direct usage
def check_sql_equivalence(
    predicted_sql: Union[str, List[str]], 
    ground_truth_sql: Union[str, List[str]], 
    db_name: str,
    check_order: bool = False,
    reset_db: bool = True,
    verbose: bool = False,
    pg_password: str = "123123"
) -> bool:
    """
    Quick function to check SQL equivalence. Returns True if equivalent, False otherwise.
    
    Example:
        equivalent = check_sql_equivalence(
            "SELECT name FROM users WHERE age > 25",
            "SELECT name FROM users WHERE age > 25 ORDER BY id", 
            "test_db"
        )
    """
    
    checker = SQLEquivalenceChecker(pg_password)
    try:
        result = checker.check_equivalence(
            predicted_sql, ground_truth_sql, db_name, 
            check_order, reset_db, verbose
        )
        return result['equivalent']
    finally:
        checker.close_connections()


def detailed_sql_equivalence(
    predicted_sql: Union[str, List[str]], 
    ground_truth_sql: Union[str, List[str]], 
    db_name: str,
    check_order: bool = False,
    reset_db: bool = True,
    verbose: bool = True,
    pg_password: str = "123123"
) -> Dict:
    """
    Detailed function to check SQL equivalence with full result information.
    
    Example:
        result = detailed_sql_equivalence(
            "SELECT COUNT(*) FROM orders",
            "SELECT COUNT(id) FROM orders", 
            "shop_db"
        )
        print(f"Equivalent: {result['equivalent']}")
        print(f"Predicted result: {result['predicted_result']}")
    """
    
    checker = SQLEquivalenceChecker(pg_password)
    try:
        return checker.check_equivalence(
            predicted_sql, ground_truth_sql, db_name, 
            check_order, reset_db, verbose
        )
    finally:
        checker.close_connections()


if __name__ == "__main__":
    # Example usage and testing
    print("🧪 SQL Equivalence Checker - Test Examples")
    print("=" * 50)
    
    # Example 1: Basic equivalence check
    print("\n1️⃣ Basic Equivalence Check:")
    try:
        equivalent = check_sql_equivalence(
            predicted_sql="SELECT 1 as test_col",
            ground_truth_sql="SELECT 1 as test_col",
            db_name="test_db"  # Replace with actual database name
        )
        print(f"   Result: {'✅ EQUIVALENT' if equivalent else '❌ NOT EQUIVALENT'}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Example 2: Detailed check with different queries
    print("\n2️⃣ Detailed Check:")
    try:
        result = detailed_sql_equivalence(
            predicted_sql="SELECT COUNT(*) FROM dual",
            ground_truth_sql="SELECT 1", 
            db_name="test_db",  # Replace with actual database name
            verbose=False
        )
        print(f"   Equivalent: {result['equivalent']}")
        if result['error']:
            print(f"   Error: {result['error']}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n🎯 Use these functions in your code to check SQL semantic equivalence!")
