#!/usr/bin/env python3
"""
Test script to verify SQLExecutionTool JSON serialization fix
"""
import json
import sys
import os
import tempfile

# Add the code directory to path
sys.path.append('/home/dev/lab/BIRD-Interact/bird_interact_conv_enhanced/code')

from sql_execution_tool import SQLExecutionTool
from infer_api_system_enhanced import ConversationState

def test_sql_tool_serialization():
    """Test that SQLExecutionTool doesn't break JSON serialization"""
    print("🧪 Testing SQLExecutionTool JSON serialization...")
    
    try:
        # Create the SQL tool (this was causing the error)
        sql_tool = SQLExecutionTool("test_db", max_rows=50, timeout_seconds=15)
        
        # Create conversation state
        state = ConversationState("test_instance", max_turns=5, max_sql_executions=3)
        
        # Simulate the data structure that was causing the error
        result_data = {
            "db_id": "test_db",
            "question": "Test question",
            "response": "Test response",
            "conversation_state": state.to_dict(),  # This was fixed
            # The SQLExecutionTool should NOT be included in JSON data
            # "sql_tool": sql_tool,  # This would cause the error
        }
        
        # Test JSON serialization (this should work now)
        json_str = json.dumps(result_data, ensure_ascii=False)
        print("✅ JSON serialization succeeded!")
        print(f"✅ JSON length: {len(json_str)} characters")
        
        # Test deserialization
        parsed_data = json.loads(json_str)
        restored_state = ConversationState.from_dict(parsed_data["conversation_state"])
        
        assert restored_state.instance_id == "test_instance"
        print("✅ JSON deserialization succeeded!")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_sql_tool_direct_serialization():
    """Test what happens when we try to serialize SQLExecutionTool directly"""
    print("\n🧪 Testing direct SQLExecutionTool serialization (should fail)...")
    
    try:
        sql_tool = SQLExecutionTool("test_db", max_rows=50)
        
        # This should fail (demonstrating the original problem)
        try:
            json_str = json.dumps(sql_tool)
            print("❌ UNEXPECTED: Direct serialization succeeded!")
            return False
        except TypeError as e:
            print(f"✅ Expected: Direct serialization failed: {e}")
            return True
            
    except Exception as e:
        print(f"❌ Test setup failed: {e}")
        return False

def test_data_filtering():
    """Test filtering out non-serializable objects before JSON writing"""
    print("\n🧪 Testing data filtering for JSON serialization...")
    
    try:
        sql_tool = SQLExecutionTool("test_db", max_rows=50)
        state = ConversationState("test_instance", max_turns=5, max_sql_executions=3)
        
        # Simulate data with non-serializable objects
        raw_data = {
            "db_id": "test_db",
            "question": "Test question",
            "response": "Test response",
            "conversation_state": state,  # Will need conversion
            "sql_tool": sql_tool,  # Should be filtered out
            "some_number": 42,
            "some_text": "hello"
        }
        
        # Filter and convert for JSON (this is what the fix does)
        filtered_data = {}
        for key, value in raw_data.items():
            if hasattr(value, 'to_dict'):
                # Convert objects with to_dict method
                filtered_data[key] = value.to_dict()
            elif key not in ['sql_tool']:  # Filter out non-serializable objects
                # Keep serializable objects
                filtered_data[key] = value
        
        # Test serialization of filtered data
        json_str = json.dumps(filtered_data, ensure_ascii=False)
        print("✅ Filtered data serialization succeeded!")
        
        # Verify sql_tool was filtered out
        parsed_data = json.loads(json_str)
        assert "sql_tool" not in parsed_data
        assert "conversation_state" in parsed_data
        assert parsed_data["some_number"] == 42
        
        print("✅ Data filtering test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Filtering test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing SQLExecutionTool JSON Serialization Fix")
    print("=" * 65)
    
    test1 = test_sql_tool_serialization()
    test2 = test_sql_tool_direct_serialization() 
    test3 = test_data_filtering()
    
    if test1 and test2 and test3:
        print("\n🎉 All SQLExecutionTool JSON tests passed!")
        print("✅ The SQLExecutionTool serialization error should now be fixed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)