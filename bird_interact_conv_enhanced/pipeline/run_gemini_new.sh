#!/usr/bin/env bash
set -e

#####################################
# BIRD-Interact Experiment Runner
#####################################

# Configuration Parameters
patience=3
US_model_name="gemini-2.0-flash"
system_model_name="gemini-2.5-pro"
project_root="/app/"
log_level="INFO"
experiment_name=""  # Optional: custom experiment name suffix

# Optional: Override with environment variables
patience=${PATIENCE:-$patience}
US_model_name=${US_MODEL_NAME:-$US_model_name}
system_model_name=${SYSTEM_MODEL_NAME:-$system_model_name}
project_root=${PROJECT_ROOT:-$project_root}
log_level=${LOG_LEVEL:-$log_level}
experiment_name=${EXPERIMENT_NAME:-$experiment_name}

echo "=========================================="
echo "BIRD-Interact Experiment Runner"
echo "=========================================="
echo "Configuration:"
echo "  Patience: $patience"
echo "  System Model: $system_model_name"
echo "  User Model: $US_model_name"
echo "  Project Root: $project_root"
echo "  Log Level: $log_level"
if [ -n "$experiment_name" ]; then
    echo "  Experiment Name: $experiment_name"
else
    echo "  Experiment Name: Auto-generated timestamp"
fi
echo "=========================================="

# Build command with optional experiment name
cmd_args=(
    --patience "$patience"
    --system_model_name "$system_model_name"
    --US_model_name "$US_model_name"
    --project_root "$project_root"
    --log_level "$log_level"
)

# Add experiment name if provided
if [ -n "$experiment_name" ]; then
    cmd_args+=(--experiment_name "$experiment_name")
fi

# Run the Python experiment script
python "${project_root}/bird_interact_conv/code/run_experiment.py" "${cmd_args[@]}"

echo "Experiment completed. Check logs for details."
