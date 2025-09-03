#!/usr/bin/env python3
"""
Script to merge bird_interact_data.jsonl with bird_interact_gt_kg_testcases_0606.jsonl
by matching on instance_id and adding missing fields from the ground truth file.
"""

import json
import os
from typing import Dict, Any

def load_jsonl(filepath: str) -> Dict[str, Any]:
    """Load JSONL file into a dictionary keyed by instance_id"""
    data = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                instance_id = record.get('instance_id')
                if instance_id:
                    data[instance_id] = record
                else:
                    print(f"Warning: No instance_id found in line {line_num} of {filepath}")
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON in line {line_num} of {filepath}: {e}")
    return data

def merge_records(main_record: Dict[str, Any], gt_record: Dict[str, Any]) -> Dict[str, Any]:
    """Merge main record with ground truth record, prioritizing non-empty GT fields"""
    merged = main_record.copy()
    
    # Fields to update from ground truth if they exist and are not empty
    fields_to_update = ['sol_sql', 'external_knowledge', 'test_cases']
    
    for field in fields_to_update:
        if field in gt_record:
            gt_value = gt_record[field]
            # Update if GT has a non-empty value
            if gt_value is not None and gt_value != [] and gt_value != "":
                merged[field] = gt_value
    
    # Also update follow_up if it exists in GT
    if 'follow_up' in gt_record and gt_record['follow_up']:
        follow_up_gt = gt_record['follow_up']
        if 'follow_up' in merged:
            # Update specific follow_up fields
            if 'sol_sql' in follow_up_gt and follow_up_gt['sol_sql']:
                merged['follow_up']['sol_sql'] = follow_up_gt['sol_sql']
            if 'external_knowledge' in follow_up_gt and follow_up_gt['external_knowledge']:
                merged['follow_up']['external_knowledge'] = follow_up_gt['external_knowledge']
            if 'test_cases' in follow_up_gt and follow_up_gt['test_cases']:
                merged['follow_up']['test_cases'] = follow_up_gt['test_cases']
    
    return merged

def save_jsonl(data: Dict[str, Any], filepath: str):
    """Save dictionary to JSONL file"""
    with open(filepath, 'w', encoding='utf-8') as f:
        for record in data.values():
            json.dump(record, f, ensure_ascii=False)
            f.write('\n')

def main():
    # File paths
    data_dir = '/usr/local/google/home/pourreza/Research/BIRD-Interact/bird_interact_conv/data/bird-interact-lite'
    main_file = os.path.join(data_dir, 'bird_interact_data.jsonl')
    gt_file = os.path.join(data_dir, 'bird_interact_gt_kg_testcases_0606.jsonl')
    output_file = os.path.join(data_dir, 'bird_interact_data_merged.jsonl')
    backup_file = os.path.join(data_dir, 'bird_interact_data_backup.jsonl')
    
    print("Loading main data file...")
    main_data = load_jsonl(main_file)
    print(f"Loaded {len(main_data)} records from main file")
    
    print("Loading ground truth file...")
    gt_data = load_jsonl(gt_file)
    print(f"Loaded {len(gt_data)} records from ground truth file")
    
    # Create backup of original file
    print("Creating backup of original file...")
    import shutil
    shutil.copy2(main_file, backup_file)
    print(f"Backup saved to: {backup_file}")
    
    # Merge data
    print("Merging records...")
    merged_data = {}
    matches = 0
    main_only = 0
    gt_only = 0
    
    # Process all instance_ids from both files
    all_instance_ids = set(main_data.keys()) | set(gt_data.keys())
    
    for instance_id in all_instance_ids:
        if instance_id in main_data and instance_id in gt_data:
            # Both files have this instance_id - merge them
            merged_data[instance_id] = merge_records(main_data[instance_id], gt_data[instance_id])
            matches += 1
        elif instance_id in main_data:
            # Only in main file
            merged_data[instance_id] = main_data[instance_id]
            main_only += 1
            print(f"Warning: instance_id '{instance_id}' found only in main file")
        else:
            # Only in GT file
            merged_data[instance_id] = gt_data[instance_id]
            gt_only += 1
            print(f"Warning: instance_id '{instance_id}' found only in ground truth file")
    
    print("Merge statistics:")
    print(f"  Matched records: {matches}")
    print(f"  Main-only records: {main_only}")
    print(f"  GT-only records: {gt_only}")
    print(f"  Total merged records: {len(merged_data)}")
    
    # Save merged data
    print(f"Saving merged data to: {output_file}")
    save_jsonl(merged_data, output_file)
    
    # Replace original file with merged data
    print("Replacing original file with merged data...")
    shutil.move(output_file, main_file)
    
    print("Merge completed successfully!")
    print(f"Original file backed up to: {backup_file}")
    print(f"Merged data saved to: {main_file}")
    
    # Show example of what was merged
    if matches > 0:
        sample_id = next(iter(gt_data.keys()))
        if sample_id in main_data:
            print(f"\nExample merge for instance_id '{sample_id}':")
            print(f"  sol_sql field updated: {'Yes' if gt_data[sample_id].get('sol_sql') else 'No'}")
            print(f"  external_knowledge field updated: {'Yes' if gt_data[sample_id].get('external_knowledge') else 'No'}")
            print(f"  test_cases field updated: {'Yes' if gt_data[sample_id].get('test_cases') else 'No'}")

if __name__ == "__main__":
    main()
