#!/usr/bin/env bash
# Compare disambiguation recall between baseline and finetuned approaches

set -e

#####################################
# Configuration
#####################################

# Generate timestamp for this run
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

patience=3
US_model_name="gemini-2.0-flash"
system_model_name="gemini-2.5-pro"
finetuned_model="projects/618488765595/locations/us-central1/endpoints/897266359451254784"
project_root="/app/"
finetuned_result_dir="${project_root}/bird_interact_conv/results/batch_disambiguation/gemini-2.5-pro_20251016_123928/"

data_path="${project_root}/bird_interact_conv/data/bird-interact-lite/bird_interact_data.jsonl"
DB_schema_path="${project_root}/bird_interact_conv/data/bird-interact-lite/[[DB_name]]/[[DB_name]]_schema.txt"

echo "=========================================="
echo "Disambiguation Recall Comparison"
echo "=========================================="
echo "Run Timestamp:   ${TIMESTAMP}"
echo "Baseline Model:  ${system_model_name}"
echo "Finetuned Model: ${finetuned_model}"
echo "User Simulator:  ${US_model_name}"
echo "=========================================="

# Option 1: Evaluate existing results (default)
# Option 2: Run pipelines first (use --run_pipeline flag)

RUN_PIPELINE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --run_pipeline)
            RUN_PIPELINE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--run_pipeline]"
            exit 1
            ;;
    esac
done

#####################################
# Evaluate Baseline Approach
#####################################

echo ""
echo "=========================================="
echo "1. Evaluating BASELINE Approach"
echo "=========================================="

baseline_result_dir="${project_root}/bird_interact_conv/results/patience_${patience}/${system_model_name}/"
baseline_output="${baseline_result_dir}/recall_evaluation_baseline_${TIMESTAMP}.json"

if [ "$RUN_PIPELINE" = true ]; then
    python ${project_root}/bird_interact_conv/evaluate_disambiguation_recall.py \
        --approach baseline \
        --model_name ${system_model_name} \
        --US_model_name ${US_model_name} \
        --data_path ${data_path} \
        --DB_schema_path ${DB_schema_path} \
        --result_dir ${baseline_result_dir} \
        --output_path ${baseline_output} \
        --timestamp ${TIMESTAMP} \
        --patience ${patience} \
        --project_root ${project_root} \
        --run_pipeline
else
    python ${project_root}/bird_interact_conv/evaluate_disambiguation_recall.py \
        --approach baseline \
        --model_name ${system_model_name} \
        --data_path ${data_path} \
        --result_dir ${baseline_result_dir} \
        --output_path ${baseline_output} \
        --timestamp ${TIMESTAMP} \
        --patience ${patience} \
        --project_root ${project_root}
fi

#####################################
# Evaluate Finetuned Approach
#####################################

echo ""
echo "=========================================="
echo "2. Evaluating FINETUNED Approach"
echo "=========================================="

finetuned_output="${finetuned_result_dir}/recall_evaluation_finetuned_${TIMESTAMP}.json"

if [ "$RUN_PIPELINE" = true ]; then
    python ${project_root}/bird_interact_conv/evaluate_disambiguation_recall.py \
        --approach finetuned \
        --model_name ${system_model_name} \
        --finetuned_model ${finetuned_model} \
        --US_model_name ${US_model_name} \
        --data_path ${data_path} \
        --DB_schema_path ${DB_schema_path} \
        --result_dir ${finetuned_result_dir} \
        --output_path ${finetuned_output} \
        --timestamp ${TIMESTAMP} \
        --project_root ${project_root} \
        --run_pipeline
else
    python ${project_root}/bird_interact_conv/evaluate_disambiguation_recall.py \
        --approach finetuned \
        --model_name ${system_model_name} \
        --finetuned_model ${finetuned_model} \
        --data_path ${data_path} \
        --result_dir ${finetuned_result_dir} \
        --output_path ${finetuned_output} \
        --timestamp ${TIMESTAMP} \
        --project_root ${project_root}
fi

#####################################
# Generate Comparison Report
#####################################

echo ""
echo "=========================================="
echo "3. Generating Comparison Report"
echo "=========================================="

comparison_output="${project_root}/bird_interact_conv/results/disambiguation_comparison_${TIMESTAMP}.json"

python ${project_root}/bird_interact_conv/generate_comparison_report.py \
    --baseline_results ${baseline_output} \
    --finetuned_results ${finetuned_output} \
    --output_path ${comparison_output}

echo ""
echo "=========================================="
echo "✓ Comparison Complete!"
echo "=========================================="
echo "Run Timestamp:      ${TIMESTAMP}"
echo "Baseline results:   ${baseline_output}"
echo "Finetuned results:  ${finetuned_output}"
echo "Comparison report:  ${comparison_output}"
echo ""
