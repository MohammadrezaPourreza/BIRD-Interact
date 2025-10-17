#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os  
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import argparse  
import json   


# Modified prompt template for final SQL generation with clarifications
final_sql_prompt_template = """You are a good data scientist with great SQL writing ability. You have a DB called "[[DB_name]]". You are given the DB schema information below:

# DB Schema Info:
[[DB_schema]]

And you are given some useful external knowledge about this DB below:
# External Knowledge:
```json
[[external_kg]]
```

[[clarification_section]]

# Instructions:
You are tasked with generating PostgreSQL to solve the user task below. [[clarification_instruction]]

You MUST enclose your final PostgreSQL between "<t>```postgresql" and "```</t>", for example "<t>```postgresql [FILL-YOUR-SQL] ```</t>".

# User Task:
[[user_query]]

# Your Response:
- You: <t>"""


def create_final_sql_prompt(data, DB_schema_path, external_kg_path):
    """
    Creates prompt for final SQL generation with all clarifications.
    Reuses logic from infer_api_system.py but modified for batch context.
    """
    # Skip if already processed
    if "prompt" in data:
        del data["prompt"]
    
    # Skip if already has final SQL
    if "final_turn" in data and "prediction_turn_" + str(data["final_turn"]) in data:
        return data
    
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
        
        # Prepare clarification section
        clarification_context = data.get("clarification_context", "")
        if clarification_context:
            clarification_section = """# Previous Clarifications:
The following clarifications were provided by the user:
```
[[clarification_context]]
```
"""
            clarification_section = clarification_section.replace("[[clarification_context]]", clarification_context)
            clarification_instruction = "Based on the clarifications provided above, generate the correct PostgreSQL."
        else:
            clarification_section = ""
            clarification_instruction = "Generate the correct PostgreSQL for this task."
        
        # Fill prompt template
        prompt = final_sql_prompt_template.replace('[[user_query]]', question)
        prompt = prompt.replace('[[DB_name]]', db_name)
        prompt = prompt.replace('[[DB_schema]]', DB_schema)
        prompt = prompt.replace('[[external_kg]]', external_kg)
        prompt = prompt.replace('[[clarification_section]]', clarification_section)
        prompt = prompt.replace('[[clarification_instruction]]', clarification_instruction)
        
        data["prompt"] = prompt
        data["final_turn"] = 1  # Mark as turn 1 for compatibility with existing evaluation
        
    except Exception as e:
        print(f"Error processing instance {data.get('instance_id', 'unknown')}: {e}")
    
    return data


def load_from_jsonl_dataset(prompt_path, result_path, DB_schema_path, external_kg_path):
    """
    Load data and generate final SQL prompts.
    """
    with open(prompt_path, 'r') as f:
        dataset = [json.loads(line) for line in f]
        dataset = [create_final_sql_prompt(dataset[j], DB_schema_path, external_kg_path) 
                   for j in range(len(dataset))]
        
    with open(result_path, "w", encoding="utf-8") as f:
        for item in dataset:
            if "prompt" in item:
                json_line = json.dumps(item, ensure_ascii=False)
                f.write(json_line + "\n")


def inference():  
    parser = argparse.ArgumentParser(description='Generate final SQL prompts with clarifications.')  
    parser.add_argument('--prompt_path', type=str, required=True, 
                        help='Path to the input .jsonl file with clarifications.')  
    parser.add_argument('--result_path', type=str, required=True, 
                        help='Path where the output .jsonl file with results will be saved.')  
    parser.add_argument('--DB_schema_path', type=str, required=True, 
                        help='Path where the DB_schema.txt file will be saved.')
    parser.add_argument('--external_kg_path', type=str, required=True, 
                        help='Path where the external_kg.jsonl file will be saved.')  

    args = parser.parse_args()  

    load_from_jsonl_dataset(
        prompt_path=args.prompt_path, 
        result_path=args.result_path, 
        DB_schema_path=args.DB_schema_path, 
        external_kg_path=args.external_kg_path
    )
 
if __name__ == "__main__":  
    inference()
