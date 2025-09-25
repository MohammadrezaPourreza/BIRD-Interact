#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Enhanced BIRD-Interact Implementation

This script tests the basic functionality of the enhanced BIRD-Interact system
with SQL execution tool capabilities.

Author: Enhanced BIRD-Interact Team
"""

import os
import sys
import json
import tempfile
from pathlib import Path

def test_imports():
    """Test that all required modules can be imported."""
    print("🧪 Testing imports...")
    
    try:
        # Test basic SQL execution tool
        sys.path.append(os.path.join(os.path.dirname(__file__), 'code'))
        from sql_execution_tool import SQLExecutionTool, parse_sql_tool_call
        print("   ✅ SQL execution tool imported successfully")
        
        # Test enhanced prompts
        sys.path.append(os.path.join(os.path.dirname(__file__), 'prompts'))
        from prompts_enhanced import system_react_enhanced
        print("   ✅ Enhanced prompts imported successfully")
        
        return True
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return False

def test_sql_tool():
    """Test SQL execution tool functionality."""
    print("\n🔧 Testing SQL execution tool...")
    
    try:
        from sql_execution_tool import SQLExecutionTool, parse_sql_tool_call
        
        # Test SQL tool creation (without actual DB connection)
        tool = SQLExecutionTool("test_db")
        print("   ✅ SQL tool created successfully")
        
        # Test SQL parsing
        test_response = """I need to check the data first.

<sql_execute>SELECT COUNT(*) FROM users;</sql_execute>

Based on the results, I can now provide a better answer."""
        
        sql_query, remaining = parse_sql_tool_call(test_response)
        
        if sql_query == "SELECT COUNT(*) FROM users;":
            print("   ✅ SQL parsing works correctly")
        else:
            print(f"   ❌ SQL parsing failed: got '{sql_query}'")
            return False
            
        if "I need to check the data first." in remaining and "Based on the results" in remaining:
            print("   ✅ Response text parsing works correctly")
        else:
            print(f"   ❌ Response parsing failed: got '{remaining}'")
            return False
            
        return True
    except Exception as e:
        print(f"   ❌ SQL tool test failed: {e}")
        return False

def test_prompt_generation():
    """Test enhanced prompt generation."""
    print("\n📝 Testing prompt generation...")
    
    try:
        from prompts_enhanced import system_react_enhanced
        
        # Test prompt template structure
        required_placeholders = [
            '[[user_query]]', '[[DB_name]]', '[[max_turn]]', 
            '[[max_sql_executions]]', '[[DB_schema]]', '[[external_kg]]'
        ]
        
        for placeholder in required_placeholders:
            if placeholder not in system_react_enhanced:
                print(f"   ❌ Missing placeholder: {placeholder}")
                return False
        
        print("   ✅ Enhanced prompt template has all required placeholders")
        
        # Test SQL execution instructions are present
        if "<sql_execute>" in system_react_enhanced and "SQL execution opportunities" in system_react_enhanced:
            print("   ✅ SQL execution instructions found in prompt")
        else:
            print("   ❌ SQL execution instructions missing from prompt")
            return False
            
        return True
    except Exception as e:
        print(f"   ❌ Prompt test failed: {e}")
        return False

def test_conversation_state():
    """Test conversation state management."""
    print("\n💬 Testing conversation state management...")
    
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), 'code'))
        from infer_api_system_enhanced import ConversationState
        
        # Test conversation state creation
        state = ConversationState("test_instance", max_turns=3, max_sql_executions=5)
        print("   ✅ Conversation state created successfully")
        
        # Test budget tracking
        if state.can_ask_question() and state.can_execute_sql():
            print("   ✅ Budget tracking works")
        else:
            print("   ❌ Budget tracking failed")
            return False
            
        # Test budget consumption
        state.use_clarification_turn()
        state.use_sql_execution()
        
        if state.current_turn == 2 and state.sql_executions_used == 1:
            print("   ✅ Budget consumption works correctly")
        else:
            print(f"   ❌ Budget consumption failed: turn={state.current_turn}, sql={state.sql_executions_used}")
            return False
            
        return True
    except Exception as e:
        print(f"   ❌ Conversation state test failed: {e}")
        return False

def test_file_structure():
    """Test that all required files exist."""
    print("\n📁 Testing file structure...")
    
    base_dir = Path(__file__).parent
    required_files = [
        "code/sql_execution_tool.py",
        "code/infer_api_system_enhanced.py", 
        "code/collect_response_enhanced.py",
        "prompts/prompts_enhanced.py",
        "pipeline/run_enhanced_pipeline.sh",
        "pyproject.toml"
    ]
    
    missing_files = []
    for file_path in required_files:
        full_path = base_dir / file_path
        if not full_path.exists():
            missing_files.append(file_path)
        else:
            print(f"   ✅ {file_path}")
    
    if missing_files:
        print(f"   ❌ Missing files: {missing_files}")
        return False
    
    print("   ✅ All required files present")
    return True

def test_json_processing():
    """Test JSON processing capabilities."""
    print("\n🔧 Testing JSON processing...")
    
    try:
        # Create test data
        test_data = {
            "instance_id": "test_001",
            "selected_database": "test_db",
            "user_query": "Show me all users",
            "amb_user_query": "Show me users",
            "user_query_ambiguity": {"critical_ambiguity": ["time_period"]},
            "knowledge_ambiguity": [],
            "response": "I need to check something. <sql_execute>SELECT * FROM users LIMIT 5;</sql_execute> Now I can help you better."
        }
        
        # Test JSON serialization
        json_str = json.dumps(test_data, ensure_ascii=False)
        parsed_data = json.loads(json_str)
        
        if parsed_data["instance_id"] == "test_001":
            print("   ✅ JSON processing works correctly")
            return True
        else:
            print("   ❌ JSON processing failed")
            return False
            
    except Exception as e:
        print(f"   ❌ JSON processing test failed: {e}")
        return False

def run_all_tests():
    """Run all tests and report results."""
    print("🚀 Starting Enhanced BIRD-Interact Tests")
    print("=" * 50)
    
    tests = [
        ("File Structure", test_file_structure),
        ("Imports", test_imports),
        ("SQL Tool", test_sql_tool),
        ("Prompt Generation", test_prompt_generation),
        ("Conversation State", test_conversation_state),
        ("JSON Processing", test_json_processing),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"   ❌ {test_name} test crashed: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print("🏆 Test Results Summary")
    print(f"   ✅ Passed: {passed}")
    print(f"   ❌ Failed: {failed}")
    print(f"   📊 Success Rate: {passed/(passed+failed)*100:.1f}%")
    
    if failed == 0:
        print("\n🎉 All tests passed! Enhanced BIRD-Interact is ready.")
        return True
    else:
        print(f"\n⚠️  {failed} tests failed. Please check the errors above.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

def test_sql_execution_tool():
    """Test the SQL execution tool functionality."""
    print("🧪 Testing SQL Execution Tool...")
    
    try:
        from sql_execution_tool import SQLExecutionTool, parse_sql_tool_call, process_llm_response_with_sql_tool
        
        # Test SQL tool initialization
        tool = SQLExecutionTool("test_db")
        print("✅ SQL tool initialization successful")
        
        # Test SQL parsing
        test_response = "I need to check the data first.\n\n<sql_execute>SELECT 1 as test;</sql_execute>\n\nBased on the results..."
        sql_query, remaining = parse_sql_tool_call(test_response)
        
        assert sql_query == "SELECT 1 as test;", f"Expected 'SELECT 1 as test;', got '{sql_query}'"
        assert "I need to check the data first." in remaining, "Remaining response parsing failed"
        assert "Based on the results..." in remaining, "Remaining response parsing failed"
        
        print("✅ SQL parsing functionality working correctly")
        
        # Test error handling
        result = tool.execute_sql("")
        assert not result['success'], "Empty query should fail"
        assert result['error_type'] == 'invalid_input', "Wrong error type for empty query"
        
        print("✅ Error handling working correctly")
        print("🎉 SQL Execution Tool tests passed!\n")
        
        return True
        
    except Exception as e:
        print(f"❌ SQL Execution Tool test failed: {e}")
        return False


def test_enhanced_prompts():
    """Test the enhanced prompt system."""
    print("🧪 Testing Enhanced Prompts...")
    
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), 'prompts'))
        from prompts_enhanced import system_react_enhanced, system_debug_enhanced
        
        # Test prompt placeholders
        assert "[[max_sql_executions]]" in system_react_enhanced, "SQL execution placeholder missing"
        assert "<sql_execute>" in system_react_enhanced, "SQL execute tag missing"
        assert "reflection" in system_react_enhanced.lower(), "Reflection guidance missing"
        
        print("✅ Enhanced prompts contain required elements")
        
        # Test template substitution
        test_prompt = system_react_enhanced.replace("[[DB_name]]", "test_db")
        test_prompt = test_prompt.replace("[[max_sql_executions]]", "5")
        test_prompt = test_prompt.replace("[[max_turn]]", "3")
        
        assert "[[DB_name]]" not in test_prompt, "DB name substitution failed"
        assert "5" in test_prompt, "SQL execution count substitution failed"
        
        print("✅ Prompt template substitution working")
        print("🎉 Enhanced Prompts tests passed!\n")
        
        return True
        
    except Exception as e:
        print(f"❌ Enhanced Prompts test failed: {e}")
        return False


def test_conversation_state():
    """Test the conversation state management."""
    print("🧪 Testing Conversation State Management...")
    
    try:
        from infer_api_system_enhanced import ConversationState
        
        # Test state initialization
        state = ConversationState("test_instance", max_turns=3, max_sql_executions=5)
        
        assert state.current_turn == 1, "Initial turn should be 1"
        assert state.sql_executions_used == 0, "Initial SQL executions should be 0"
        assert state.can_ask_question(), "Should be able to ask questions initially"
        assert state.can_execute_sql(), "Should be able to execute SQL initially"
        
        print("✅ State initialization working correctly")
        
        # Test budget tracking
        state.use_clarification_turn()
        state.use_clarification_turn()
        state.use_clarification_turn()
        
        assert not state.can_ask_question(), "Should not be able to ask more questions after budget exhausted"
        assert state.can_execute_sql(), "Should still be able to execute SQL"
        
        print("✅ Budget tracking working correctly")
        
        # Test conversation history
        state.add_conversation("user", "What is the total count?")
        state.add_sql_execution("SELECT COUNT(*) FROM table", {"success": True, "result": [[42]]})
        
        assert len(state.conversation_history) == 1, "Conversation history not updated"
        assert len(state.sql_execution_history) == 1, "SQL history not updated"
        
        print("✅ History tracking working correctly")
        print("🎉 Conversation State tests passed!\n")
        
        return True
        
    except Exception as e:
        print(f"❌ Conversation State test failed: {e}")
        return False


def test_enhanced_response_processing():
    """Test the enhanced response processing."""
    print("🧪 Testing Enhanced Response Processing...")
    
    try:
        from collect_response_enhanced import EnhancedResponseProcessor, parse_sql_tool_call
        
        # Test response processor initialization
        processor = EnhancedResponseProcessor()
        print("✅ Response processor initialization successful")
        
        # Test parsing SQL from responses
        test_response = "Let me check: <sql_execute>SELECT COUNT(*) FROM users;</sql_execute>"
        sql_query, remaining = parse_sql_tool_call(test_response)
        
        assert sql_query == "SELECT COUNT(*) FROM users;", "SQL parsing failed"
        assert remaining.strip() == "Let me check:", "Remaining text parsing failed"
        
        print("✅ SQL parsing from responses working")
        
        # Test response processing without database (should handle gracefully)
        test_data = {
            "response": "I need to explore: <sql_execute>SELECT 1;</sql_execute>",
            "selected_database": "nonexistent_db"
        }
        
        processed = processor.process_response(test_data)
        assert "sql_executed" in processed, "SQL execution flag missing"
        
        print("✅ Response processing pipeline working")
        print("🎉 Enhanced Response Processing tests passed!\n")
        
        return True
        
    except Exception as e:
        print(f"❌ Enhanced Response Processing test failed: {e}")
        return False


def test_enhanced_scoring():
    """Test the enhanced scoring system."""
    print("🧪 Testing Enhanced Scoring System...")
    
    try:
        from calculate_enhanced_score import EnhancedScoreCalculator
        
        # Create temporary test directory
        with tempfile.TemporaryDirectory() as temp_dir:
            calculator = EnhancedScoreCalculator(temp_dir, patience=3, max_sql_executions=5)
            
            # Test with empty directory (should handle gracefully)
            scores = calculator.calculate_traditional_scores()
            assert "error" in scores, "Should handle empty data gracefully"
            
            print("✅ Empty data handling working")
            
            # Test report generation
            report = calculator.generate_comprehensive_report()
            assert "evaluation_config" in report, "Report structure incomplete"
            assert "traditional_scores" in report, "Report structure incomplete"
            assert "enhanced_metrics" in report, "Report structure incomplete"
            
            print("✅ Report generation working")
            
        print("🎉 Enhanced Scoring System tests passed!\n")
        return True
        
    except Exception as e:
        print(f"❌ Enhanced Scoring System test failed: {e}")
        return False


def run_all_tests():
    """Run all tests and report results."""
    print("🚀 Starting Enhanced BIRD-Interact Test Suite")
    print("=" * 60)
    
    tests = [
        ("SQL Execution Tool", test_sql_execution_tool),
        ("Enhanced Prompts", test_enhanced_prompts), 
        ("Conversation State", test_conversation_state),
        ("Response Processing", test_enhanced_response_processing),
        ("Enhanced Scoring", test_enhanced_scoring)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    print("=" * 60)
    print("📊 Test Results Summary:")
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"  {test_name}: {status}")
        if success:
            passed += 1
    
    print(f"\n🏆 Overall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! Enhanced BIRD-Interact is ready to use.")
        return True
    else:
        print("⚠️  Some tests failed. Please review the implementation before proceeding.")
        return False


def main():
    """Main test runner."""
    success = run_all_tests()
    
    if success:
        print("\n🔧 Next Steps:")
        print("1. Configure API keys in code/config.py")
        print("2. Set up database environment with ../evaluation/setup-databases.sh")
        print("3. Run the enhanced pipeline with pipeline/run_enhanced_pipeline.sh")
        sys.exit(0)
    else:
        print("\n🐛 Fix the failing tests before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    main()