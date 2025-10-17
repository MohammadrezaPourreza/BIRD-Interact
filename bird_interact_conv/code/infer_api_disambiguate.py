#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os  
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import argparse  
import json   


def wrap_up_prompt(data, DB_schema_path, external_kg_path, prompt_template):
    """
    Creates prompt for finetuned disambiguation model.
    Reuses logic from infer_api_system.py for loading schema and knowledge.
    """
    # Skip if already processed
    if "disambiguation_response" in data:
        return data
    
    if "prompt" in data:
        del data["prompt"]
    
    try:
        db_name = data.get('selected_database', '')
        question = data.get('amb_user_query', '')
        
        # Load DB schema
        with open(DB_schema_path.replace("[[DB_name]]", db_name), 'r', encoding='utf-8') as file:
            DB_schema = file.read()
        
        # Load and filter external knowledge (exclude masked knowledge)
        external_kg_list = []
        exclude_ids = []
        for knowledge_amb_i in data.get("knowledge_ambiguity", []):
            exclude_ids.append(knowledge_amb_i["deleted_knowledge"])
            
        with open(external_kg_path.replace("[[DB_name]]", db_name), "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("id") not in exclude_ids:
                    external_kg_list.append(json.dumps(obj))

        external_kg = "\n".join(external_kg_list)

        # Fill prompt template
        prompt = prompt_template.replace('[[user_query]]', question)
        prompt = prompt.replace('[[DB_schema]]', DB_schema)
        prompt = prompt.replace('[[external_kg]]', external_kg)
        
        data["prompt"] = prompt
        
    except Exception as e:
        print(f"Error processing instance {data.get('instance_id', 'unknown')}: {e}")
    
    return data


def load_from_jsonl_dataset(prompt_path, result_path, DB_schema_path, external_kg_path, prompt_template):
    """
    Load data and generate disambiguation prompts.
    """
    with open(prompt_path, 'r') as f:
        dataset = [json.loads(line) for line in f]
        dataset = [wrap_up_prompt(dataset[j], DB_schema_path, external_kg_path, prompt_template) 
                   for j in range(len(dataset))]
        
    with open(result_path, "w", encoding="utf-8") as f:
        for item in dataset:
            if "prompt" in item:
                json_line = json.dumps(item, ensure_ascii=False)
                f.write(json_line + "\n")


def inference():  
    parser = argparse.ArgumentParser(description='Generate disambiguation prompts for finetuned model.')  
    parser.add_argument('--prompt_path', type=str, required=True, 
                        help='Path to the input .jsonl file containing prompts.')  
    parser.add_argument('--result_path', type=str, required=True, 
                        help='Path where the output .jsonl file with results will be saved.')  
    parser.add_argument('--DB_schema_path', type=str, required=True, 
                        help='Path where the DB_schema.txt file will be saved.')
    parser.add_argument('--external_kg_path', type=str, required=True, 
                        help='Path where the external_kg.jsonl file will be saved.')  

    args = parser.parse_args()  
        
    from bird_interact_conv.prompts.prompts import system_disambiguate_prompt
    prompt_template = system_disambiguate_prompt

    load_from_jsonl_dataset(
        prompt_path=args.prompt_path, 
        result_path=args.result_path, 
        DB_schema_path=args.DB_schema_path, 
        external_kg_path=args.external_kg_path, 
        prompt_template=prompt_template
    )
 
if __name__ == "__main__":  
    inference()
