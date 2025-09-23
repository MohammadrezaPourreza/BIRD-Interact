#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Simple Examples: How to Use BIRD-Interact Evaluation Functions

This script demonstrates how to use the core evaluation functions 
to check if two SQL queries are semantically equivalent.
"""

import sys
import os

# Add evaluation modules to path
current_dir = os.path.dirname(os.path.abspath(__file__))
eval_src_dir = os.path.join(current_dir, '..', '..', 'evaluation', 'src')
sys.path.append(eval_src_dir)

from eval_bird_interact import test_case_default, ex_base
from postgresql_utils import get_connection_for_phase, reset_and_restore_database


def simple_equivalence_check(pred_sql, gt_sql, db_name, reset_db=True):
    """
    Simple function to check if two SQL queries are semantically equivalent.
    
    Args:
        pred_sql (str or list): Predicted SQL query(ies)
        gt_sql (str or list): Ground truth SQL query(ies) 
        db_name (str): Database name to run queries against
        reset_db (bool): Whether to reset database before testing
        
    Returns:
        bool: True if queries are equivalent, False otherwise
    """
    
    # Convert to lists if needed
    if isinstance(pred_sql, str):
        pred_sql = [pred_sql]
    if isinstance(gt_sql, str):
        gt_sql = [gt_sql]
    
    try:
        # Reset database if requested
        if reset_db:
            print(f"🔄 Resetting database {db_name}...")
            reset_and_restore_database(db_name, "123123")  # Default password
        
        # Get database connection
        print(f"🔌 Connecting to database {db_name}...")
        conn = get_connection_for_phase(db_name)
        
        # Use the default test case function (same as BIRD-Interact evaluation)
        print("⚡ Running semantic equivalence check...")
        result = test_case_default(pred_sql, gt_sql, db_name, conn)
        
        # Close connection
        conn.close()
        
        return result == 1
        
    except Exception as e:
        print(f"❌ Error during evaluation: {e}")
        return False


def compare_with_conditions(pred_sql, gt_sql, db_name, check_order=False):
    """
    Compare queries with specific conditions (e.g., order sensitivity).
    
    Args:
        pred_sql: Predicted SQL
        gt_sql: Ground truth SQL
        db_name: Database name
        check_order: Whether order of results matters
        
    Returns:
        bool: True if equivalent according to conditions
    """
    
    if isinstance(pred_sql, str):
        pred_sql = [pred_sql]
    if isinstance(gt_sql, str):
        gt_sql = [gt_sql]
    
    try:
        # Get connection
        conn = get_connection_for_phase(db_name)
        
        # Create conditions dict
        conditions = {"order": check_order} if check_order else None
        
        # Use the base comparison function directly
        result = ex_base(pred_sql, gt_sql, db_name, conn, conditions)
        
        conn.close()
        return result == 1
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


# Example usage
if __name__ == "__main__":
    print("🧪 SQL Semantic Equivalence Examples")
    print("=" * 40)
    
    # Replace 'your_db_name' with actual database name
    DB_NAME = "test_db"  # Change this to your database
    
    print(f"\n📊 Testing against database: {DB_NAME}")
    
    # Example 1: Simple equivalence (ignoring ORDER BY)
    print("\n1️⃣ Simple Equivalence Check:")
    print("   Pred: SELECT name FROM users WHERE age > 25")
    print("   GT:   SELECT name FROM users WHERE age > 25 ORDER BY name")
    
    try:
        is_equivalent = simple_equivalence_check(
            pred_sql="SELECT name FROM users WHERE age > 25",
            gt_sql="SELECT name FROM users WHERE age > 25 ORDER BY name", 
            db_name=DB_NAME
        )
        print(f"   Result: {'✅ EQUIVALENT' if is_equivalent else '❌ NOT EQUIVALENT'}")
    except Exception as e:
        print(f"   ❌ Could not test: {e}")
    
    # Example 2: Different but semantically equivalent queries
    print("\n2️⃣ Semantic Equivalence:")
    print("   Pred: SELECT DISTINCT category FROM products")
    print("   GT:   SELECT category FROM products GROUP BY category")
    
    try:
        is_equivalent = simple_equivalence_check(
            pred_sql="SELECT DISTINCT category FROM products",
            gt_sql="SELECT category FROM products GROUP BY category",
            db_name=DB_NAME
        )
        print(f"   Result: {'✅ EQUIVALENT' if is_equivalent else '❌ NOT EQUIVALENT'}")
    except Exception as e:
        print(f"   ❌ Could not test: {e}")
    
    # Example 3: Order-sensitive comparison
    print("\n3️⃣ Order-Sensitive Comparison:")
    print("   Pred: SELECT * FROM products ORDER BY price ASC")
    print("   GT:   SELECT * FROM products ORDER BY price DESC")
    print("   (Order matters = True)")
    
    try:
        is_equivalent = compare_with_conditions(
            pred_sql="SELECT * FROM products ORDER BY price ASC",
            gt_sql="SELECT * FROM products ORDER BY price DESC",
            db_name=DB_NAME,
            check_order=True
        )
        print(f"   Result: {'✅ EQUIVALENT' if is_equivalent else '❌ NOT EQUIVALENT'}")
    except Exception as e:
        print(f"   ❌ Could not test: {e}")
    
    # Example 4: Count queries
    print("\n4️⃣ Count Equivalence:")
    print("   Pred: SELECT COUNT(*) FROM orders")
    print("   GT:   SELECT COUNT(id) FROM orders")
    
    try:
        is_equivalent = simple_equivalence_check(
            pred_sql="SELECT COUNT(*) FROM orders",
            gt_sql="SELECT COUNT(id) FROM orders",
            db_name=DB_NAME
        )
        print(f"   Result: {'✅ EQUIVALENT' if is_equivalent else '❌ NOT EQUIVALENT'}")
    except Exception as e:
        print(f"   ❌ Could not test: {e}")
    
    print("\n" + "=" * 40)
    print("💡 Key Points:")
    print("   • Evaluation is based on RESULT COMPARISON, not SQL syntax")
    print("   • DISTINCT, ROUND(), and ORDER BY are automatically normalized")
    print("   • Dates, decimals, and data types are standardized")
    print("   • By default, result order doesn't matter (set comparison)")
    print("   • Use conditions={'order': True} if order matters")
    print("\n🎯 Replace DB_NAME with your actual database to run tests!")
