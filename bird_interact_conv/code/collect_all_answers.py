#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os  
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import argparse  
import json


def extract_user_response(original_response):
    """
    Extract content between <s> and </s> tags.
    Reuses pattern from infer_api_system.py
    """
    if not original_response:
        return ""
    
    cut_idx = original_response.find("</s>")
    if cut_idx != -1:
        extracted_response = original_response[:cut_idx].strip()
    else:
        extracted_response = original_response.strip()
        
    if "<s>" in extracted_response:
        cut_idx_1 = extracted_response.find("<s>") 
        extracted_response = extracted_response[cut_idx_1:].replace("<s>", "").strip()
        
    return extracted_response


def collect_and_format_answers(parsed_path, decoder_response_path, output_path):
    """
    Groups all Q&A pairs by instance_id and formats them.
    Reuses pattern from collect_response.py
    """
    # Load parsed data
    with open(parsed_path, 'r') as f:
        dataset = {json.loads(line)["instance_id"]: json.loads(line) for line in f if line.strip()}
    
    # Load decoder responses
    decoder_responses = {}
    with open(decoder_response_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            resp = json.loads(line)
            instance_id = resp.get("instance_id")
            question_idx = resp.get("question_idx")
            key = (instance_id, question_idx)
            response = resp.get("response", "")
            decoder_responses[key] = extract_user_response(response)
    
    # Collect and format Q&A pairs
    with open(output_path, "w", encoding="utf-8") as out_file:
        for instance_id, data in dataset.items():
            if not data.get("needs_clarification", False):
                # No clarification needed - pass through without Q&A
                data["disambiguation_answers"] = []
                data["clarification_context"] = ""
            else:
                questions = data.get("disambiguation_questions", [])
                answers = []
                
                for idx, question in enumerate(questions):
                    key = (instance_id, idx)
                    answer = decoder_responses.get(key, "Sorry, I cannot answer that question.")
                    answers.append(answer)
                
                data["disambiguation_answers"] = answers
                
                # Format clarification context for final SQL generation
                qa_pairs = []
                for q, a in zip(questions, answers):
                    qa_pairs.append(f"Q: {q}\nA: {a}")
                
                data["clarification_context"] = "\n\n".join(qa_pairs)
            
            # Clean up temporary fields
            if "prompt" in data:
                del data["prompt"]
            if "disambiguation_response" in data:
                del data["disambiguation_response"]
            
            out_file.write(json.dumps(data, ensure_ascii=False) + "\n")
    
    print(f"Collected answers for {len(dataset)} instances")


def inference():  
    parser = argparse.ArgumentParser(description='Collect all Q&A pairs and format them.')  
    parser.add_argument('--parsed_path', type=str, required=True, 
                        help='Path to the parsed disambiguation .jsonl file.')
    parser.add_argument('--decoder_response_path', type=str, required=True, 
                        help='Path to the decoder response .jsonl file.')
    parser.add_argument('--result_path', type=str, required=True, 
                        help='Path where the output .jsonl file will be saved.')  
    
    args = parser.parse_args()  
    collect_and_format_answers(
        parsed_path=args.parsed_path,
        decoder_response_path=args.decoder_response_path,
        output_path=args.result_path
    )

if __name__ == "__main__":  
    inference()
