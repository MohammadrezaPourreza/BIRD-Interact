#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os  
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import argparse  
import json
from sql_parser import segment_sql


def wrap_up_encoder_prompt(data, question, question_idx, DB_schema_path, prompt_template):
    """
    Creates encoder prompt for a single question.
    Reuses logic from infer_api_user_1.py
    """
    try:
        db_name = data.get('selected_database', '')
        
        # Load DB schema
        with open(DB_schema_path.replace("[[DB_name]]", db_name), 'r', encoding='utf-8') as file:
            DB_schema = file.read()
        
        # Prepare ambiguities JSON (match original format)
        amb_json = "user_query_ambiguity: \n" + json.dumps(data.get("user_query_ambiguity", {}), indent=4) + '\n\nknowledge_ambiguity: \n' + json.dumps(data.get("knowledge_ambiguity", []), indent=4)
        
        # Parse SQL into segments using sql_parser (match original format)
        sql_segs = ""
        cnt = 0
        for sol_sql_i in data.get("sol_sql", []): 
            cnt += 1 
            if cnt > 1:
                sql_segs = sql_segs + "\n===\n"
            for clause, text in segment_sql(sol_sql_i):
                sql_segs = sql_segs + clause + ":\n" + text + "\n\n"
        
        # Fill encoder template
        prompt = prompt_template.replace('[[amb_json]]', amb_json)
        prompt = prompt.replace('[[SQL_Glot]]', sql_segs.strip())
        prompt = prompt.replace('[[DB_schema]]', DB_schema)
        prompt = prompt.replace('[[clarification_Q]]', question)
        
        return {
            "instance_id": data.get("instance_id"),
            "question_idx": question_idx,
            "phase": "encoder",
            "original_question": question,
            "prompt": prompt
        }
        
    except Exception as e:
        print(f"Error creating encoder prompt for instance {data.get('instance_id', 'unknown')}, question {question_idx}: {e}")
        return None


def load_and_generate_encoder_prompts(parsed_path, DB_schema_path, prompt_template, output_path):
    """
    Generate encoder prompts for all questions that need clarification.
    """
    with open(parsed_path, 'r') as f:
        dataset = [json.loads(line) for line in f]
    
    all_prompts = []
    
    for data in dataset:
        if not data.get("needs_clarification", False):
            continue
        
        questions = data.get("disambiguation_questions", [])
        for idx, question in enumerate(questions):
            prompt_data = wrap_up_encoder_prompt(data, question, idx, DB_schema_path, prompt_template)
            if prompt_data:
                all_prompts.append(prompt_data)
    
    # Write all prompts
    with open(output_path, "w", encoding="utf-8") as f:
        for prompt_data in all_prompts:
            f.write(json.dumps(prompt_data, ensure_ascii=False) + "\n")
    
    print(f"Generated {len(all_prompts)} encoder prompts")


def inference():  
    parser = argparse.ArgumentParser(description='Generate user simulator encoder prompts.')  
    parser.add_argument('--parsed_path', type=str, required=True, 
                        help='Path to the parsed disambiguation .jsonl file.')
    parser.add_argument('--result_path', type=str, required=True, 
                        help='Path where the output .jsonl file with prompts will be saved.')  
    parser.add_argument('--DB_schema_path', type=str, required=True, 
                        help='Path template for DB schema files.')
    parser.add_argument('--phase', type=str, default='encoder', 
                        help='Phase: encoder or decoder')
    
    args = parser.parse_args()  
    
    if args.phase == 'encoder':
        from bird_interact_conv.prompts.prompts import user_simulator_encoder
        prompt_template = user_simulator_encoder
        
        load_and_generate_encoder_prompts(
            parsed_path=args.parsed_path,
            DB_schema_path=args.DB_schema_path,
            prompt_template=prompt_template,
            output_path=args.result_path
        )
    else:
        print(f"Phase {args.phase} not supported in this script. Use process_encoder_and_generate_decoder.py for decoder phase.")

if __name__ == "__main__":  
    inference()
