#!/usr/bin/env python3
"""
Script to calculate final performance scores for BIRD-Interact results.

Scoring Logic:
- Clarification, first try (solved without debugging): 0.7 points
- Clarification, after debugging (solved on second try): 0.5 points  
- Follow-up, first try (solved without debugging): 0.3 points
- Follow-up, after debugging (solved on second try): 0.2 points
"""

import json
import os
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

def load_jsonl(file_path: str) -> List[Dict]:
    """Load a JSONL file and return a list of dictionaries."""
    data = []
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line:
                        try:
                            data.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            print(f"Warning: Failed to parse line {line_num} in {file_path}: {e}")
                            continue
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
    return data

def extract_status(record: Dict) -> Optional[str]:
    """Extract status from a record. Returns 'success' or 'failed' or None."""
    if not record:
        return None
    
    # Check various possible status fields
    if 'status' in record:
        status = record['status']
        if isinstance(status, str):
            return status.lower()
        elif isinstance(status, bool):
            return 'success' if status else 'failed'
    
    # Check other possible fields
    for field in ['result', 'success', 'execution_success']:
        if field in record:
            value = record[field]
            if isinstance(value, bool):
                return 'success' if value else 'failed'
            elif isinstance(value, str):
                return value.lower()
    
    # Check if there's an error field
    if 'error' in record:
        error = record['error']
        if error is None or error == "" or error == False:
            return 'success'
        else:
            return 'failed'
    
    return None

def analyze_model_performance(model_dir: Path) -> Dict:
    """Analyze performance for a single model directory."""
    
    print(f"\nAnalyzing {model_dir.name}...")
    
    # Define file mappings - support both original and batch disambiguation naming
    # Try batch disambiguation files first, then fall back to original naming
    files_info = {
        'clarification_first': {
            'sql_file': ['sql_results.jsonl', 'sql_results_interaction.jsonl'],
            'status_file': ['sql_results_output_with_status.jsonl', 'sql_results_interaction_output_with_status.jsonl']
        },
        'clarification_debug': {
            'sql_file': ['sql_results_debug.jsonl', 'sql_results_interaction_debug.jsonl'], 
            'status_file': ['sql_results_debug_output_with_status.jsonl', 'sql_results_interaction_debug_output_with_status.jsonl']
        },
        'followup_first': {
            'sql_file': ['sql_results_fu.jsonl', 'sql_results_interaction_fu.jsonl'],
            'status_file': ['sql_results_fu_output_with_status.jsonl', 'sql_results_interaction_fu_output_with_status.jsonl']
        },
        'followup_debug': {
            'sql_file': ['sql_results_fu_debug.jsonl', 'sql_results_interaction_fu_debug.jsonl'],
            'status_file': ['sql_results_fu_debug_output_with_status.jsonl', 'sql_results_interaction_fu_debug_output_with_status.jsonl']
        }
    }
    
    # Load all files - try multiple possible filenames
    loaded_files = {}
    for category, file_info in files_info.items():
        # Try each possible filename
        sql_data = []
        status_data = []
        sql_exists = False
        status_exists = False
        
        # Try each sql_file option
        for sql_filename in (file_info['sql_file'] if isinstance(file_info['sql_file'], list) else [file_info['sql_file']]):
            sql_path = model_dir / sql_filename
            if sql_path.exists():
                sql_data = load_jsonl(str(sql_path))
                sql_exists = True
                break
        
        # Try each status_file option
        for status_filename in (file_info['status_file'] if isinstance(file_info['status_file'], list) else [file_info['status_file']]):
            status_path = model_dir / status_filename
            if status_path.exists():
                status_data = load_jsonl(str(status_path))
                status_exists = True
                break
        
        loaded_files[category] = {
            'sql_data': sql_data,
            'status_data': status_data,
            'sql_exists': sql_exists,
            'status_exists': status_exists
        }
    
    # Get the number of instances
    max_instances = 0
    for category, data in loaded_files.items():
        max_instances = max(max_instances, len(data['status_data']))
    
    if max_instances == 0:
        print(f"Warning: No instances found for {model_dir.name}")
        # Initialize empty scores with proper structure
        empty_scores = {
            'clarification_first_try': {'count': 0, 'points': 0.0},
            'clarification_after_debug': {'count': 0, 'points': 0.0},
            'followup_first_try': {'count': 0, 'points': 0.0},
            'followup_after_debug': {'count': 0, 'points': 0.0}
        }
        return {
            'model': model_dir.name,
            'total_instances': 0,
            'scores': empty_scores,
            'total_score': 0.0,
            'average_score': 0.0
        }
    
    # Initialize scoring
    scores = {
        'clarification_first_try': {'count': 0, 'points': 0.0},
        'clarification_after_debug': {'count': 0, 'points': 0.0},
        'followup_first_try': {'count': 0, 'points': 0.0},
        'followup_after_debug': {'count': 0, 'points': 0.0}
    }
    
    # Score mapping
    score_values = {
        'clarification_first_try': 0.7,
        'clarification_after_debug': 0.5,
        'followup_first_try': 0.3,
        'followup_after_debug': 0.2
    }
    
    # Analyze each instance
    for i in range(max_instances):
        # Get status for each category
        statuses = {}
        for category in files_info.keys():
            status_data = loaded_files[category]['status_data']
            if i < len(status_data):
                statuses[category] = extract_status(status_data[i])
            else:
                statuses[category] = None
        
        # Apply scoring logic
        
        # Clarification phase
        clarification_first_success = statuses.get('clarification_first') == 'success'
        clarification_debug_success = statuses.get('clarification_debug') == 'success'
        
        if clarification_first_success:
            # Solved on first try
            scores['clarification_first_try']['count'] += 1
            scores['clarification_first_try']['points'] += score_values['clarification_first_try']
        elif clarification_debug_success:
            # Solved after debugging
            scores['clarification_after_debug']['count'] += 1
            scores['clarification_after_debug']['points'] += score_values['clarification_after_debug']
        
        # Follow-up phase
        followup_first_success = statuses.get('followup_first') == 'success'
        followup_debug_success = statuses.get('followup_debug') == 'success'
        
        if followup_first_success:
            # Solved on first try
            scores['followup_first_try']['count'] += 1
            scores['followup_first_try']['points'] += score_values['followup_first_try']
        elif followup_debug_success:
            # Solved after debugging
            scores['followup_after_debug']['count'] += 1
            scores['followup_after_debug']['points'] += score_values['followup_after_debug']
    
    # Calculate totals
    total_score = sum(category['points'] for category in scores.values())
    average_score = total_score / max_instances if max_instances > 0 else 0.0
    
    return {
        'model': model_dir.name,
        'total_instances': max_instances,
        'scores': scores,
        'total_score': total_score,
        'average_score': average_score
    }

def print_detailed_results(results: List[Dict]):
    """Print detailed results for all models."""
    
    print("\n" + "="*80)
    print("BIRD-INTERACT PERFORMANCE ANALYSIS")
    print("="*80)
    
    # Print individual model results
    for result in results:
        model = result['model']
        print(f"\nModel: {model}")
        print("-" * 50)
        print(f"Total instances: {result['total_instances']}")
        print(f"Total score: {result['total_score']:.2f}")
        print(f"Average score per instance: {result['average_score']:.3f}")
        
        print("\nBreakdown by category:")
        scores = result['scores']
        
        # Ensure all required keys exist with default values
        default_score = {'count': 0, 'points': 0.0}
        safe_scores = {
            'clarification_first_try': scores.get('clarification_first_try', default_score),
            'clarification_after_debug': scores.get('clarification_after_debug', default_score),
            'followup_first_try': scores.get('followup_first_try', default_score),
            'followup_after_debug': scores.get('followup_after_debug', default_score)
        }
        
        print(f"  Clarification (first try):     {safe_scores['clarification_first_try']['count']:3d} wins × 0.7 = {safe_scores['clarification_first_try']['points']:5.2f} points")
        print(f"  Clarification (after debug):   {safe_scores['clarification_after_debug']['count']:3d} wins × 0.5 = {safe_scores['clarification_after_debug']['points']:5.2f} points")
        print(f"  Follow-up (first try):         {safe_scores['followup_first_try']['count']:3d} wins × 0.3 = {safe_scores['followup_first_try']['points']:5.2f} points")
        print(f"  Follow-up (after debug):       {safe_scores['followup_after_debug']['count']:3d} wins × 0.2 = {safe_scores['followup_after_debug']['points']:5.2f} points")
        
        # Calculate success rates
        total_clarification_attempts = result['total_instances']
        total_followup_attempts = result['total_instances']
        
        clarification_successes = safe_scores['clarification_first_try']['count'] + safe_scores['clarification_after_debug']['count']
        followup_successes = safe_scores['followup_first_try']['count'] + safe_scores['followup_after_debug']['count']
        
        clarification_rate = (clarification_successes / total_clarification_attempts * 100) if total_clarification_attempts > 0 else 0
        followup_rate = (followup_successes / total_followup_attempts * 100) if total_followup_attempts > 0 else 0
        
        print(f"\nSuccess rates:")
        print(f"  Clarification phase: {clarification_successes}/{total_clarification_attempts} ({clarification_rate:.1f}%)")
        print(f"  Follow-up phase:     {followup_successes}/{total_followup_attempts} ({followup_rate:.1f}%)")
    
    # Print summary comparison
    if len(results) > 1:
        print("\n" + "="*80)
        print("SUMMARY COMPARISON")
        print("="*80)
        
        # Sort by average score
        sorted_results = sorted(results, key=lambda x: x['average_score'], reverse=True)
        
        print(f"{'Rank':<5} {'Model':<25} {'Avg Score':<12} {'Total Score':<12} {'Instances':<10}")
        print("-" * 70)
        
        for rank, result in enumerate(sorted_results, 1):
            print(f"{rank:<5} {result['model']:<25} {result['average_score']:<12.3f} {result['total_score']:<12.2f} {result['total_instances']:<10}")

def main():
    parser = argparse.ArgumentParser(description='Calculate BIRD-Interact final performance scores')
    parser.add_argument('--results_dir', 
                       default='./results',
                       help='Path to the results directory (will scan all subdirectories)')
    parser.add_argument('--specific_dir',
                       help='Specific model directory to analyze (e.g., patience_3/gemini-2.5-pro)')
    
    args = parser.parse_args()
    
    results_dir = Path(args.results_dir)
    
    if not results_dir.exists():
        print(f"Error: Results directory {results_dir} does not exist")
        return
    
    # Find all model directories - search in subdirectories
    model_dirs = []
    
    if args.specific_dir:
        # Analyze specific directory
        specific_path = results_dir / args.specific_dir
        if specific_path.exists() and specific_path.is_dir():
            model_dirs = [specific_path]
        else:
            print(f"Error: Specific directory {specific_path} does not exist")
            return
    else:
        # Scan for all model directories (2 levels deep)
        # Level 1: results/patience_3, results/batch_disambiguation, etc.
        for subdir in results_dir.iterdir():
            if subdir.is_dir():
                # Level 2: results/patience_3/gemini-2.5-pro, etc.
                for model_dir in subdir.iterdir():
                    if model_dir.is_dir():
                        # Check if this looks like a results directory (has .jsonl files)
                        jsonl_files = list(model_dir.glob('*.jsonl'))
                        if jsonl_files:
                            model_dirs.append(model_dir)
    
    if not model_dirs:
        print(f"No model directories with results found in {results_dir}")
        print("Looking for directories with .jsonl files...")
        return
    
    print(f"Found {len(model_dirs)} model directories:")
    for d in model_dirs:
        # Get relative path from results_dir
        rel_path = d.relative_to(results_dir)
        print(f"  - {rel_path}")
    
    # Analyze each model
    all_results = []
    for model_dir in sorted(model_dirs):
        try:
            # Use relative path as model name for better identification
            rel_path = model_dir.relative_to(results_dir)
            result = analyze_model_performance(model_dir)
            # Update model name to include the full path
            result['model'] = str(rel_path)
            all_results.append(result)
        except Exception as e:
            print(f"Error analyzing {model_dir.name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    if not all_results:
        print("No results were successfully analyzed")
        return
    
    # Print results
    print_detailed_results(all_results)
    
    # Save results to file
    output_file = results_dir / 'performance_analysis.json'
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"\nDetailed results saved to: {output_file}")
    except PermissionError:
        # Try alternative location
        output_file = Path('performance_analysis.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"\nDetailed results saved to: {output_file}")

if __name__ == '__main__':
    main()