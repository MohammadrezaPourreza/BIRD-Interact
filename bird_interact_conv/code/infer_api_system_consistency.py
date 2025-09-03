#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os  
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import argparse  
import json   
import hashlib
from collections import Counter
from typing import Dict, List, Tuple, Any

# Import consistency analyzer functions
from consistency_analyzer import execute_sql_queries


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

def extract_sql_from_response(response: str) -> str:
    """Extract SQL query from model response."""
    if "```postgresql" in response:
        start_idx = response.find("```postgresql")
        sql_block = response[start_idx:].replace("```postgresql", "").strip()
        if "```" in sql_block:
            end_idx = sql_block.find("```")
            sql_block = sql_block[:end_idx].strip()
        return sql_block
    elif "<t>" in response and "</t>" in response:
        start_idx = response.find("<t>")
        end_idx = response.find("</t>")
        sql_block = response[start_idx+3:end_idx].strip()
        if "```postgresql" in sql_block:
            sql_block = sql_block.replace("```postgresql", "").replace("```", "").strip()
        return sql_block
    else:
        return response.strip()

def normalize_sql_for_comparison(sql: str) -> str:
    """Normalize SQL for comparison by removing whitespace and converting to lowercase."""
    return ' '.join(sql.lower().split())

def hash_sql_result(sql_result: Any) -> str:
    """Create a hash of SQL execution result for grouping."""
    if sql_result is None:
        return "null_result"
    
    # Convert result to string for hashing
    result_str = str(sql_result)
    return hashlib.md5(result_str.encode()).hexdigest()

def group_queries_by_results(sql_queries: List[str], sql_results: List[Any]) -> Dict[Any, List[str]]:
    """Group SQL queries by their execution results."""
    result_groups = {}
    
    for sql, result in zip(sql_queries, sql_results):
        # Use the result directly as the key (since it's already processed)
        result_key = result if isinstance(result, (tuple, str)) else str(result)
        
        if result_key not in result_groups:
            result_groups[result_key] = []
        result_groups[result_key].append(sql)
    
    return result_groups

def get_highest_confidence_query(result_groups: Dict[Any, List[str]], num_resp: int) -> Tuple[str, float]:
    """Get the query from the largest group and calculate confidence."""
    if not result_groups:
        return "", 0.0
    
    # Find the largest group
    largest_group_key = max(result_groups.keys(), key=lambda k: len(result_groups[k]))
    largest_group = result_groups[largest_group_key]
    
    # Calculate confidence
    confidence = len(largest_group) / num_resp
    
    # Return the first query from the largest group
    highest_confidence_query = largest_group[0]
    
    return highest_confidence_query, confidence

def build_conversation_context(data: Dict, turn_i: int) -> str:
    """Build conversation context from previous turns."""
    context = ""
    for i in range(1, turn_i):
        if f'prediction_turn_{i}' in data:
            sys_response = data[f'prediction_turn_{i}']
            context += f"### Turn {i}:\n- System: {sys_response}\n"
            if f'user_response_turn_{i}' in data:
                user_response = data[f'user_response_turn_{i}']
                context += f"- User: {user_response}\n"
    return context

def format_sql_queries_list(unique_queries: List[str]) -> str:
    """Format unique SQL queries for display in prompt."""
    formatted_list = ""
    for i, query in enumerate(unique_queries, 1):
        formatted_list += f"Query {i}:\n```postgresql\n{query}\n```\n\n"
    return formatted_list

def wrap_up_prompt_consistency(data, DB_schema_path, external_kg_path, prompt_template_react, 
                             prompt_template_sql, prompt_template_clarification, patience, turn_i, 
                             data_user_dict, phase="amb", num_resp=5, threshold=0.6):    
    if "prompt" in data:
        del data["prompt"]
    
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
        if "Terminate_flg" in data or return_flg:
            terminate_flag = True
            return data
        else:
            terminate_flag = False
        
        max_turn = len(data["user_query_ambiguity"]["critical_ambiguity"]) + len(data["knowledge_ambiguity"]) + patience
        
        ### Database setup for all turns
        db_name = data.get('selected_database', '')
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
        
        ### Build conversation context for non-first turns
        conversation_context = ""
        if turn_i > 1:
            conversation_context = build_conversation_context(data, turn_i)
            conversation_context = f"# Conversation Context:\n{conversation_context}\n"
        
        ### Check if we need to generate multiple SQL queries or ask clarification
        if 'consistency_mode' not in data or data['consistency_mode'] == 'generate_sql':
            # Generate multiple SQL queries for consistency check
            data['consistency_mode'] = 'generate_sql'
            data['num_resp'] = num_resp
            data['current_turn'] = turn_i
            
            # Create SQL generation prompt
            prompt = prompt_template_sql.replace('[[user_query]]', question)
            prompt = prompt.replace('[[DB_name]]', db_name)
            prompt = prompt.replace('[[DB_schema]]', DB_schema)
            prompt = prompt.replace('[[external_kg]]', external_kg)
            prompt = prompt.replace('[[conversation_context]]', conversation_context)
            
            data['prompt_turn_'+str(turn_i)] = prompt
            data["prompt"] = prompt
            data['final_turn'] = turn_i
            data['max_turn'] = max_turn
            
        elif data['consistency_mode'] == 'analyze_consistency':
            # Analyze the generated SQL queries and decide next action
            generated_queries = data.get('generated_sql_queries', [])
            sql_results = data.get('sql_execution_results', [])
            
            if not generated_queries:
                # Fallback to regular mode if no queries generated
                data['consistency_mode'] = 'regular'
                prompt = prompt_template_react.replace('[[user_query]]', question)
                prompt = prompt.replace('[[DB_name]]', db_name)
                prompt = prompt.replace('[[max_turn]]', str(max_turn))
                prompt = prompt.replace('[[DB_schema]]', DB_schema)
                prompt = prompt.replace('[[external_kg]]', external_kg)
                
                data['prompt_turn_'+str(turn_i)] = prompt
                data["prompt"] = prompt
                data['final_turn'] = turn_i
                data['max_turn'] = max_turn
                return data
            
            # Execute SQL queries if not already executed
            if not sql_results or len(sql_results) != len(generated_queries):
                try:
                    sql_results = execute_sql_queries(generated_queries, db_name)
                    data['sql_execution_results'] = sql_results
                except Exception as e:
                    print(f"Error executing SQL queries: {e}")
                    # Use mock results as fallback
                    sql_results = [f"Error: {e}"] * len(generated_queries)
                    data['sql_execution_results'] = sql_results
            
            # Group queries by results
            result_groups = group_queries_by_results(generated_queries, sql_results)
            highest_confidence_query, confidence = get_highest_confidence_query(result_groups, num_resp)
            
            data['confidence'] = confidence
            data['highest_confidence_query'] = highest_confidence_query
            
            if confidence >= threshold:
                # High confidence - use the highest confidence query
                data["Terminate_flg"] = True
                data['pred_sqls'] = [highest_confidence_query]
                data['final_prediction'] = highest_confidence_query
                data['consistency_mode'] = 'completed'
                return data
            else:
                # Low confidence - ask clarifying question
                data['consistency_mode'] = 'ask_clarification'
                
                # Get unique queries for clarification prompt
                unique_queries = []
                seen_normalized = set()
                for query_list in result_groups.values():
                    for query in query_list:
                        normalized = normalize_sql_for_comparison(query)
                        if normalized not in seen_normalized:
                            unique_queries.append(query)
                            seen_normalized.add(normalized)
                
                sql_queries_list = format_sql_queries_list(unique_queries[:5])  # Limit to 5 for readability
                
                prompt = prompt_template_clarification.replace('[[user_query]]', question)
                prompt = prompt.replace('[[DB_name]]', db_name)
                prompt = prompt.replace('[[DB_schema]]', DB_schema)
                prompt = prompt.replace('[[external_kg]]', external_kg)
                prompt = prompt.replace('[[conversation_context]]', conversation_context)
                prompt = prompt.replace('[[sql_queries_list]]', sql_queries_list)
                
                data['prompt_turn_'+str(turn_i)] = prompt
                data["prompt"] = prompt
                data['final_turn'] = turn_i
                data['unique_queries_for_clarification'] = unique_queries
                
        elif data['consistency_mode'] == 'ask_clarification':
            # We asked for clarification, now continue with regular conversation
            data['consistency_mode'] = 'generate_sql'  # Reset for next round
            
            prompt = data.get('prompt_turn_'+str(turn_i-1), '')
            response_prev = data.get('prediction_turn_'+str(turn_i-1), '')
            response_user_prev = data_user.get('prediction_turn_'+str(turn_i-1), '')
            
            if max_turn > turn_i:
                sys_response, terminate_flag = extract_system_response(response_prev)
                if terminate_flag == True:
                    data["Terminate_flg"] = True
                user_response = extract_user_response(response_user_prev)
                data[f'user_response_turn_{turn_i-1}'] = user_response
                prompt = prompt + sys_response + "\n- User: " + user_response + '\n\n### Turn [[turn_i]] ([[turn_left]] turns left): \n# Based on the clarification above, generate the final PostgreSQL query.\n# Format: "<t>```postgresql [YOUR-SQL] ```</t>"\n- You: <t>'.replace('[[turn_i]]', str(turn_i)).replace('[[turn_left]]', str(max_turn-turn_i+1))
            else:
                sys_response, terminate_flag = extract_system_response(response_prev)
                if terminate_flag == True:
                    data["Terminate_flg"] = True
                user_response = extract_user_response(response_user_prev)
                data[f'user_response_turn_{turn_i-1}'] = user_response
                prompt = prompt + sys_response + "\n- User: " + user_response + '\n\n### Turn [[turn_i]] (1 turn left): \n# It is the final turn. You MUST provide the final PostgreSQL and follow the format: "<t>```postgresql [YOUR-SQL] ```</t>"\n- You: <t>'.replace('[[turn_i]]', str(turn_i))
            
            if terminate_flag != True:  
                data['prompt_turn_'+str(turn_i)] = prompt
                data["prompt"] = prompt
                data['final_turn'] = turn_i
                
    elif phase=="debug" and data_user!={} and data_user["status"]=="failed":
        # Debug phase - same as original logic
        data_sql_report = data_user
        prompt = data.get('prompt_turn_'+str(data['final_turn']), '')
        data['final_turn'] = data['final_turn'] + 1
        
        if "[exec_err_flg]" in data_sql_report["error_msg"]:
            error_msg = "Your SQL is not executable and raises the following error: " + data_sql_report["error_msg"]
        else:
            error_msg = "Are you sure about your SQL? You have one more chance to update your SQL now."
            
        prompt = prompt.replace("- You: <t>", "- You: \n```postgresql \n") + data_sql_report.get('pred_sqls', '')[0] + '\n``` \n\n### Turn [[turn_i]]: \n# Your sql in previous turn may have problem. You MUST provide the updated PostgreSQL and follow the format: "<t>```postgresql [YOUR-SQL] ```</t>"\n-User: '.replace('[[turn_i]]', str(data['final_turn'])) + error_msg.strip() + '\n- You: <t>'
        
        data['prompt_turn_'+str(data['final_turn'])] = prompt
        data["prompt"] = prompt
    
    elif phase=="follow" and data_user!={} and data_user["status"]=="success":
        # Follow-up phase - same as original logic
        data_sql_report = data_user
        prompt = data.get('prompt_turn_'+str(data['final_turn']), '')
        data['final_turn'] = data['final_turn'] + 1
        follow_up_Q = data['follow_up']['query']
        
        prompt = prompt.replace("- You: <t>", "- You: \n```postgresql \n") + data_sql_report.get('pred_sqls', '')[0] + '\n``` \n\n### Turn [[turn_i]]: \n# Here is a follow up question. You MUST provide the PostgreSQ to solve this question and follow the format: "<t>```postgresql [YOUR-SQL] ```</t>"\n-User: ```text \n'.replace('[[turn_i]]', str(data['final_turn'])) + follow_up_Q + '\n```\n\n- You: <t>'
        data['prompt_turn_'+str(data['final_turn'])] = prompt
        data["prompt"] = prompt
        
    else:
        pass

    return data

def load_from_jsonl_dataset(prompt_path, user_resp_path, result_path, DB_schema_path, external_kg_path, 
                           prompt_template_react, prompt_template_sql, prompt_template_clarification, 
                           patience, turn_i, phase="amb", num_resp=5, threshold=0.6):

    with open(user_resp_path, 'r') as f:
        dataset_user = {}
        for line in f:
            dict = json.loads(line)
            dataset_user[dict["instance_id"]] = dict
    with open(prompt_path, 'r') as f:
        dataset = [json.loads(line) for line in f]
        dataset = [wrap_up_prompt_consistency(dataset[j], DB_schema_path, external_kg_path, 
                                            prompt_template_react, prompt_template_sql, 
                                            prompt_template_clarification, patience, turn_i, 
                                            dataset_user, phase=phase, num_resp=num_resp, 
                                            threshold=threshold) for j in range(len(dataset))]
        
    with open(result_path, "w", encoding="utf-8") as f:
        for item in dataset:
            if "prompt" in item:
                json_line = json.dumps(item, ensure_ascii=False)
                f.write(json_line + "\n")


def inference():  
    parser = argparse.ArgumentParser(description='Call OpenAI API with specified parameters and configurations for consistency-based system.')  
    parser.add_argument('--patience', type=int, default=6, help='Maximum turn.')   
    parser.add_argument('--turn_num', type=int, help='Turn number.')   
    parser.add_argument('--prompt_path', type=str, required=True, help='Path to the input .jsonl file containing prompts.')  
    parser.add_argument('--user_resp_path', type=str, required=True, help='Path to the user_resp.jsonl file containing user responses.')
    parser.add_argument('--result_path', type=str, required=True, help='Path where the output .jsonl file with results will be saved.')  
    parser.add_argument('--DB_schema_path', type=str, required=True, help='Path where the DB_schema.json file will be saved.')
    parser.add_argument('--external_kg_path', type=str, required=True, help='Path where the external_kg.json file will be saved.')  
    parser.add_argument('--phase', type=str, required=False, default='amb', help='The phase you want to proceed: ["amb", "debug", "follow"]')
    parser.add_argument('--num_resp', type=int, default=5, help='Number of SQL responses to generate for consistency check.')
    parser.add_argument('--threshold', type=float, default=0.6, help='Confidence threshold for accepting SQL query.')

    args = parser.parse_args()  
        
    from bird_interact_conv.prompts.new_prompts import system_react_consistency, system_generate_sql_only, system_clarification_question
    prompt_template_react = system_react_consistency
    prompt_template_sql = system_generate_sql_only
    prompt_template_clarification = system_clarification_question

    load_from_jsonl_dataset(prompt_path=args.prompt_path, user_resp_path=args.user_resp_path, 
                           result_path=args.result_path, DB_schema_path=args.DB_schema_path, 
                           external_kg_path=args.external_kg_path, 
                           prompt_template_react=prompt_template_react,
                           prompt_template_sql=prompt_template_sql,
                           prompt_template_clarification=prompt_template_clarification,
                           patience=args.patience, turn_i=args.turn_num, phase=args.phase,
                           num_resp=args.num_resp, threshold=args.threshold)
 
if __name__ == "__main__":  
    inference()
