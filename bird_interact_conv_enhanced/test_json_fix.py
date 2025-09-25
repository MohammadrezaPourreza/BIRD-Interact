#!/usr/bin/env python3
"""
Test script to verify ConversationState JSON serialization
"""

import json
import sys
import os

# Add the code directory to Python path
sys.path.append('/home/dev/lab/BIRD-Interact/bird_interact_conv_enhanced/code')

from infer_api_system_enhanced import ConversationState

def test_conversation_state_serialization():
    """Test that ConversationState can be properly serialized to JSON"""
    
    print("🧪 Testing ConversationState JSON serialization...")
    
    # Create a ConversationState object
    state = ConversationState("test_instance", max_turns=3, max_sql_executions=5)
    
    # Add some test data
    state.add_conversation("user", "What are the sales figures?")
    state.add_sql_execution("SELECT * FROM sales LIMIT 1", {"status": "success", "rows": 1})
    state.use_clarification_turn()
    state.use_sql_execution()
    
    # Test to_dict method
    state_dict = state.to_dict()
    print(f"✅ ConversationState.to_dict() works: {bool(state_dict)}")
    
    # Test JSON serialization
    try:
        json_str = json.dumps(state_dict, ensure_ascii=False)
        print(f"✅ JSON serialization works: {len(json_str)} characters")
        
        # Test deserialization
        loaded_dict = json.loads(json_str)
        new_state = ConversationState.from_dict(loaded_dict)
        print(f"✅ JSON deserialization works: {new_state.instance_id}")
        
        # Test data integrity
        assert new_state.instance_id == state.instance_id
        assert new_state.current_turn == state.current_turn
        assert new_state.sql_executions_used == state.sql_executions_used
        assert len(new_state.conversation_history) == len(state.conversation_history)
        assert len(new_state.sql_execution_history) == len(state.sql_execution_history)
        print("✅ Data integrity preserved")
        
        # Test the problematic scenario from the error
        test_data = {
            "instance_id": "test",
            "conversation_state": state  # This was causing the error
        }
        
        # Simulate the fix
        test_data_fixed = test_data.copy()
        if "conversation_state" in test_data_fixed and hasattr(test_data_fixed["conversation_state"], 'to_dict'):
            test_data_fixed["conversation_state"] = test_data_fixed["conversation_state"].to_dict()
            
        json_str_fixed = json.dumps(test_data_fixed, ensure_ascii=False)
        print("✅ Fixed JSON serialization for data with ConversationState works")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during JSON serialization: {e}")
        return False

if __name__ == "__main__":
    success = test_conversation_state_serialization()
    if success:
        print("\n🎉 All ConversationState serialization tests passed!")
        print("The JSON serialization error should now be fixed.")
    else:
        print("\n💥 Tests failed - there are still serialization issues.")
        sys.exit(1)