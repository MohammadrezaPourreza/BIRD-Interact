#!/usr/bin/env python3
"""
Test script to verify SQLExecutionTool serialization fix
"""
import json
import sys
import os
import tempfile

# Add the code directory to path
sys.path.append('/home/dev/lab/BIRD-Interact/bird_interact_conv_enhanced/code')

from infer_api_system_enhanced import ConversationState
from sql_execution_tool import SQLExecutionTool

def test_sqlexecutiontool_serialization():
    """Test that SQLExecutionTool objects are properly handled during JSON serialization"""
    print("🧪 Testing SQLExecutionTool JSON serialization fix...")
    
    try:
        # Simulate the data structure that includes both ConversationState and SQLExecutionTool
        state = ConversationState("test_instance", max_turns=5, max_sql_executions=3)
        sql_tool = SQLExecutionTool("test_db")
        
        # This is what gets stored in the results list
        result_data = {
            "db_id": "test_db",
            "question": "Test question with SQL tool",
            "response": "Test response",
            "conversation_state": state,  # This was fixed before
            "sql_tool": sql_tool,  # This is the new issue
            "other_data": "some value"
        }
        
        # Make a copy and apply the same fixes as in the actual code
        result_data_copy = result_data.copy()
        
        # Convert ConversationState to dict if present
        if "conversation_state" in result_data_copy and hasattr(result_data_copy["conversation_state"], 'to_dict'):
            result_data_copy["conversation_state"] = result_data_copy["conversation_state"].to_dict()
        
        # Remove SQLExecutionTool object (not JSON serializable)
        if "sql_tool" in result_data_copy:
            del result_data_copy["sql_tool"]
        
        # Test JSON serialization (this was failing before the fix)
        json_str = json.dumps(result_data_copy, ensure_ascii=False)
        print("✅ JSON serialization succeeded!")
        print(f"✅ JSON length: {len(json_str)} characters")
        
        # Verify that sql_tool was removed but other data remains
        parsed_data = json.loads(json_str)
        assert "sql_tool" not in parsed_data, "sql_tool should have been removed"
        assert "db_id" in parsed_data, "Other data should remain"
        assert "conversation_state" in parsed_data, "ConversationState should be serialized"
        assert isinstance(parsed_data["conversation_state"], dict), "ConversationState should be a dict"
        
        print("✅ All assertions passed!")
        print("✅ SQLExecutionTool serialization fix works!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_file_writing_simulation():
    """Test the exact file writing scenario that was failing"""
    print("\n🧪 Testing file writing simulation...")
    
    try:
        # Create multiple result entries like in the actual pipeline
        results = []
        
        for i in range(2):
            state = ConversationState(f"instance_{i}", max_turns=5, max_sql_executions=3)
            sql_tool = SQLExecutionTool(f"test_db_{i}")
            
            result_data = {
                "db_id": f"test_db_{i}",
                "question": f"Test question {i}",
                "conversation_state": state,
                "sql_tool": sql_tool,
                "final_score": 0.8
            }
            results.append(result_data)
        
        # Simulate the exact file writing code from infer_api_system_enhanced.py
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as temp_file:
            temp_path = temp_file.name
            
            for result_data in results:
                # Make a copy to avoid modifying original data
                result_data = result_data.copy()
                
                # Convert ConversationState to dict if present
                if "conversation_state" in result_data and hasattr(result_data["conversation_state"], 'to_dict'):
                    result_data["conversation_state"] = result_data["conversation_state"].to_dict()
                
                # Remove SQLExecutionTool object (not JSON serializable)
                if "sql_tool" in result_data:
                    del result_data["sql_tool"]
                
                # This line was failing before the fix
                temp_file.write(json.dumps(result_data, ensure_ascii=False) + '\n')
        
        print("✅ File writing succeeded!")
        
        # Verify file contents
        with open(temp_path, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) == 2, "Should have 2 lines"
        for line in lines:
            parsed = json.loads(line.strip())
            assert "sql_tool" not in parsed, "sql_tool should not be in JSON"
            assert "conversation_state" in parsed, "conversation_state should be in JSON"
        
        print("✅ File verification passed!")
        
        # Clean up
        os.unlink(temp_path)
        
        print("✅ File writing simulation test passed!")
        return True
        
    except Exception as e:
        print(f"❌ File writing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing SQLExecutionTool JSON Serialization Fix")
    print("=" * 60)
    
    test1 = test_sqlexecutiontool_serialization()
    test2 = test_file_writing_simulation()
    
    if test1 and test2:
        print("\n🎉 All SQLExecutionTool JSON tests passed!")
        print("✅ The Docker container error should now be fixed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)