#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os  
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import argparse  
import json
import re


def extract_questions(response):
    """
    Parses model output between [CLARIFICATION] and [/CLARIFICATION]
    
    Returns:
    - List of questions if numbered list found
    - "CLEAR" if response indicates no clarification needed
    - Empty list if malformed
    """
    if not response:
        return []
    
    # Find content between tags
    match = re.search(r'\[CLARIFICATION\](.*?)\[/CLARIFICATION\]', response, re.DOTALL | re.IGNORECASE)
    
    if not match:
        # Try without tags in case model forgot them
        content = response.strip()
    else:
        content = match.group(1).strip()
    
    # Check if CLEAR
    if content.upper() == "CLEAR" or "CLEAR" in content.upper()[:20]:
        return "CLEAR"
    
    # Parse numbered list
    questions = []
    # Match patterns like "1.", "1)", "1:", or just numbers at start of line
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Try to match numbered patterns
        question_match = re.match(r'^(\d+)[\.\)\:]?\s*(.+)$', line)
        if question_match:
            question_text = question_match.group(2).strip()
            if question_text:
                questions.append(question_text)
        elif line and not re.match(r'^[\d\.\)\:\s]+$', line):
            # If line doesn't start with number but has content, might be continuation
            # or unnumbered question
            if questions:
                # Append to last question if it seems like continuation
                if len(line) > 10 and not line[0].isupper():
                    questions[-1] += " " + line
                elif len(line) > 10:
                    # Treat as new question if substantial
                    questions.append(line)
            else:
                # First question without number
                if len(line) > 10:
                    questions.append(line)
    
    return questions


def normalize_question(question):
    """
    Normalize question for deduplication (lowercase, strip, remove extra spaces).
    """
    return ' '.join(question.lower().strip().split())


def deduplicate_questions(all_questions):
    """
    Deduplicate questions while preserving order.
    Uses normalized form for comparison but keeps original text.
    """
    seen = set()
    unique_questions = []
    
    for question in all_questions:
        normalized = normalize_question(question)
        if normalized not in seen and normalized:
            seen.add(normalized)
            unique_questions.append(question)
    
    return unique_questions


def process_disambiguation_responses(source_path, response_paths, result_path):
    """
    Merges responses from multiple tries, extracts questions, and deduplicates.
    Reuses pattern from collect_response.py
    """
    # Support both single path and multiple paths
    if isinstance(response_paths, str):
        response_paths = [response_paths]
    
    # Load responses from all tries
    id_to_responses = {}  # instance_id -> list of responses
    for response_path in response_paths:
        with open(response_path, "r", encoding="utf-8") as resp_file:
            for line in resp_file:
                if not line.strip():
                    continue
                dict_i = json.loads(line)
                instance_id = dict_i.get("instance_id")
                if instance_id is not None:
                    if instance_id not in id_to_responses:
                        id_to_responses[instance_id] = []
                    id_to_responses[instance_id].append(dict_i.get("response", ""))

    # Load source data
    with open(source_path, "r", encoding="utf-8") as f:
        src_file = [json.loads(line) for line in f]
    
    # Process each instance
    with open(result_path, "w", encoding="utf-8") as out_file:
        for item in src_file:
            instance_id = item.get("instance_id")
            
            if instance_id in id_to_responses:
                responses = id_to_responses[instance_id]
                
                # Aggregate questions from all tries
                all_questions = []
                all_responses_text = []
                has_clear = False
                
                for response in responses:
                    all_responses_text.append(response)
                    questions = extract_questions(response)
                    
                    if questions == "CLEAR":
                        has_clear = True
                    elif isinstance(questions, list):
                        all_questions.extend(questions)
                
                # Store all raw responses for debugging
                item["disambiguation_responses"] = all_responses_text
                item["num_tries"] = len(responses)
                
                # If any try says CLEAR, but others have questions, use the questions
                # Only if ALL tries say CLEAR, then mark as no clarification needed
                if has_clear and not all_questions:
                    item["disambiguation_questions"] = []
                    item["num_questions"] = 0
                    item["needs_clarification"] = False
                elif all_questions:
                    # Deduplicate questions across all tries
                    unique_questions = deduplicate_questions(all_questions)
                    item["disambiguation_questions"] = unique_questions
                    item["num_questions"] = len(unique_questions)
                    item["num_questions_before_dedup"] = len(all_questions)
                    item["needs_clarification"] = len(unique_questions) > 0
                else:
                    item["disambiguation_questions"] = []
                    item["num_questions"] = 0
                    item["needs_clarification"] = False
            else:
                # No response found - assume clear
                item["disambiguation_questions"] = []
                item["num_questions"] = 0
                item["needs_clarification"] = False
            
            # Clean up temporary fields
            if "prompt" in item:
                del item["prompt"]
            
            out_file.write(json.dumps(item, ensure_ascii=False) + "\n")


def inference():  
    parser = argparse.ArgumentParser(description='Parse disambiguation responses and extract questions.')  
    parser.add_argument('--source_path', type=str, required=True, 
                        help='Path to the source .jsonl file.')
    parser.add_argument('--response_path', type=str, default=None,
                        help='Path to a single response.jsonl file (deprecated, use --response_paths).')
    parser.add_argument('--response_paths', type=str, nargs='+', default=None,
                        help='Paths to multiple response.jsonl files from different tries.')
    parser.add_argument('--result_path', type=str, required=True, 
                        help='Path where the output .jsonl file with results will be saved.')  
    
    args = parser.parse_args()  
    
    # Support both old single path and new multiple paths
    if args.response_paths:
        response_paths = args.response_paths
    elif args.response_path:
        response_paths = [args.response_path]
    else:
        raise ValueError("Must provide either --response_path or --response_paths")
    
    process_disambiguation_responses(args.source_path, response_paths, args.result_path)

if __name__ == "__main__":  
    inference()
