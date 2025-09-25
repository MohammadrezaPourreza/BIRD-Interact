#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Enhanced System Inference for BIRD-Interact with SQL Execution Tool

This module handles the enhanced conversation flow that allows LLMs to execute SQL queries
during the clarification phase for better problem understanding and solution refinement.

Author: Enhanced BIRD-Interact Team
"""

import os  
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import argparse  
import json
import re
from decimal import Decimal
from datetime import date, datetime
from sql_execution_tool import SQLExecutionTool, parse_sql_tool_call, process_llm_response_with_sql_tool


class EnhancedJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles SQL result types like Decimal, date, datetime"""
    
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, (date, datetime)):
            return obj.isoformat()
        elif hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return super().default(obj)


class ConversationState:
    """Tracks the state of enhanced conversations with SQL execution budgets."""
    
    def __init__(self, instance_id: str, max_turns: int, max_sql_executions: int):
        self.instance_id = instance_id
        self.max_turns = max_turns
        self.max_sql_executions = max_sql_executions
        self.current_turn = 1
        self.sql_executions_used = 0
        self.conversation_history = []
        self.sql_execution_history = []
        self.terminated = False
        
    def can_ask_question(self) -> bool:
        """Check if more clarification questions are allowed."""
        return self.current_turn <= self.max_turns and not self.terminated
    
    def can_execute_sql(self) -> bool:
        """Check if more SQL executions are allowed."""
        return self.sql_executions_used < self.max_sql_executions and not self.terminated
    
    def use_clarification_turn(self):
        """Use one clarification turn."""
        self.current_turn += 1
    
    def use_sql_execution(self):
        """Use one SQL execution."""
        self.sql_executions_used += 1
    
    def add_conversation(self, role: str, message: str):
        """Add a message to conversation history."""
        self.conversation_history.append({"role": role, "message": message, "turn": self.current_turn})
    
    def add_sql_execution(self, query: str, result: dict):
        """Add SQL execution to history."""
        self.sql_execution_history.append({
            "turn": self.current_turn,
            "query": query,
            "result": result,
            "timestamp": self.sql_executions_used + 1
        })
    
    def terminate(self):
        """Mark conversation as terminated."""
        self.terminated = True
    
    def get_status_info(self) -> str:
        """Get current status for prompts."""
        turns_left = max(0, self.max_turns - self.current_turn + 1)
        sql_left = max(0, self.max_sql_executions - self.sql_executions_used)
        return f"{turns_left} clarification turns left, {sql_left} SQL executions left"
    
    def to_dict(self) -> dict:
        """Convert ConversationState to JSON-serializable dictionary."""
        return {
            "instance_id": self.instance_id,
            "max_turns": self.max_turns,
            "max_sql_executions": self.max_sql_executions,
            "current_turn": self.current_turn,
            "sql_executions_used": self.sql_executions_used,
            "conversation_history": self.conversation_history,
            "sql_execution_history": self.sql_execution_history,
            "terminated": self.terminated
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """Create ConversationState from dictionary."""
        state = cls(data["instance_id"], data["max_turns"], data["max_sql_executions"])
        state.current_turn = data["current_turn"]
        state.sql_executions_used = data["sql_executions_used"]
        state.conversation_history = data["conversation_history"]
        state.sql_execution_history = data["sql_execution_history"]
        state.terminated = data["terminated"]
        return state


def process_batch_data(data, batch_size):
    # Assuming process_batch_data is a custom function to split data into batches
    return [data[i:i + batch_size] for i in range(0, len(data), batch_size)]


def extract_user_response(original_response):
    cut_idx = original_response.find("</s>")
    if cut_idx != -1:
        extracted_response = original_response[:cut_idx].strip()
    else:
        extracted_response = original_response
        
    if "<s>" in extracted_response:
        cut_idx_1 = extracted_response.find("<s>") 
        extracted_response = extracted_response[cut_idx_1:].replace("<s>", "").strip()
        
    return extracted_response


def extract_system_response(original_response):
    cut_prep = original_response.find("### Turn ")
    if cut_prep != -1:
        original_response = original_response[:cut_prep]
    if "</s>" in original_response:
        sep_char = "s"
        terminate_flag = False
    elif "</t>" in original_response:
        sep_char = "t"
        terminate_flag = True
    else:
        terminate_flag = False
        return original_response, terminate_flag
    
    cut_idx = original_response.find("</"+sep_char+">")
    extracted_response = original_response[:cut_idx].strip()
    if "<"+sep_char+">" in extracted_response:
        cut_idx_1 = extracted_response.find("<"+sep_char+">") 
        extracted_response = extracted_response[cut_idx_1:].replace("<"+sep_char+">", "").strip()
        
    return extracted_response, terminate_flag


def extract_enhanced_system_response(original_response):
    """
    Enhanced version that handles SQL execution tool calls.
    Returns (response, terminate_flag, sql_query, response_type)
    """
    # Check for SQL execution first
    sql_query, remaining_response = parse_sql_tool_call(original_response)
    if sql_query:
        return remaining_response, False, sql_query, "sql_execution"
    
    # Then check for standard responses
    cut_prep = original_response.find("### Turn ")
    if cut_prep != -1:
        original_response = original_response[:cut_prep]
        
    if "</s>" in original_response:
        sep_char = "s"
        terminate_flag = False
        response_type = "clarification"
    elif "</t>" in original_response:
        sep_char = "t"
        terminate_flag = True
        response_type = "final_sql"
    else:
        terminate_flag = False
        return original_response, terminate_flag, None, "unknown"
    
    cut_idx = original_response.find("</"+sep_char+">")
    extracted_response = original_response[:cut_idx].strip()
    if "<"+sep_char+">" in extracted_response:
        cut_idx_1 = extracted_response.find("<"+sep_char+">") 
        extracted_response = extracted_response[cut_idx_1:].replace("<"+sep_char+">", "").strip()
        
    return extracted_response, terminate_flag, None, response_type


def wrap_up_prompt_enhanced(data, DB_schema_path, external_kg_path, prompt_template, patience, turn_i, data_user_dict, phase="amb", max_sql_executions=5):
    """Enhanced prompt generation with SQL execution tool support."""
    
    if "prompt" in data:
        del data["prompt"]
    
    # Initialize conversation state if not exists
    instance_id = data.get("instance_id", "unknown")
    if "conversation_state" not in data:
        max_turns = len(data["user_query_ambiguity"]["critical_ambiguity"]) + len(data["knowledge_ambiguity"]) + patience
        data["conversation_state"] = ConversationState(instance_id, max_turns, max_sql_executions)
    elif isinstance(data["conversation_state"], dict):
        # If conversation_state is a dict (loaded from JSON), convert it back to ConversationState object
        data["conversation_state"] = ConversationState.from_dict(data["conversation_state"])
    
    conv_state = data["conversation_state"]
    
    # Initialize SQL execution tool
    db_name = data.get('selected_database', '')
    if "sql_tool" not in data:
        data["sql_tool"] = SQLExecutionTool(db_name)
    
    sql_tool = data["sql_tool"]
    
    # re-run error cases: set flg
    if 'prediction_turn_'+str(turn_i) in data and "Error:" in data['prediction_turn_'+str(turn_i)]:
        error_flg = True
        data["error_flg"] = error_flg
    else:
        error_flg = False
        data["error_flg"] = error_flg
    return_flg = 'prediction_turn_'+str(turn_i) in data and "Error:" not in data['prediction_turn_'+str(turn_i)]
    
    # Start
    try:
        data_user = data_user_dict[data["instance_id"]]
    except KeyError:
        data_user = {}
    
    if phase == "amb":
        if conv_state.terminated or return_flg:
            return data
        
        ### If first turn:
        if turn_i == 1:
            question = data.get('amb_user_query', '')
            with open(DB_schema_path.replace("[[DB_name]]", db_name), 'r', encoding='utf-8') as file:
                DB_schema = file.read()
            
            ### Exclude masked knowledge
            external_kg_list = []
            exclude_ids = []
            for knowledge_amb_i in data["knowledge_ambiguity"]:
                exclude_ids.append(knowledge_amb_i["deleted_knowledge"])
                
            with open(external_kg_path.replace("[[DB_name]]", db_name), "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if obj.get("id") not in exclude_ids:
                        external_kg_list.append(json.dumps(obj))

            external_kg = "\n".join(external_kg_list)

            ### Enhanced prompt filling
            prompt = prompt_template.replace('[[user_query]]', question)
            prompt = prompt.replace('[[DB_name]]', db_name)
            prompt = prompt.replace('[[max_turn]]', str(conv_state.max_turns))
            prompt = prompt.replace('[[max_sql_executions]]', str(conv_state.max_sql_executions))
            prompt = prompt.replace('[[DB_schema]]', DB_schema)
            prompt = prompt.replace('[[external_kg]]', external_kg)
            
        ### If not first turn:
        else:
            prompt = data.get('prompt_turn_'+str(turn_i-1), '')
            response_prev = data.get('prediction_turn_'+str(turn_i-1), '')
            response_user_prev = data_user.get('prediction_turn_'+str(turn_i-1), '')
            
            # Process previous system response for SQL execution
            processed_response = process_llm_response_with_sql_tool(response_prev, sql_tool)
            
            # Check if SQL was executed in previous turn
            sql_query, remaining_response = parse_sql_tool_call(response_prev)
            if sql_query and conv_state.can_execute_sql():
                # Execute the SQL and get results
                execution_result = sql_tool.execute_sql(sql_query)
                conv_state.add_sql_execution(sql_query, execution_result)
                conv_state.use_sql_execution()
                
                # Format result for conversation
                sql_result_formatted = sql_tool.format_result_for_llm(execution_result)
                conv_state.add_conversation("system_sql", sql_result_formatted)
            
            # Extract the regular response part
            sys_response, terminate_flag, _, _ = extract_enhanced_system_response(response_prev)
            
            if terminate_flag:
                conv_state.terminate()
                data["Terminate_flg"] = True
                
            user_response = extract_user_response(response_user_prev) if response_user_prev else ""
            
            if conv_state.can_ask_question():
                status_info = conv_state.get_status_info()
                prompt = prompt + sys_response + "\n- User: " + user_response + f'\n\n### Turn {turn_i} ({status_info}): \n# Format Options:\n# - Clarification: "<s>[YOUR-QUESTION]</s>"\n# - SQL Execution: "<sql_execute>[YOUR-SQL-QUERY]</sql_execute>"\n# - Final Answer: "<t>```postgresql [FILL-YOUR-SQL] ```</t>"\n- You: '
            else:
                prompt = prompt + sys_response + "\n- User: " + user_response + f'\n\n### Turn {turn_i} (Final turn): \n# You MUST provide the final PostgreSQL: "<t>```postgresql [YOUR-SQL] ```</t>"\n- You: <t>'
        
        if not conv_state.terminated:  
            data['prompt_turn_'+str(turn_i)] = prompt
            data["prompt"] = prompt
            data['final_turn'] = turn_i
            
    elif phase == "debug" and data_user != {} and data_user.get("status") == "failed":
        data_sql_report = data_user
        prompt = data.get('prompt_turn_'+str(data['final_turn']), '')
        data['final_turn'] = data['final_turn'] + 1
        
        if "[exec_err_flg]" in data_sql_report.get("error_msg", ""):
            error_msg = "Your SQL is not executable and raises the following error: " + data_sql_report["error_msg"]
        else:
            error_msg = "Are you sure about your SQL? You have one more chance to update your SQL now."
        
        # Enhanced debug prompt with SQL execution capability
        status_info = conv_state.get_status_info() if "conversation_state" in data else "0 SQL executions left"
        prompt = prompt.replace("- You: <t>", "- You: \n```postgresql \n") + data_sql_report.get('pred_sqls', '')[0] + f'\n``` \n\n### Debug Turn ({status_info}): \n# Options:\n# - SQL Execution: "<sql_execute>[DIAGNOSTIC-QUERY]</sql_execute>"\n# - Fixed Answer: "<t>```postgresql [YOUR-SQL] ```</t>"\n-User: ' + error_msg.strip() + '\n- You: '
        
        data['prompt_turn_'+str(data['final_turn'])] = prompt
        data["prompt"] = prompt
    
    elif phase == "follow" and data_user != {} and data_user.get("status") == "success":
        data_sql_report = data_user
        prompt = data.get('prompt_turn_'+str(data['final_turn']), '')
        data['final_turn'] = data['final_turn'] + 1
        follow_up_Q = data['follow_up']['query']
        
        # Reset SQL execution budget for follow-up phase
        conv_state.sql_executions_used = 0  # Reset for follow-up phase
        
        status_info = f"{max_sql_executions} SQL executions left"
        prompt = prompt.replace("- You: <t>", "- You: \n```postgresql \n") + data_sql_report.get('pred_sqls', '')[0] + f'\n``` \n\n### Follow-up Turn ({status_info}): \n# Follow-up Question: {follow_up_Q}\n# Options:\n# - SQL Execution: "<sql_execute>[EXPLORATION-QUERY]</sql_execute>"\n# - Final Answer: "<t>```postgresql [YOUR-SQL] ```</t>"\n-User: Your SQL looks good! Now I have a follow-up question: ' + follow_up_Q + '\n- You: '
        
        data['prompt_turn_'+str(data['final_turn'])] = prompt
        data["prompt"] = prompt
    
    return data


def load_from_jsonl_dataset(prompt_path, user_resp_path, result_path, DB_schema_path, external_kg_path, prompt_template, patience, turn_i, phase="amb", max_sql_executions=5):
    """Enhanced dataset loading with SQL execution tool support."""
    
    # Build user response dictionary
    data_user_dict = {}
    with open(user_resp_path, 'r', encoding='utf-8') as file_user:
        for line_user in file_user:
            try:
                data_user = json.loads(line_user.strip())
                data_user_dict[data_user.get("instance_id", "")] = data_user
            except json.JSONDecodeError:
                continue
    
    # Process each data item
    results = []
    with open(prompt_path, 'r', encoding='utf-8') as file:
        for line in file:
            try:
                data = json.loads(line.strip())
                if not data:
                    continue
                    
                # Apply enhanced prompt wrapping
                updated_data = wrap_up_prompt_enhanced(
                    data, DB_schema_path, external_kg_path, prompt_template, 
                    patience, turn_i, data_user_dict, phase, max_sql_executions
                )
                
                if updated_data and "prompt" in updated_data:
                    results.append(updated_data)
                    
            except json.JSONDecodeError:
                continue
    
    # Write results
    with open(result_path, 'w', encoding='utf-8') as file_out:
        for result_data in results:
            # Make a copy to avoid modifying original data
            result_data = result_data.copy()
            
            # Convert ConversationState to dict if present
            if "conversation_state" in result_data and hasattr(result_data["conversation_state"], 'to_dict'):
                result_data["conversation_state"] = result_data["conversation_state"].to_dict()
            
            # Remove SQLExecutionTool object (not JSON serializable)
            if "sql_tool" in result_data:
                del result_data["sql_tool"]
            
            file_out.write(json.dumps(result_data, ensure_ascii=False, cls=EnhancedJSONEncoder) + '\n')


def inference():  
    parser = argparse.ArgumentParser(description='Enhanced BIRD-Interact system inference with SQL execution tool.')  
    parser.add_argument('--patience', type=int, default=3, help='Maximum clarification turns.')   
    parser.add_argument('--max_sql_executions', type=int, default=5, help='Maximum SQL executions allowed.')
    parser.add_argument('--turn_num', type=int, help='Turn number.')   
    parser.add_argument('--prompt_path', type=str, required=True, help='Path to the input .jsonl file containing prompts.')  
    parser.add_argument('--user_resp_path', type=str, required=True, help='Path to the user_resp.jsonl file containing user responses.')
    parser.add_argument('--result_path', type=str, required=True, help='Path where the output .jsonl file with results will be saved.')  
    parser.add_argument('--DB_schema_path', type=str, required=True, help='Path where the DB_schema.json file will be saved.')
    parser.add_argument('--external_kg_path', type=str, required=True, help='Path where the external_kg.json file will be saved.')  
    parser.add_argument('--phase', type=str, required=False, default='amb', help='The phase you want to proceed: ["amb", "debug", "follow"]')

    args = parser.parse_args()  
        
    # Use enhanced prompts
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/../prompts')
    from prompts_enhanced import system_react_enhanced
    prompt_template = system_react_enhanced

    load_from_jsonl_dataset(
        prompt_path=args.prompt_path, 
        user_resp_path=args.user_resp_path, 
        result_path=args.result_path, 
        DB_schema_path=args.DB_schema_path, 
        external_kg_path=args.external_kg_path, 
        prompt_template=prompt_template, 
        patience=args.patience, 
        turn_i=args.turn_num, 
        phase=args.phase,
        max_sql_executions=args.max_sql_executions
    )


if __name__ == "__main__":  
    inference()