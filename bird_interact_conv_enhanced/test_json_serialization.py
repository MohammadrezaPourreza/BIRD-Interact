#!/usr/bin/env python3
"""
Test script to verify ConversationState JSON serialization fix
"""
import json
import sys
import os

# Add the code directory to path
sys.path.append('/home/dev/lab/BIRD-Interact/bird_interact_conv_enhanced/code')

from infer_api_system_enhanced import ConversationState

def test_conversation_state_serialization():
    """Test that ConversationState can be serialized to JSON"""
    print("🧪 Testing ConversationState JSON serialization...")
    
    # Create a ConversationState with some test data
    state = ConversationState("test_instance", max_turns=5, max_sql_executions=3)
    state.current_turn = 2
    state.sql_executions_used = 1
    state.add_conversation("user", "test question")
    state.add_conversation("assistant", "test response")
    state.add_sql_execution("SELECT * FROM test;", {"success": True, "result": "test result"})
    
    try:
        # Test direct JSON serialization (should fail with original code)
        print("❌ Testing direct JSON serialization (should fail)...")
        try:
            json_str = json.dumps(state)
            print(f"❌ UNEXPECTED: Direct serialization succeeded: {json_str}")
            return False
        except TypeError as e:
            print(f"✅ Expected: Direct serialization failed: {e}")
        
        # Test our to_dict() method
        print("✅ Testing to_dict() method...")
        state_dict = state.to_dict()
        print(f"State dict: {state_dict}")
        
        # Test JSON serialization of the dictionary
        print("✅ Testing JSON serialization of dictionary...")
        json_str = json.dumps(state_dict, ensure_ascii=False)
        print(f"JSON serialized: {json_str}")
        
        # Test deserialization
        print("✅ Testing deserialization...")
        parsed_dict = json.loads(json_str)
        restored_state = ConversationState.from_dict(parsed_dict)
        
        # Verify restored state
        assert restored_state.instance_id == state.instance_id
        assert restored_state.current_turn == state.current_turn
        assert restored_state.sql_executions_used == state.sql_executions_used
        assert len(restored_state.conversation_history) == len(state.conversation_history)
        assert len(restored_state.sql_execution_history) == len(state.sql_execution_history)
        
        print("✅ All serialization tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_result_data_serialization():
    """Test serialization of result data with ConversationState"""
    print("\n🧪 Testing result data with ConversationState...")
    
    try:
        # Create test result data like what gets written to JSON files
        state = ConversationState("test_db_instance", max_turns=5, max_sql_executions=3)
        state.current_turn = 3
        state.sql_executions_used = 1
        state.add_conversation("user", "test question")
        state.add_sql_execution("SELECT COUNT(*) FROM table;", {"success": True, "rows": 5})
        
        result_data = {
            "db_id": "test_db",
            "question": "Test question",
            "response": "Test response", 
            "conversation_state": state.to_dict()  # This is the key fix
        }
        
        # Test JSON serialization
        json_str = json.dumps(result_data, ensure_ascii=False)
        print(f"✅ Result data serialized successfully!")
        print(f"Length: {len(json_str)} characters")
        
        # Test deserialization
        parsed_data = json.loads(json_str)
        restored_state = ConversationState.from_dict(parsed_data["conversation_state"])
        
        assert restored_state.current_turn == 3
        print("✅ Result data serialization test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Result data test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing JSON serialization fixes...")
    
    test1 = test_conversation_state_serialization()
    test2 = test_result_data_serialization()
    
    if test1 and test2:
        print("\n🎉 All JSON serialization tests passed!")
        print("✅ The ConversationState JSON serialization issue is fixed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)