#!/bin/bash

# Consistency-based BIRD-Interact Experiment Launcher
# This script runs experiments using the new consistency-based approach

set -e

# Default parameters
MODEL="gpt-4"
API_PROVIDER="openai"
SAMPLES=10
CONFIDENCE_THRESHOLD=0.6
PATIENCE=3
MAX_WORKERS=10
PHASES="amb debug follow"
OUTPUT_DIR="./results/consistency"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --model)
            MODEL="$2"
            shift 2
            ;;
        --api-provider)
            API_PROVIDER="$2"
            shift 2
            ;;
        --samples)
            SAMPLES="$2"
            shift 2
            ;;
        --confidence-threshold)
            CONFIDENCE_THRESHOLD="$2"
            shift 2
            ;;
        --patience)
            PATIENCE="$2"
            shift 2
            ;;
        --max-workers)
            MAX_WORKERS="$2"
            shift 2
            ;;
        --phases)
            PHASES="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help)
            echo "Consistency-based BIRD-Interact Experiment Launcher"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --model MODEL                  Model name (default: gpt-4)"
            echo "  --api-provider PROVIDER        API provider: openai/anthropic/google (default: openai)"
            echo "  --samples N                    Number of SQL samples for consistency (default: 10)"
            echo "  --confidence-threshold THRESH  Confidence threshold for accepting SQL (default: 0.6)"
            echo "  --patience N                   Maximum clarification turns (default: 3)"
            echo "  --max-workers N                Parallel API workers (default: 10)"
            echo "  --phases PHASES                Phases to run: 'amb debug follow' (default: all)"
            echo "  --output-dir DIR               Output directory (default: ./results/consistency)"
            echo "  --help                         Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --model gpt-4 --samples 15 --confidence-threshold 0.7"
            echo "  $0 --model claude-3-sonnet --api-provider anthropic --samples 5"
            echo "  $0 --model gemini-pro --api-provider google --phases 'amb debug'"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Set up environment
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
cd bird_interact_conv

# Create experiment name with timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
EXPERIMENT_NAME="${MODEL//\//_}_consistency_${TIMESTAMP}"

echo "=========================================="
echo "Consistency-based BIRD-Interact Experiment"
echo "=========================================="
echo "Model: $MODEL"
echo "API Provider: $API_PROVIDER"
echo "Samples: $SAMPLES"
echo "Confidence Threshold: $CONFIDENCE_THRESHOLD"
echo "Patience: $PATIENCE"
echo "Phases: $PHASES"
echo "Experiment Name: $EXPERIMENT_NAME"
echo "Output Directory: $OUTPUT_DIR"
echo "=========================================="

# Check if required data exists
if [ ! -f "data/bird-interact-lite/instances.jsonl" ]; then
    echo "Error: Required data file not found: data/bird-interact-lite/instances.jsonl"
    echo "Please ensure the BIRD-Interact dataset is properly set up."
    exit 1
fi

# Run the consistency experiment
python code/run_consistency_experiment.py \
    --model "$MODEL" \
    --api_provider "$API_PROVIDER" \
    --samples "$SAMPLES" \
    --confidence_threshold "$CONFIDENCE_THRESHOLD" \
    --patience "$PATIENCE" \
    --max_workers "$MAX_WORKERS" \
    --phases $PHASES \
    --output_dir "$OUTPUT_DIR" \
    --experiment_name "$EXPERIMENT_NAME"

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "Experiment completed successfully!"
    echo "Results saved to: ${OUTPUT_DIR}/${EXPERIMENT_NAME}"
    echo "=========================================="
    
    # Show summary if available
    SUMMARY_FILE="${OUTPUT_DIR}/${EXPERIMENT_NAME}/experiment_summary.json"
    if [ -f "$SUMMARY_FILE" ]; then
        echo ""
        echo "Experiment Summary:"
        echo "==================="
        python3 -c "
import json
import sys
try:
    with open('$SUMMARY_FILE') as f:
        summary = json.load(f)
    print(f'Model: {summary[\"model_name\"]}')
    print(f'Samples: {summary[\"samples\"]}')
    print(f'Confidence Threshold: {summary[\"confidence_threshold\"]}')
    print(f'Experiment Directory: {summary[\"experiment_name\"]}')
    print()
    print('Generated Files:')
    for phase, files in summary.get(\"files\", {}).items():
        print(f'  {phase.upper()} Phase:')
        for file_type, info in files.items():
            status = '✓' if info['exists'] and info['size'] > 0 else '✗'
            size_kb = info['size'] // 1024 if info['size'] > 0 else 0
            print(f'    {status} {file_type}: {size_kb}KB')
except Exception as e:
    print(f'Could not read summary: {e}')
"
    fi
else
    echo ""
    echo "=========================================="
    echo "Experiment failed!"
    echo "Check the logs for details."
    echo "=========================================="
    exit 1
fi
