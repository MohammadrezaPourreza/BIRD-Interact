#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os  
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import argparse  
import json
from sql_parser import segment_sql


def extract_action(encoder_response):
    """
    Extracts action from encoder response.
    Example: "<s>labeled("customer_type")</s>" → 'labeled("customer_type")'
    Reuses pattern from infer_api_system.py extract functions
    """
    if not encoder_response:
        return "unanswerable()"
    
    # Extract content between <s> and </s>
    start_idx = encoder_response.find("<s>")
    end_idx = encoder_response.find("</s>")
    
    if start_idx != -1 and end_idx != -1:
        action = encoder_response[start_idx+3:end_idx].strip()
    elif start_idx != -1:
        action = encoder_response[start_idx+3:].strip()
    else:
        action = encoder_response.strip()
    
    # Clean up any extra tags
    action = action.replace("<s>", "").replace("</s>", "").strip()
    
    # Default to unanswerable if empty or malformed
    if not action or len(action) < 3:
        action = "unanswerable()"
    
    return action


def wrap_up_decoder_prompt(data, question, question_idx, action, DB_schema_path, prompt_template):
    """
    Creates decoder prompt for a single question with its action.
    Reuses logic from infer_api_user_2.py
    """
    try:
        db_name = data.get('selected_database', '')
        
        # Load DB schema
        with open(DB_schema_path.replace("[[DB_name]]", db_name), 'r', encoding='utf-8') as file:
            DB_schema = file.read()
        
        # Prepare ambiguities JSON (match original format)
        amb_json = "user_query_ambiguity: \n" + json.dumps(data.get("user_query_ambiguity", {}), indent=4) + '\n\nknowledge_ambiguity: \n' + json.dumps(data.get("knowledge_ambiguity", []), indent=4)
        
        # Parse SQL into segments (match original format)
        sql_segs = ""
        sol_sql_all = ""
        cnt = 0
        for sol_sql_i in data.get("sol_sql", []): 
            sol_sql_all = sol_sql_all + sol_sql_i + "\n\n"
            cnt += 1 
            if cnt > 1:
                sql_segs = sql_segs + "\n===\n"
            for clause, text in segment_sql(sol_sql_i):
                sql_segs = sql_segs + clause + ":\n" + text + "\n\n"
        
        # Get clear query
        clear_query = data.get('query', data.get('amb_user_query', ''))
        
        # Fill decoder template
        prompt = prompt_template.replace('[[DB_schema]]', DB_schema)
        prompt = prompt.replace('[[amb_json]]', amb_json)
        prompt = prompt.replace('[[GT_SQL]]', sol_sql_all.strip())
        prompt = prompt.replace('[[SQL_Glot]]', sql_segs.strip())
        prompt = prompt.replace('[[clarification_Q]]', question)
        prompt = prompt.replace('[[Action]]', action)
        prompt = prompt.replace('[[clear_query]]', clear_query)
        
        return {
            "instance_id": data.get("instance_id"),
            "question_idx": question_idx,
            "phase": "decoder",
            "original_question": question,
            "action": action,
            "prompt": prompt
        }
        
    except Exception as e:
        print(f"Error creating decoder prompt for instance {data.get('instance_id', 'unknown')}, question {question_idx}: {e}")
        return None


def generate_decoder_prompts(parsed_path, encoder_response_path, DB_schema_path, prompt_template, output_path):
    """
    Process encoder responses and generate decoder prompts.
    """
    # Load parsed data
    with open(parsed_path, 'r') as f:
        dataset = {json.loads(line)["instance_id"]: json.loads(line) for line in f if line.strip()}
    
    # Load encoder responses
    encoder_responses = {}
    with open(encoder_response_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            resp = json.loads(line)
            instance_id = resp.get("instance_id")
            question_idx = resp.get("question_idx")
            key = (instance_id, question_idx)
            encoder_responses[key] = resp.get("response", "")
    
    # Generate decoder prompts
    all_prompts = []
    
    for instance_id, data in dataset.items():
        if not data.get("needs_clarification", False):
            continue
        
        questions = data.get("disambiguation_questions", [])
        for idx, question in enumerate(questions):
            key = (instance_id, idx)
            encoder_response = encoder_responses.get(key, "")
            action = extract_action(encoder_response)
            
            prompt_data = wrap_up_decoder_prompt(
                data, question, idx, action, DB_schema_path, prompt_template
            )
            if prompt_data:
                all_prompts.append(prompt_data)
    
    # Write all prompts
    with open(output_path, "w", encoding="utf-8") as f:
        for prompt_data in all_prompts:
            f.write(json.dumps(prompt_data, ensure_ascii=False) + "\n")
    
    print(f"Generated {len(all_prompts)} decoder prompts")


def inference():  
    parser = argparse.ArgumentParser(description='Process encoder responses and generate decoder prompts.')  
    parser.add_argument('--parsed_path', type=str, required=True, 
                        help='Path to the parsed disambiguation .jsonl file.')
    parser.add_argument('--encoder_response_path', type=str, required=True, 
                        help='Path to the encoder response .jsonl file.')
    parser.add_argument('--result_path', type=str, required=True, 
                        help='Path where the output .jsonl file with decoder prompts will be saved.')  
    parser.add_argument('--DB_schema_path', type=str, required=True, 
                        help='Path template for DB schema files.')
    
    args = parser.parse_args()  
    
    from bird_interact_conv.prompts.prompts import user_simulator_decoder
    prompt_template = user_simulator_decoder
    
    generate_decoder_prompts(
        parsed_path=args.parsed_path,
        encoder_response_path=args.encoder_response_path,
        DB_schema_path=args.DB_schema_path,
        prompt_template=prompt_template,
        output_path=args.result_path
    )

if __name__ == "__main__":  
    inference()
