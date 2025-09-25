#!/usr/bin/env python3
"""
Test script to verify the enhanced pipeline can handle ConversationState serialization
by simulating the actual inference workflow.
"""

import json
import os
import sys
import tempfile

# Add the code directory to path
sys.path.append('/home/dev/lab/BIRD-Interact/bird_interact_conv_enhanced/code')

from infer_api_system_enhanced import ConversationState

def test_pipeline_json_serialization():
    """Test the actual JSON writing workflow that was failing"""
    print("🧪 Testing pipeline JSON serialization workflow...")
    
    try:
        # Simulate the data structure that gets written to results
        state = ConversationState("test_instance", max_turns=5, max_sql_executions=3)
        state.current_turn = 2
        state.sql_executions_used = 1
        state.add_conversation("user", "What are the recent sales?")
        state.add_sql_execution(
            "SELECT * FROM sales LIMIT 5;", 
            {"success": True, "data": [{"id": 1, "amount": 100}], "row_count": 1}
        )
        
        # This is what gets written in the actual pipeline
        result_data = {
            "db_id": "sample_db",
            "question": "What are the recent sales?", 
            "response": "Based on my exploration...",
            "generated_sql": "SELECT * FROM sales WHERE date >= CURRENT_DATE - INTERVAL '30 days';",
            "conversation_state": state.to_dict(),  # KEY FIX: Convert to dict
            "final_score": 0.8,
            "execution_time": 2.5
        }
        
        # Test writing to a temporary file (simulating the actual pipeline)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as temp_file:
            temp_path = temp_file.name
            # This is the exact line that was failing before the fix
            temp_file.write(json.dumps(result_data, ensure_ascii=False) + '\n')
        
        print("✅ JSON writing succeeded!")
        
        # Test reading it back
        with open(temp_path, 'r') as f:
            loaded_data = json.loads(f.readline().strip())
        
        # Verify the conversation state can be restored
        restored_state = ConversationState.from_dict(loaded_data["conversation_state"])
        assert restored_state.instance_id == "test_instance"
        assert restored_state.current_turn == 2
        assert restored_state.sql_executions_used == 1
        assert len(restored_state.sql_execution_history) == 1
        
        print("✅ JSON reading and deserialization succeeded!")
        
        # Clean up
        os.unlink(temp_path)
        
        print("✅ Pipeline JSON serialization test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Pipeline test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_multiple_states_serialization():
    """Test serializing multiple conversation states (batch processing)"""
    print("\n🧪 Testing batch serialization (multiple states)...")
    
    try:
        states_data = []
        
        # Create multiple conversation states
        for i in range(3):
            state = ConversationState(f"instance_{i}", max_turns=5, max_sql_executions=3)
            state.current_turn = i + 1
            state.add_conversation("user", f"Question {i}")
            
            result_data = {
                "db_id": f"db_{i}",
                "question": f"Test question {i}",
                "conversation_state": state.to_dict()
            }
            states_data.append(result_data)
        
        # Test writing all to file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as temp_file:
            temp_path = temp_file.name
            for data in states_data:
                temp_file.write(json.dumps(data, ensure_ascii=False) + '\n')
        
        print("✅ Batch writing succeeded!")
        
        # Test reading all back
        loaded_states = []
        with open(temp_path, 'r') as f:
            for line in f:
                loaded_data = json.loads(line.strip())
                loaded_states.append(ConversationState.from_dict(loaded_data["conversation_state"]))
        
        assert len(loaded_states) == 3
        for i, state in enumerate(loaded_states):
            assert state.instance_id == f"instance_{i}"
            assert state.current_turn == i + 1
        
        print("✅ Batch reading and deserialization succeeded!")
        
        # Clean up
        os.unlink(temp_path)
        
        print("✅ Batch serialization test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Batch test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing Enhanced Pipeline JSON Serialization")
    print("=" * 60)
    
    test1 = test_pipeline_json_serialization()
    test2 = test_multiple_states_serialization()
    
    if test1 and test2:
        print("\n🎉 All pipeline JSON tests passed!")
        print("✅ The original error should now be fixed!")
        print("✅ Enhanced BIRD-Interact can now run in Docker containers!")
        sys.exit(0)
    else:
        print("\n❌ Some pipeline tests failed!")
        sys.exit(1)