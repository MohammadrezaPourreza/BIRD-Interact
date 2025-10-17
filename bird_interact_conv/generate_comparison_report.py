#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generate comparison report between baseline and finetuned disambiguation approaches.
"""

import argparse
import json
import sys


def load_results(filepath):
    """Load evaluation results from JSON file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"ERROR: Invalid JSON in file: {filepath}")
        sys.exit(1)


def generate_comparison(baseline_results, finetuned_results):
    """Generate comparison statistics."""
    
    baseline_stats = baseline_results.get("statistics", {})
    finetuned_stats = finetuned_results.get("statistics", {})
    
    comparison = {
        "summary": {
            "baseline": {
                "approach": "Baseline (Iterative)",
                "mean_recall": baseline_stats.get("mean_recall", 0.0),
                "perfect_recall_rate": baseline_stats.get("perfect_recall_rate", 0.0),
                "zero_recall_rate": baseline_stats.get("zero_recall_rate", 0.0),
                "total_instances": baseline_stats.get("total_instances", 0)
            },
            "finetuned": {
                "approach": "Finetuned (Batch)",
                "mean_recall": finetuned_stats.get("mean_recall", 0.0),
                "perfect_recall_rate": finetuned_stats.get("perfect_recall_rate", 0.0),
                "zero_recall_rate": finetuned_stats.get("zero_recall_rate", 0.0),
                "total_instances": finetuned_stats.get("total_instances", 0)
            }
        },
        "improvements": {
            "mean_recall_improvement": finetuned_stats.get("mean_recall", 0.0) - baseline_stats.get("mean_recall", 0.0),
            "perfect_recall_improvement": finetuned_stats.get("perfect_recall_rate", 0.0) - baseline_stats.get("perfect_recall_rate", 0.0),
            "zero_recall_reduction": baseline_stats.get("zero_recall_rate", 0.0) - finetuned_stats.get("zero_recall_rate", 0.0)
        },
        "detailed_comparison": {
            "baseline_statistics": baseline_stats,
            "finetuned_statistics": finetuned_stats
        }
    }
    
    # Per-instance comparison
    baseline_instances = baseline_results.get("per_instance_results", {})
    finetuned_instances = finetuned_results.get("per_instance_results", {})
    
    instance_comparisons = {}
    all_instances = set(baseline_instances.keys()) | set(finetuned_instances.keys())
    
    for instance_id in all_instances:
        baseline_data = baseline_instances.get(instance_id, {})
        finetuned_data = finetuned_instances.get(instance_id, {})
        
        baseline_recall = baseline_data.get("recall", 0.0)
        finetuned_recall = finetuned_data.get("recall", 0.0)
        
        instance_comparisons[instance_id] = {
            "baseline_recall": baseline_recall,
            "finetuned_recall": finetuned_recall,
            "improvement": finetuned_recall - baseline_recall,
            "baseline_addressed": baseline_data.get("addressed_ambiguities", 0),
            "finetuned_addressed": finetuned_data.get("addressed_ambiguities", 0),
            "total_ambiguities": baseline_data.get("total_ambiguities", finetuned_data.get("total_ambiguities", 0))
        }
    
    comparison["per_instance_comparison"] = instance_comparisons
    
    # Count improvements/degradations
    improvements = sum(1 for v in instance_comparisons.values() if v["improvement"] > 0)
    degradations = sum(1 for v in instance_comparisons.values() if v["improvement"] < 0)
    same = sum(1 for v in instance_comparisons.values() if v["improvement"] == 0)
    
    comparison["improvement_summary"] = {
        "instances_improved": improvements,
        "instances_degraded": degradations,
        "instances_same": same,
        "improvement_rate": improvements / len(instance_comparisons) if instance_comparisons else 0.0,
        "degradation_rate": degradations / len(instance_comparisons) if instance_comparisons else 0.0
    }
    
    return comparison


def print_comparison_report(comparison):
    """Print formatted comparison report."""
    
    print("\n" + "="*70)
    print("DISAMBIGUATION RECALL COMPARISON REPORT")
    print("="*70)
    
    # Summary
    print("\n1. OVERALL PERFORMANCE SUMMARY")
    print("-"*70)
    
    baseline = comparison["summary"]["baseline"]
    finetuned = comparison["summary"]["finetuned"]
    
    print(f"\n{'Metric':<30} {'Baseline':<20} {'Finetuned':<20}")
    print("-"*70)
    print(f"{'Mean Recall':<30} {baseline['mean_recall']:<20.4f} {finetuned['mean_recall']:<20.4f}")
    print(f"{'Perfect Recall Rate':<30} {baseline['perfect_recall_rate']:<20.2%} {finetuned['perfect_recall_rate']:<20.2%}")
    print(f"{'Zero Recall Rate':<30} {baseline['zero_recall_rate']:<20.2%} {finetuned['zero_recall_rate']:<20.2%}")
    print(f"{'Total Instances':<30} {baseline['total_instances']:<20} {finetuned['total_instances']:<20}")
    
    # Improvements
    print("\n2. IMPROVEMENTS")
    print("-"*70)
    
    improvements = comparison["improvements"]
    
    print(f"Mean Recall Improvement:     {improvements['mean_recall_improvement']:+.4f}")
    print(f"Perfect Recall Improvement:  {improvements['perfect_recall_improvement']:+.2%}")
    print(f"Zero Recall Reduction:       {improvements['zero_recall_reduction']:+.2%}")
    
    # Instance-level summary
    print("\n3. INSTANCE-LEVEL CHANGES")
    print("-"*70)
    
    imp_summary = comparison["improvement_summary"]
    
    print(f"Instances Improved:  {imp_summary['instances_improved']} ({imp_summary['improvement_rate']:.2%})")
    print(f"Instances Degraded:  {imp_summary['instances_degraded']} ({imp_summary['degradation_rate']:.2%})")
    print(f"Instances Same:      {imp_summary['instances_same']}")
    
    # Top improvements
    print("\n4. TOP 5 IMPROVEMENTS")
    print("-"*70)
    
    instance_comp = comparison["per_instance_comparison"]
    sorted_improvements = sorted(
        instance_comp.items(), 
        key=lambda x: x[1]["improvement"], 
        reverse=True
    )[:5]
    
    for instance_id, data in sorted_improvements:
        print(f"\nInstance: {instance_id}")
        print(f"  Baseline Recall:   {data['baseline_recall']:.4f} ({data['baseline_addressed']}/{data['total_ambiguities']})")
        print(f"  Finetuned Recall:  {data['finetuned_recall']:.4f} ({data['finetuned_addressed']}/{data['total_ambiguities']})")
        print(f"  Improvement:       {data['improvement']:+.4f}")
    
    # Top degradations
    print("\n5. TOP 5 DEGRADATIONS")
    print("-"*70)
    
    sorted_degradations = sorted(
        instance_comp.items(), 
        key=lambda x: x[1]["improvement"]
    )[:5]
    
    for instance_id, data in sorted_degradations:
        if data["improvement"] >= 0:
            print("(No degradations found)")
            break
        print(f"\nInstance: {instance_id}")
        print(f"  Baseline Recall:   {data['baseline_recall']:.4f} ({data['baseline_addressed']}/{data['total_ambiguities']})")
        print(f"  Finetuned Recall:  {data['finetuned_recall']:.4f} ({data['finetuned_addressed']}/{data['total_ambiguities']})")
        print(f"  Degradation:       {data['improvement']:+.4f}")
    
    # Distribution comparison
    print("\n6. RECALL DISTRIBUTION COMPARISON")
    print("-"*70)
    
    baseline_dist = comparison["detailed_comparison"]["baseline_statistics"].get("recall_distribution", {})
    finetuned_dist = comparison["detailed_comparison"]["finetuned_statistics"].get("recall_distribution", {})
    
    print(f"\n{'Range':<15} {'Baseline':<15} {'Finetuned':<15} {'Change':<15}")
    print("-"*60)
    
    for bin_name in ["0.0", "0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0", "1.0"]:
        baseline_count = baseline_dist.get(bin_name, 0)
        finetuned_count = finetuned_dist.get(bin_name, 0)
        change = finetuned_count - baseline_count
        print(f"{bin_name:<15} {baseline_count:<15} {finetuned_count:<15} {change:+<15}")
    
    print("\n" + "="*70)


def save_comparison(comparison, output_path):
    """Save comparison to JSON file."""
    with open(output_path, 'w') as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    print(f"\nComparison saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate comparison report between baseline and finetuned approaches.'
    )
    
    parser.add_argument('--baseline_results', type=str, required=True,
                        help='Path to baseline evaluation results JSON')
    
    parser.add_argument('--finetuned_results', type=str, required=True,
                        help='Path to finetuned evaluation results JSON')
    
    parser.add_argument('--output_path', type=str, required=True,
                        help='Path to save comparison report JSON')
    
    args = parser.parse_args()
    
    # Load results
    print("Loading evaluation results...")
    baseline_results = load_results(args.baseline_results)
    finetuned_results = load_results(args.finetuned_results)
    
    # Generate comparison
    print("Generating comparison...")
    comparison = generate_comparison(baseline_results, finetuned_results)
    
    # Print report
    print_comparison_report(comparison)
    
    # Save comparison
    save_comparison(comparison, args.output_path)
    
    print("\n✓ Comparison report generated successfully!")


if __name__ == "__main__":
    main()
