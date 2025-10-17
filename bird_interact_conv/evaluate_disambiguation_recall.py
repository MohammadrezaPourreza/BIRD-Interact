#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Disambiguation Recall Evaluation Script

This script evaluates the effectiveness of disambiguation question generation
by computing recall metrics for both baseline (iterative) and finetuned (batch) approaches.

Recall = Number of labeled ambiguities addressed / Total critical ambiguities

Usage:
    # Evaluate baseline approach
    python evaluate_disambiguation_recall.py --approach baseline --model_name gemini-2.5-pro

    # Evaluate finetuned batch approach
    python evaluate_disambiguation_recall.py --approach finetuned --model_name gemini-2.5-pro --finetuned_model "projects/..."
    
    # Evaluate with custom paths
    python evaluate_disambiguation_recall.py --approach baseline --model_name gpt-4 --data_path custom_data.jsonl
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import argparse
import json
import re
from collections import defaultdict
from typing import Dict, List, Tuple
from datetime import datetime


def extract_action(encoder_response):
    """
    Extracts action from encoder response.
    Example: "<s>labeled("customer_type")</s>" → 'labeled("customer_type")'
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


def is_labeled_action(action):
    """
    Checks if action is labeled("...") type.
    Returns True for labeled actions, False otherwise.
    """
    action_lower = action.lower().strip()
    return action_lower.startswith("labeled(") or action_lower.startswith("labeled (")


def extract_labeled_term(action):
    """
    Extracts the term from labeled("term") action.
    Returns the term or None if not a labeled action.
    """
    if not is_labeled_action(action):
        return None
    
    # Extract content between parentheses
    match = re.search(r'labeled\s*\(\s*["\']?([^"\'()]+)["\']?\s*\)', action, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def get_critical_ambiguities(data):
    """
    Extracts all critical ambiguity terms from the ground truth data.
    Returns a set of ambiguity terms.
    """
    ambiguity_terms = set()
    
    # Extract from user_query_ambiguity.critical_ambiguity
    # Each item is a dict with keys: term, sql_snippet, is_mask, type
    # We want the value of the "term" key
    user_query_amb = data.get("user_query_ambiguity", {})
    if isinstance(user_query_amb, dict):
        critical_amb = user_query_amb.get("critical_ambiguity", [])
        if isinstance(critical_amb, list):
            for amb_item in critical_amb:
                if isinstance(amb_item, dict):
                    # Get the "term" value from the ambiguity dict
                    term = amb_item.get("term", "")
                    if term:
                        ambiguity_terms.add(term)
    
    # Extract from knowledge_ambiguity
    # Each item is a dict with keys: term, sql_snippet, is_mask, type, deleted_knowledge
    # We want the value of the "term" key
    knowledge_amb = data.get("knowledge_ambiguity", [])
    if isinstance(knowledge_amb, list):
        for amb_item in knowledge_amb:
            if isinstance(amb_item, dict):
                term = amb_item.get("term", "")
                # Use the term as the ambiguity identifier
                if term:
                    ambiguity_terms.add(term)
    
    return ambiguity_terms


def evaluate_baseline_recall(result_dir, data_path, patience=3):
    """
    Evaluates recall for the baseline (iterative) approach.
    
    Args:
        result_dir: Directory containing baseline results
        data_path: Path to original data
        patience: Number of patience turns
        
    Returns:
        Dict with recall metrics per instance and overall statistics
    """
    print("\n" + "="*60)
    print("EVALUATING BASELINE (ITERATIVE) APPROACH")
    print("="*60)
    
    # Load original data for ground truth
    with open(data_path, 'r') as f:
        ground_truth = {json.loads(line)["instance_id"]: json.loads(line) 
                       for line in f if line.strip()}
    
    # Load user_1_interaction.jsonl (contains encoder responses)
    user_1_path = os.path.join(result_dir, "user_1_interaction.jsonl")
    
    if not os.path.exists(user_1_path):
        print(f"ERROR: File not found: {user_1_path}")
        return None
    
    results = {}
    
    with open(user_1_path, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            
            data = json.loads(line)
            instance_id = data.get("instance_id")
            
            if instance_id not in ground_truth:
                continue
            
            gt_data = ground_truth[instance_id]
            critical_ambiguities = get_critical_ambiguities(gt_data)
            
            # Collect all labeled actions across all turns
            labeled_terms = set()
            
            # Check all prediction turns
            for key, value in data.items():
                if key.startswith("prediction_turn_"):
                    action = extract_action(value)
                    if is_labeled_action(action):
                        term = extract_labeled_term(action)
                        if term:
                            labeled_terms.add(term)
            
            # Calculate recall
            total_ambiguities = len(critical_ambiguities)
            addressed_ambiguities = len(labeled_terms & critical_ambiguities)
            recall = addressed_ambiguities / total_ambiguities if total_ambiguities > 0 else 0.0
            
            results[instance_id] = {
                "total_ambiguities": total_ambiguities,
                "addressed_ambiguities": addressed_ambiguities,
                "recall": recall,
                "critical_ambiguities": list(critical_ambiguities),
                "labeled_terms": list(labeled_terms),
                "matched_terms": list(labeled_terms & critical_ambiguities)
            }
    
    return results


def evaluate_finetuned_recall(result_dir, data_path):
    """
    Evaluates recall for the finetuned (batch) approach.
    
    Args:
        result_dir: Directory containing finetuned results
        data_path: Path to original data
        
    Returns:
        Dict with recall metrics per instance and overall statistics
    """
    print("\n" + "="*60)
    print("EVALUATING FINETUNED (BATCH) APPROACH")
    print("="*60)
    
    # Load original data for ground truth
    with open(data_path, 'r') as f:
        ground_truth = {json.loads(line)["instance_id"]: json.loads(line) 
                       for line in f if line.strip()}
    
    # Load user_encoder_response.jsonl (contains encoder responses for all questions)
    encoder_path = os.path.join(result_dir, "user_encoder_response.jsonl")
    
    if not os.path.exists(encoder_path):
        print(f"ERROR: File not found: {encoder_path}")
        return None
    
    # Group encoder responses by instance_id
    encoder_responses = defaultdict(list)
    with open(encoder_path, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            resp = json.loads(line)
            instance_id = resp.get("instance_id")
            response = resp.get("response", "")
            action = extract_action(response)
            encoder_responses[instance_id].append(action)
    
    results = {}
    
    for instance_id, gt_data in ground_truth.items():
        critical_ambiguities = get_critical_ambiguities(gt_data)
        
        # Collect all labeled actions for this instance
        labeled_terms = set()
        actions = encoder_responses.get(instance_id, [])
        
        for action in actions:
            if is_labeled_action(action):
                term = extract_labeled_term(action)
                if term:
                    labeled_terms.add(term)
        
        # Calculate recall
        total_ambiguities = len(critical_ambiguities)
        addressed_ambiguities = len(labeled_terms & critical_ambiguities)
        recall = addressed_ambiguities / total_ambiguities if total_ambiguities > 0 else 0.0
        
        results[instance_id] = {
            "total_ambiguities": total_ambiguities,
            "addressed_ambiguities": addressed_ambiguities,
            "recall": recall,
            "critical_ambiguities": list(critical_ambiguities),
            "labeled_terms": list(labeled_terms),
            "matched_terms": list(labeled_terms & critical_ambiguities)
        }
    
    return results


def compute_statistics(results):
    """
    Computes aggregate statistics from per-instance results.
    
    Returns:
        Dict with overall statistics
    """
    if not results:
        return None
    
    recalls = [r["recall"] for r in results.values()]
    total_instances = len(recalls)
    
    # Count perfect recalls
    perfect_recalls = sum(1 for r in recalls if r == 1.0)
    zero_recalls = sum(1 for r in recalls if r == 0.0)
    
    # Distribution
    recall_bins = {
        "0.0": 0,
        "0.0-0.2": 0,
        "0.2-0.4": 0,
        "0.4-0.6": 0,
        "0.6-0.8": 0,
        "0.8-1.0": 0,
        "1.0": 0
    }
    
    for r in recalls:
        if r == 0.0:
            recall_bins["0.0"] += 1
        elif r == 1.0:
            recall_bins["1.0"] += 1
        elif r < 0.2:
            recall_bins["0.0-0.2"] += 1
        elif r < 0.4:
            recall_bins["0.2-0.4"] += 1
        elif r < 0.6:
            recall_bins["0.4-0.6"] += 1
        elif r < 0.8:
            recall_bins["0.6-0.8"] += 1
        else:
            recall_bins["0.8-1.0"] += 1
    
    stats = {
        "total_instances": total_instances,
        "mean_recall": sum(recalls) / total_instances if total_instances > 0 else 0.0,
        "min_recall": min(recalls) if recalls else 0.0,
        "max_recall": max(recalls) if recalls else 0.0,
        "perfect_recalls": perfect_recalls,
        "perfect_recall_rate": perfect_recalls / total_instances if total_instances > 0 else 0.0,
        "zero_recalls": zero_recalls,
        "zero_recall_rate": zero_recalls / total_instances if total_instances > 0 else 0.0,
        "recall_distribution": recall_bins
    }
    
    return stats


def print_results(results, stats, approach):
    """
    Prints detailed results and statistics.
    """
    print(f"\n{'='*60}")
    print(f"RESULTS FOR {approach.upper()} APPROACH")
    print(f"{'='*60}\n")
    
    if not results or not stats:
        print("No results to display.")
        return
    
    # Overall statistics
    print("OVERALL STATISTICS")
    print("-" * 60)
    print(f"Total Instances:        {stats['total_instances']}")
    print(f"Mean Recall:            {stats['mean_recall']:.4f}")
    print(f"Min Recall:             {stats['min_recall']:.4f}")
    print(f"Max Recall:             {stats['max_recall']:.4f}")
    print(f"Perfect Recalls (1.0):  {stats['perfect_recalls']} ({stats['perfect_recall_rate']:.2%})")
    print(f"Zero Recalls (0.0):     {stats['zero_recalls']} ({stats['zero_recall_rate']:.2%})")
    
    print("\nRECALL DISTRIBUTION")
    print("-" * 60)
    for bin_name, count in stats['recall_distribution'].items():
        percentage = count / stats['total_instances'] * 100
        bar = "█" * int(percentage / 2)
        print(f"{bin_name:>10}: {count:>4} ({percentage:>5.1f}%) {bar}")
    
    # Sample instances
    print("\nSAMPLE INSTANCES (First 5)")
    print("-" * 60)
    for i, (instance_id, result) in enumerate(list(results.items())[:5]):
        print(f"\nInstance ID: {instance_id}")
        print(f"  Total Ambiguities:     {result['total_ambiguities']}")
        print(f"  Addressed Ambiguities: {result['addressed_ambiguities']}")
        print(f"  Recall:                {result['recall']:.4f}")
        print(f"  Critical Ambiguities:  {result['critical_ambiguities']}")
        print(f"  Labeled Terms:         {result['labeled_terms']}")
        print(f"  Matched Terms:         {result['matched_terms']}")
    
    print(f"\n{'='*60}\n")


def save_results(results, stats, output_path, approach):
    """
    Saves results to JSON file.
    """
    output_data = {
        "approach": approach,
        "statistics": stats,
        "per_instance_results": results
    }
    
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"Results saved to: {output_path}")


def run_baseline_pipeline(data_path, DB_schema_path, result_dir, system_model_name, US_model_name, patience):
    """
    Runs the baseline pipeline to generate disambiguation questions.
    """
    print("\n" + "="*60)
    print("RUNNING BASELINE PIPELINE")
    print("="*60)
    
    # Import necessary modules
    from bird_interact_conv.code.infer_api_system import load_from_jsonl_dataset as system_load
    from bird_interact_conv.code.infer_api_user_1 import load_from_jsonl_dataset as user1_load
    from bird_interact_conv.prompts.prompts import system_react, user_simulator_encoder
    from bird_interact_conv.code.call_api import collect_response_from_api, load_jsonl
    from bird_interact_conv.code.collect_response import merge_jsonl_by_instance_id
    
    external_kg_path = DB_schema_path.replace("_schema.txt", "_kb.jsonl")
    
    # Turn 1 only for disambiguation evaluation
    turn_num = 1
    
    print(f"\nTurn {turn_num}: System generates clarification questions...")
    
    # System interaction
    system_prompt_path = os.path.join(result_dir, "system_interaction_prompt.jsonl")
    system_load(
        prompt_path=data_path,
        user_resp_path=data_path,
        result_path=system_prompt_path,
        DB_schema_path=DB_schema_path,
        external_kg_path=external_kg_path,
        prompt_template=system_react,
        patience=patience,
        turn_i=turn_num,
        phase="amb"
    )
    
    # Call API for system
    system_response_path = os.path.join(result_dir, "system_interaction_response.jsonl")
    data_list = load_jsonl(system_prompt_path)
    prompts = [d["prompt"] for d in data_list]
    print(f"Calling API for {len(prompts)} system prompts...")
    collect_response_from_api(prompts, system_model_name, data_list, system_response_path)
    
    # Collect system responses
    system_interaction_path = os.path.join(result_dir, "system_interaction.jsonl")
    merge_jsonl_by_instance_id(data_path, system_response_path, system_interaction_path)
    
    print(f"\nTurn {turn_num}: User simulator (encoder) processes questions...")
    
    # User simulator encoder
    user1_prompt_path = os.path.join(result_dir, "user_1_interaction_prompt.jsonl")
    user1_load(
        prompt_path=data_path,
        sys_resp_path=system_interaction_path,
        result_path=user1_prompt_path,
        DB_schema_path=DB_schema_path,
        prompt_template=user_simulator_encoder,
        turn_i=turn_num
    )
    
    # Call API for user simulator
    user1_response_path = os.path.join(result_dir, "user_1_interaction_response.jsonl")
    data_list = load_jsonl(user1_prompt_path)
    prompts = [d["prompt"] for d in data_list]
    print(f"Calling API for {len(prompts)} user encoder prompts...")
    collect_response_from_api(prompts, US_model_name, data_list, user1_response_path)
    
    # Collect user responses
    user1_interaction_path = os.path.join(result_dir, "user_1_interaction.jsonl")
    merge_jsonl_by_instance_id(data_path, user1_response_path, user1_interaction_path)
    
    print("\n✓ Baseline pipeline completed")


def run_finetuned_pipeline(data_path, DB_schema_path, result_dir, finetuned_model, US_model_name):
    """
    Runs the finetuned pipeline to generate disambiguation questions.
    """
    print("\n" + "="*60)
    print("RUNNING FINETUNED PIPELINE")
    print("="*60)
    
    # Import necessary modules
    from bird_interact_conv.code.infer_api_disambiguate import load_from_jsonl_dataset as disambiguate_load
    from bird_interact_conv.code.parse_disambiguation_response import process_disambiguation_responses
    from bird_interact_conv.code.infer_api_batch_user_simulator import load_and_generate_encoder_prompts
    from bird_interact_conv.prompts.prompts import system_disambiguate_prompt, user_simulator_encoder
    from bird_interact_conv.code.call_api import collect_response_from_api, load_jsonl
    
    external_kg_path = DB_schema_path.replace("_schema.txt", "_kb.jsonl")
    
    print("\nStep 1: Generating disambiguation questions...")
    
    # Generate disambiguation prompts
    disambiguation_prompt_path = os.path.join(result_dir, "disambiguation_prompt.jsonl")
    disambiguate_load(
        prompt_path=data_path,
        result_path=disambiguation_prompt_path,
        DB_schema_path=DB_schema_path,
        external_kg_path=external_kg_path,
        prompt_template=system_disambiguate_prompt
    )
    
    # Call finetuned model
    disambiguation_response_path = os.path.join(result_dir, "disambiguation_response.jsonl")
    data_list = load_jsonl(disambiguation_prompt_path)
    prompts = [d["prompt"] for d in data_list]
    print(f"Calling finetuned model for {len(prompts)} prompts...")
    collect_response_from_api(prompts, finetuned_model, data_list, disambiguation_response_path)
    
    # Parse responses
    disambiguation_parsed_path = os.path.join(result_dir, "disambiguation_parsed.jsonl")
    process_disambiguation_responses(data_path, disambiguation_response_path, disambiguation_parsed_path)
    
    print("\nStep 2: User simulator (encoder) processes questions...")
    
    # Generate encoder prompts
    user_encoder_prompts_path = os.path.join(result_dir, "user_encoder_prompts.jsonl")
    load_and_generate_encoder_prompts(
        parsed_path=disambiguation_parsed_path,
        DB_schema_path=DB_schema_path,
        prompt_template=user_simulator_encoder,
        output_path=user_encoder_prompts_path
    )
    
    # Call user simulator
    user_encoder_response_path = os.path.join(result_dir, "user_encoder_response.jsonl")
    data_list = load_jsonl(user_encoder_prompts_path)
    prompts = [d["prompt"] for d in data_list]
    print(f"Calling user simulator for {len(prompts)} encoder prompts...")
    collect_response_from_api(prompts, US_model_name, data_list, user_encoder_response_path)
    
    print("\n✓ Finetuned pipeline completed")


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate disambiguation recall for baseline vs finetuned approaches.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument('--approach', type=str, required=True, choices=['baseline', 'finetuned'],
                        help='Approach to evaluate: baseline (iterative) or finetuned (batch)')
    
    parser.add_argument('--model_name', type=str, required=True,
                        help='System model name (e.g., gemini-2.5-pro, gpt-4)')
    
    parser.add_argument('--finetuned_model', type=str, default=None,
                        help='Finetuned model endpoint (required for finetuned approach)')
    
    parser.add_argument('--data_path', type=str, 
                        default='/app/bird_interact_conv/data/bird-interact-lite/bird_interact_data.jsonl',
                        help='Path to the original data file')
    
    parser.add_argument('--DB_schema_path', type=str,
                        default='/app/bird_interact_conv/data/bird-interact-lite/[[DB_name]]/[[DB_name]]_schema.txt',
                        help='Path template for DB schema files')
    
    parser.add_argument('--result_dir', type=str, default=None,
                        help='Directory containing results (auto-generated if not provided)')
    
    parser.add_argument('--output_path', type=str, default=None,
                        help='Path to save evaluation results JSON (auto-generated if not provided)')
    
    parser.add_argument('--timestamp', type=str, default=None,
                        help='Timestamp to use for output filename (format: YYYYMMDD_HHMMSS)')
    
    parser.add_argument('--patience', type=int, default=3,
                        help='Patience parameter for baseline approach')
    
    parser.add_argument('--US_model_name', type=str, default='gemini-2.0-flash',
                        help='User simulator model name')
    
    parser.add_argument('--run_pipeline', action='store_true',
                        help='Run the disambiguation pipeline before evaluation')
    
    parser.add_argument('--project_root', type=str, default='/app/',
                        help='Project root directory')
    
    args = parser.parse_args()
    
    # Validate inputs
    if args.approach == 'finetuned' and not args.finetuned_model:
        parser.error("--finetuned_model is required when --approach is 'finetuned'")
    
    # Setup result directory
    if args.result_dir is None:
        if args.approach == 'baseline':
            args.result_dir = os.path.join(
                args.project_root, 
                f'bird_interact_conv/results/patience_{args.patience}/{args.model_name}/'
            )
        else:
            args.result_dir = os.path.join(
                args.project_root,
                f'bird_interact_conv/results/batch_disambiguation/{args.model_name}/'
            )
    
    # Setup output path with optional timestamp
    if args.output_path is None:
        if args.timestamp:
            args.output_path = os.path.join(args.result_dir, f'recall_evaluation_{args.approach}_{args.timestamp}.json')
        else:
            args.output_path = os.path.join(args.result_dir, f'recall_evaluation_{args.approach}.json')
    
    # Create result directory if needed
    os.makedirs(args.result_dir, exist_ok=True)
    
    print(f"\nConfiguration:")
    print(f"  Approach:      {args.approach}")
    print(f"  Model:         {args.model_name}")
    print(f"  Data Path:     {args.data_path}")
    print(f"  Result Dir:    {args.result_dir}")
    print(f"  Output Path:   {args.output_path}")
    
    # Run pipeline if requested
    if args.run_pipeline:
        if args.approach == 'baseline':
            run_baseline_pipeline(
                args.data_path, 
                args.DB_schema_path, 
                args.result_dir,
                args.model_name,
                args.US_model_name,
                args.patience
            )
        else:
            run_finetuned_pipeline(
                args.data_path,
                args.DB_schema_path,
                args.result_dir,
                args.finetuned_model,
                args.US_model_name
            )
    
    # Evaluate
    if args.approach == 'baseline':
        results = evaluate_baseline_recall(args.result_dir, args.data_path, args.patience)
    else:
        results = evaluate_finetuned_recall(args.result_dir, args.data_path)
    
    if results is None:
        print("\nERROR: Evaluation failed. Check that the required files exist.")
        sys.exit(1)
    
    # Compute statistics
    stats = compute_statistics(results)
    
    # Print results
    print_results(results, stats, args.approach)
    
    # Save results
    save_results(results, stats, args.output_path, args.approach)
    
    print(f"\n✓ Evaluation complete!")


if __name__ == "__main__":
    main()
