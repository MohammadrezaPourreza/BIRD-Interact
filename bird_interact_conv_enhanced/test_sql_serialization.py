#!/usr/bin/env python3
"""
Test script to verify that Decimal and date JSON serialization works
"""
import json
import sys
import os
from decimal import Decimal
from datetime import date, datetime

# Add the code directory to path
sys.path.append('/home/dev/lab/BIRD-Interact/bird_interact_conv_enhanced/code')

from collect_response_enhanced import EnhancedJSONEncoder
from infer_api_system_enhanced import EnhancedJSONEncoder as InferJSONEncoder

def test_sql_result_serialization():
    """Test serialization of SQL result types"""
    print("🧪 Testing SQL result type serialization...")
    
    try:
        # Test data with SQL result types that were causing errors
        test_data = {
            "db_id": "test_db",
            "query": "SELECT price, created_date FROM products LIMIT 1;",
            "results": {
                "data": [
                    {
                        "price": Decimal("19.99"),  # This was causing the error
                        "created_date": date(2024, 1, 15),  # This was causing the error  
                        "updated_at": datetime(2024, 1, 15, 10, 30, 0),
                        "name": "Test Product"
                    }
                ],
                "row_count": 1,
                "success": True
            }
        }
        
        # Test with collect_response_enhanced encoder
        json_str1 = json.dumps(test_data, ensure_ascii=False, cls=EnhancedJSONEncoder)
        print("✅ collect_response_enhanced encoder works")
        print(f"   Sample: {json_str1[:100]}...")
        
        # Test with infer_api_system_enhanced encoder
        json_str2 = json.dumps(test_data, ensure_ascii=False, cls=InferJSONEncoder)
        print("✅ infer_api_system_enhanced encoder works")
        
        # Test deserialization
        parsed_data = json.loads(json_str1)
        assert parsed_data["results"]["data"][0]["price"] == 19.99
        assert parsed_data["results"]["data"][0]["created_date"] == "2024-01-15"
        assert parsed_data["results"]["data"][0]["updated_at"] == "2024-01-15T10:30:00"
        
        print("✅ Serialization and deserialization work correctly")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_original_problematic_types():
    """Test the exact types that were causing the original errors"""
    print("\n🧪 Testing original problematic types...")
    
    try:
        # These are the exact types mentioned in the error
        problematic_data = {
            "decimal_value": Decimal("123.456"),
            "date_value": date.today(),
            "mixed_array": [
                Decimal("99.99"),
                date(2024, 12, 25),
                "normal_string",
                42
            ]
        }
        
        # This should work now
        json_str = json.dumps(problematic_data, ensure_ascii=False, cls=EnhancedJSONEncoder)
        parsed = json.loads(json_str)
        
        # Verify conversion
        assert isinstance(parsed["decimal_value"], float)
        assert isinstance(parsed["date_value"], str)
        assert isinstance(parsed["mixed_array"][0], float)
        assert isinstance(parsed["mixed_array"][1], str)
        
        print("✅ All problematic types now serialize correctly")
        return True
        
    except Exception as e:
        print(f"❌ Problematic types test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing SQL Result JSON Serialization Fixes")
    print("=" * 60)
    
    test1 = test_sql_result_serialization()
    test2 = test_original_problematic_types()
    
    if test1 and test2:
        print("\n🎉 All SQL result serialization tests passed!")
        print("✅ Decimal and date JSON serialization errors are fixed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)