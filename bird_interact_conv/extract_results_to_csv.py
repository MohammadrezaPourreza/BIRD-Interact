#!/usr/bin/env python3
"""
Script to extract results from BIRD-Interact conversation results and create a CSV file.
"""

import json
import csv
import os
import argparse
from pathlib import Path
from typing import Dict, List, Optional

def load_jsonl(file_path: str) -> List[Dict]:
    """Load a JSONL file and return a list of dictionaries."""
    data = []
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            print(f"Warning: Failed to parse line in {file_path}: {e}")
                            continue
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
    return data

def extract_sql_query(record, preference_order=['debug', 'original']):
    """Extract SQL query from record, preferring debug version if available"""
    if not record:
        return ""
    
    # Handle both single record and list formats for backward compatibility
    if isinstance(record, list):
        if len(record) > 0:
            record = record[0]
        else:
            return ""
    
    if not isinstance(record, dict):
        return ""
    
    # Look for predicted SQL queries
    if 'pred_sqls' in record and isinstance(record['pred_sqls'], list):
        pred_sqls = record['pred_sqls']
        if len(pred_sqls) > 0:
            return pred_sqls[-1].strip() if pred_sqls[-1] else ""  # Take the last prediction
    
    # Fallback to other possible fields
    for field in ['final_query', 'predicted_sql', 'query', 'sql']:
        if field in record and record[field]:
            return record[field].strip()
    
    return ""

def extract_ground_truth_query(record):
    """Extract ground truth SQL query from sol_sql field"""
    if not record.get('sol_sql'):
        return ""
    
    sol_sql = record['sol_sql']
    if isinstance(sol_sql, list) and len(sol_sql) > 0:
        return sol_sql[0].strip() if sol_sql[0] else ""
    elif isinstance(sol_sql, str):
        return sol_sql.strip()
    else:
        return ""

def extract_followup_data(record):
    """Extract follow-up question and ground truth SQL from follow_up field"""
    followup_query = ""
    followup_gt_sql = ""
    
    if record.get('follow_up'):
        followup = record['follow_up']
        if isinstance(followup, dict):
            followup_query = followup.get('query', '').strip()
            followup_sol_sql = followup.get('sol_sql', '')
            if isinstance(followup_sol_sql, str):
                followup_gt_sql = followup_sol_sql.strip()
            elif isinstance(followup_sol_sql, list) and len(followup_sol_sql) > 0:
                followup_gt_sql = followup_sol_sql[0].strip() if followup_sol_sql[0] else ""
    
    return followup_query, followup_gt_sql

def extract_label_from_output(data: List[Dict]) -> Optional[str]:
    """Extract label/status from output files."""
    if not data:
        return None
    
    for item in data:
        if isinstance(item, dict):
            # In BIRD-Interact output files, status is the main field we're looking for
            if 'status' in item:
                return item['status']
            elif 'label' in item:
                return item['label']
            elif 'result' in item:
                return item['result']
            elif 'success' in item:
                return 'success' if item['success'] else 'failed'
            elif 'execution_success' in item:
                return 'success' if item['execution_success'] else 'failed'
            elif 'error' in item:
                return 'failed' if item['error'] else 'success'
    
    return None

def extract_metadata(data: List[Dict]) -> Dict:
    """Extract metadata like instance_id and database from JSONL data."""
    metadata = {'instance_id': None, 'database': None, 'query_text': None}
    
    if not data:
        return metadata
    
    for item in data:
        if isinstance(item, dict):
            if 'instance_id' in item:
                metadata['instance_id'] = item['instance_id']
            if 'selected_database' in item:
                metadata['database'] = item['selected_database']
            elif 'database' in item:
                metadata['database'] = item['database']
            if 'query' in item and isinstance(item['query'], str):
                metadata['query_text'] = item['query']
    
    return metadata

def get_final_query_and_label(model_dir: Path) -> tuple:
    """Get the final query and its label, preferring debug versions if they exist."""
    
    # Priority order: debug > original
    sql_files = [
        model_dir / 'sql_results_debug.jsonl',
        model_dir / 'sql_results.jsonl'
    ]
    
    output_files = [
        model_dir / 'sql_results_debug_output_with_status.jsonl',
        model_dir / 'sql_results_output_with_status.jsonl'
    ]
    
    final_query = None
    label = None
    
    # Try to get the final query
    for sql_file in sql_files:
        if sql_file.exists():
            data = load_jsonl(str(sql_file))
            final_query = extract_sql_query(data)
            if final_query:
                break
    
    # Try to get the label from corresponding output file
    for output_file in output_files:
        if output_file.exists():
            data = load_jsonl(str(output_file))
            label = extract_label_from_output(data)
            if label:
                break
    
    return final_query, label

def get_followup_query_and_label(model_dir: Path) -> tuple:
    """Get the follow-up query and its label, preferring debug versions if they exist."""
    
    # Priority order: debug > original
    sql_files = [
        model_dir / 'sql_results_fu_debug.jsonl',
        model_dir / 'sql_results_fu.jsonl'
    ]
    
    output_files = [
        model_dir / 'sql_results_fu_debug_output_with_status.jsonl',
        model_dir / 'sql_results_fu_output_with_status.jsonl'
    ]
    
    followup_query = None
    followup_label = None
    
    # Try to get the follow-up query
    for sql_file in sql_files:
        if sql_file.exists():
            data = load_jsonl(str(sql_file))
            followup_query = extract_sql_query(data)
            if followup_query:
                break
    
    # Try to get the label from corresponding output file
    for output_file in output_files:
        if output_file.exists():
            data = load_jsonl(str(output_file))
            followup_label = extract_label_from_output(data)
            if followup_label:
                break
    
    return followup_query, followup_label

def process_model_results(model_dir: Path) -> List[Dict]:
    """Process results for a single model and return extracted data as list of records."""
    
    print(f"Processing {model_dir.name}...")
    
    # Load all relevant files
    files_data = {}
    file_names = [
        'sql_results.jsonl',
        'sql_results_debug.jsonl', 
        'sql_results_output_with_status.jsonl',
        'sql_results_debug_output_with_status.jsonl',
        'sql_results_fu.jsonl',
        'sql_results_fu_debug.jsonl',
        'sql_results_fu_output_with_status.jsonl',
        'sql_results_fu_debug_output_with_status.jsonl'
    ]
    
    for filename in file_names:
        file_path = model_dir / filename
        if file_path.exists():
            files_data[filename] = load_jsonl(str(file_path))
        else:
            files_data[filename] = []
    
    # Get the number of instances (should be same across all files)
    num_instances = 0
    for filename, data in files_data.items():
        if data and len(data) > num_instances:
            num_instances = len(data)
    
    results = []
    
    # Process each instance
    for i in range(num_instances):
        result = {'model': model_dir.name}
        
        # Extract metadata from the main query file
        main_data = files_data.get('sql_results.jsonl', [])
        if i < len(main_data):
            metadata = extract_metadata([main_data[i]])
            result.update(metadata)
        
        # Get final query (prefer debug version if available)
        final_query = None
        label = None
        
        # Try debug version first
        debug_data = files_data.get('sql_results_debug.jsonl', [])
        debug_output_data = files_data.get('sql_results_debug_output_with_status.jsonl', [])
        
        if i < len(debug_data) and debug_data[i]:
            final_query = extract_sql_query(debug_data[i])
        
        if i < len(debug_output_data) and debug_output_data[i]:
            label = extract_label_from_output([debug_output_data[i]])
        
        # Fallback to original if debug not available
        if not final_query:
            original_data = files_data.get('sql_results.jsonl', [])
            if i < len(original_data):
                final_query = extract_sql_query(original_data[i])
        
        if not label:
            original_output_data = files_data.get('sql_results_output_with_status.jsonl', [])
            if i < len(original_output_data):
                label = extract_label_from_output([original_output_data[i]])
        
        # Get follow-up query (prefer debug version)
        followup_query = None
        followup_label = None
        
        fu_debug_data = files_data.get('sql_results_fu_debug.jsonl', [])
        fu_debug_output_data = files_data.get('sql_results_fu_debug_output_with_status.jsonl', [])
        
        if i < len(fu_debug_data) and fu_debug_data[i]:
            followup_query = extract_sql_query(fu_debug_data[i])
        
        if i < len(fu_debug_output_data) and fu_debug_output_data[i]:
            followup_label = extract_label_from_output([fu_debug_output_data[i]])
        
        # Fallback to original follow-up
        if not followup_query:
            fu_data = files_data.get('sql_results_fu.jsonl', [])
            if i < len(fu_data):
                followup_query = extract_sql_query(fu_data[i])
        
        if not followup_label:
            fu_output_data = files_data.get('sql_results_fu_output_with_status.jsonl', [])
            if i < len(fu_output_data):
                followup_label = extract_label_from_output([fu_output_data[i]])
        
        # Get ground truth queries from sol_sql and follow_up fields
        ground_truth_query = None
        ground_truth_followup_query = None
        followup_question = None
        
        # Extract ground truth from main data
        main_data = files_data.get('sql_results.jsonl', [])
        if i < len(main_data) and main_data[i]:
            ground_truth_query = extract_ground_truth_query(main_data[i])
            followup_question, ground_truth_followup_query = extract_followup_data(main_data[i])
            
        # If we don't have followup_query from predicted results, use the followup question
        if not followup_query and followup_question:
            followup_query = followup_question
        
        # Add all extracted data to result
        result.update({
            'final_query': final_query,
            'ground_truth_query': ground_truth_query,
            'label': label,
            'followup_query': followup_query,
            'ground_truth_followup_query': ground_truth_followup_query,
            'followup_label': followup_label
        })
        
        results.append(result)
    
    return results

def main():
    parser = argparse.ArgumentParser(description='Extract BIRD-Interact results to CSV')
    parser.add_argument('--results_dir', 
                       default='/usr/local/google/home/pourreza/Research/BIRD-Interact/bird_interact_conv/results/patience_3',
                       help='Path to the results directory')
    parser.add_argument('--output_csv', 
                       default='bird_interact_results.csv',
                       help='Output CSV file name')
    
    args = parser.parse_args()
    
    results_dir = Path(args.results_dir)
    
    if not results_dir.exists():
        print(f"Error: Results directory {results_dir} does not exist")
        return
    
    # Find all model directories
    model_dirs = [d for d in results_dir.iterdir() if d.is_dir()]
    
    if not model_dirs:
        print(f"No model directories found in {results_dir}")
        return
    
    print(f"Found {len(model_dirs)} model directories: {[d.name for d in model_dirs]}")
    
    # Process each model
    all_results = []
    for model_dir in model_dirs:
        try:
            model_results = process_model_results(model_dir)
            all_results.extend(model_results)  # Extend instead of append since we get a list
        except Exception as e:
            print(f"Error processing {model_dir.name}: {e}")
            continue
    
    if not all_results:
        print("No results extracted")
        return
    
    # Write to CSV
    fieldnames = [
        'model',
        'instance_id',
        'database', 
        'query_text',
        'final_query',
        'ground_truth_query', 
        'label',
        'followup_query',
        'ground_truth_followup_query',
        'followup_label'
    ]
    
    output_path = Path(args.output_csv)
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)
    
    print(f"Results written to {output_path}")
    print(f"Extracted {len(all_results)} total records from {len(model_dirs)} models")
    
    # Print summary by model
    models_summary = {}
    for result in all_results:
        model = result['model']
        if model not in models_summary:
            models_summary[model] = {
                'total': 0,
                'final_queries': 0,
                'followup_queries': 0,
                'successful': 0,
                'followup_successful': 0
            }
        
        models_summary[model]['total'] += 1
        if result.get('final_query'):
            models_summary[model]['final_queries'] += 1
        if result.get('followup_query'):
            models_summary[model]['followup_queries'] += 1
        if result.get('label') == 'success':
            models_summary[model]['successful'] += 1
        if result.get('followup_label') == 'success':
            models_summary[model]['followup_successful'] += 1
    
    for model, stats in models_summary.items():
        print(f"\n{model}:")
        print(f"  Total instances: {stats['total']}")
        print(f"  Final queries extracted: {stats['final_queries']}")
        print(f"  Follow-up queries extracted: {stats['followup_queries']}")
        print(f"  Successful executions: {stats['successful']}")
        print(f"  Successful follow-up executions: {stats['followup_successful']}")

if __name__ == '__main__':
    main()
