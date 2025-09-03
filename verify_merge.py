#!/usr/bin/env python3
"""
Verification script to check that the merge was successful
"""

import json

def verify_merge():
    filepath = 'bird_interact_conv/data/bird-interact-lite/bird_interact_data.jsonl'
    
    stats = {
        'total_records': 0,
        'records_with_sol_sql': 0,
        'records_with_external_knowledge': 0,
        'records_with_test_cases': 0,
        'records_with_empty_sol_sql': 0,
        'records_with_empty_external_knowledge': 0,
        'follow_up_with_sol_sql': 0,
        'follow_up_with_external_knowledge': 0
    }
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            record = json.loads(line)
            stats['total_records'] += 1
            
            # Check sol_sql field
            if 'sol_sql' in record and record['sol_sql']:
                stats['records_with_sol_sql'] += 1
            else:
                stats['records_with_empty_sol_sql'] += 1
            
            # Check external_knowledge field
            if 'external_knowledge' in record and record['external_knowledge']:
                stats['records_with_external_knowledge'] += 1
            else:
                stats['records_with_empty_external_knowledge'] += 1
                
            # Check test_cases field
            if 'test_cases' in record and record['test_cases']:
                stats['records_with_test_cases'] += 1
                
            # Check follow_up fields
            if 'follow_up' in record and record['follow_up']:
                follow_up = record['follow_up']
                if 'sol_sql' in follow_up and follow_up['sol_sql']:
                    stats['follow_up_with_sol_sql'] += 1
                if 'external_knowledge' in follow_up and follow_up['external_knowledge']:
                    stats['follow_up_with_external_knowledge'] += 1
    
    print("Merge Verification Results:")
    print("=" * 40)
    for key, value in stats.items():
        print(f"{key.replace('_', ' ').title()}: {value}")
        
    print("\nSuccess Rates:")
    print("=" * 20)
    print(f"Sol_sql populated: {stats['records_with_sol_sql']}/{stats['total_records']} ({100*stats['records_with_sol_sql']/stats['total_records']:.1f}%)")
    print(f"External_knowledge populated: {stats['records_with_external_knowledge']}/{stats['total_records']} ({100*stats['records_with_external_knowledge']/stats['total_records']:.1f}%)")
    print(f"Test_cases populated: {stats['records_with_test_cases']}/{stats['total_records']} ({100*stats['records_with_test_cases']/stats['total_records']:.1f}%)")

if __name__ == "__main__":
    verify_merge()
