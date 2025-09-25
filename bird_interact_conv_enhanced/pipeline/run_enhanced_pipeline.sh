#!/usr/bin/env bash
# Enhanced BIRD-Interact Pipeline with SQL Execution Tool
# This script runs the enhanced conversational flow that allows LLMs to execute SQL queries
# during the clarification phase for better understanding and solution refinement.

set -e

#####################################
# Enhanced Configuration Parameters
#####################################

# Basic parameters
patience=3                      # Clarification question budget
max_sql_executions=5           # SQL execution budget (separate from clarification budget)
US_model_name="gpt-4o-mini"   # User simulator model
system_model_name="gpt-4o"    # System model (LLM being evaluated)
project_root="/home/dev/lab/BIRD-Interact"            # Update this to your project root

# Paths
enhanced_dir="${project_root}/bird_interact_conv_enhanced"
result_dir="${enhanced_dir}/results/patience_${patience}_sql_${max_sql_executions}/${system_model_name}/"
mkdir -p "$result_dir"

DB_schema_path="${enhanced_dir}/data/bird-interact-lite/[[DB_name]]/[[DB_name]]_schema.txt"
external_kg_path="${enhanced_dir}/data/bird-interact-lite/[[DB_name]]/[[DB_name]]_kb.jsonl"
data_path="${enhanced_dir}/data/bird-interact-lite/bird_interact_data.jsonl"

echo "🚀 Starting Enhanced BIRD-Interact Pipeline with UV"
echo "📊 Configuration:"
echo "   - Enhanced directory: $enhanced_dir"
echo "   - Clarification budget: $patience turns"
echo "   - SQL execution budget: $max_sql_executions queries"
echo "   - System model: $system_model_name"
echo "   - User simulator: $US_model_name"
echo "   - Results directory: $result_dir"
echo ""

# Navigate to enhanced directory
cd "$enhanced_dir"

# Check if uv environment exists
if [ ! -d ".venv" ]; then
    echo "❌ UV virtual environment not found. Please run 'uv sync' first."
    exit 1
fi

echo "✅ Using UV virtual environment"

# ===========================================: Phase 1 Enhanced Ambiguity Resolution :===========================================
echo "🔍 Phase 1: Enhanced Ambiguity Resolution with SQL Execution Tool"

## Turn 1: Initial system prompt generation
turn_num=1
result_path_prompt="${result_dir}/system_interaction_prompt.jsonl"

# Check if we have previous system interaction results
FILE_PATH="${result_dir}/system_interaction.jsonl"
if [ -f "$FILE_PATH" ]; then
    data_path_system="$FILE_PATH"
else
    data_path_system="$data_path"
fi

echo "   Turn $turn_num: Generating enhanced system prompts..."
uv run python code/infer_api_system_enhanced.py \
    --prompt_path ${data_path_system} \
    --result_path ${result_path_prompt} \
    --user_resp_path ${data_path} \
    --DB_schema_path ${DB_schema_path} \
    --external_kg_path ${external_kg_path} \
    --patience ${patience} \
    --max_sql_executions ${max_sql_executions} \
    --turn_num ${turn_num} \
    --phase amb

if [ ! -s "$result_path_prompt" ]; then
    echo "❌ Error: Empty prompt file generated!"
    exit 1
fi

echo "   Turn $turn_num: Calling LLM API..."
result_path_response="${result_dir}/system_interaction_response.jsonl"
uv run python code/call_api.py \
    --model_name ${system_model_name} \
    --prompt_path ${result_path_prompt} \
    --output_path ${result_path_response}

echo "   Turn $turn_num: Processing enhanced responses with SQL execution..."
result_path_selected_llm="${result_dir}/system_interaction.jsonl"
uv run python code/collect_response_enhanced.py \
    --source_path ${result_path_selected_llm} \
    --response_path ${result_path_response} \
    --result_path ${result_path_selected_llm}

# Continue conversation turns until termination or max turns reached
for ((turn_num=2; turn_num<=15; turn_num++)); do
    echo ""
    echo "   Turn $turn_num: Checking for conversation continuation..."
    
    # Check if conversation should continue by looking for termination flags
    last_response=$(tail -n 1 "${result_dir}/system_interaction.jsonl" | jq -r '.response // empty' 2>/dev/null || echo "")
    
    if [[ "$last_response" == *"</t>"* ]] || [[ "$last_response" == *"```postgresql"* ]]; then
        echo "   ✅ Conversation terminated with final SQL answer"
        break
    fi
    
    # User Simulator Step 1: Parse system response and generate user response
    echo "   Turn $turn_num: User simulator parsing system response..."
    user_1_path="${result_dir}/user_1_interaction.jsonl"
    result_path_prompt="${result_dir}/user_1_interaction_prompt.jsonl"
    
    uv run python code/infer_api_user_1.py \
        --prompt_path ${user_1_path} \
        --result_path ${result_path_prompt} \
        --sys_resp_path ${result_dir}/system_interaction.jsonl \
        --DB_schema_path ${DB_schema_path} \
        --turn_num ${turn_num}
    
    if [ -s "$result_path_prompt" ]; then
        result_path_response="${result_dir}/user_1_interaction_response.jsonl"
        uv run python code/call_api.py \
            --model_name ${US_model_name} \
            --prompt_path ${result_path_prompt} \
            --output_path ${result_path_response}
        
        result_path_selected_llm="${result_dir}/user_1_interaction.jsonl"
        uv run python code/collect_response.py \
            --source_path ${user_1_path} \
            --response_path ${result_path_response} \
            --result_path ${result_path_selected_llm}
    fi
    
    # User Simulator Step 2: Generate final user response
    echo "   Turn $turn_num: User simulator generating response..."
    user_2_path="${result_dir}/user_2_interaction.jsonl"
    result_path_prompt="${result_dir}/user_2_interaction_prompt.jsonl"
    sys_resp_path="${result_dir}/system_interaction.jsonl"
    user_1_resp_path="${result_dir}/user_1_interaction.jsonl"
    
    python ${project_root}/bird_interact_conv_enhanced/code/infer_api_user_2.py \
        --prompt_path ${user_2_path} \
        --result_path ${result_path_prompt} \
        --sys_resp_path ${sys_resp_path} \
        --user_1_resp_path ${user_1_resp_path} \
        --DB_schema_path ${DB_schema_path} \
        --turn_num ${turn_num}
    
    if [ -s "$result_path_prompt" ]; then
        result_path_response="${result_dir}/user_2_interaction_response.jsonl"
        python ${project_root}/bird_interact_conv_enhanced/code/call_api.py \
            --model_name ${US_model_name} \
            --prompt_path ${result_path_prompt} \
            --output_path ${result_path_response}
        
        result_path_selected_llm="${result_dir}/user_2_interaction.jsonl"
        python ${project_root}/bird_interact_conv_enhanced/code/collect_response.py \
            --source_path ${user_2_path} \
            --response_path ${result_path_response} \
            --result_path ${result_path_selected_llm}
    fi
    
    # System response to user input with enhanced SQL capabilities
    echo "   Turn $turn_num: Enhanced system response generation..."
    data_path="${result_dir}/system_interaction.jsonl"
    user_resp_path="${result_dir}/user_2_interaction.jsonl"
    result_path_prompt="${result_dir}/system_interaction_prompt.jsonl"
    
    python ${project_root}/bird_interact_conv_enhanced/code/infer_api_system_enhanced.py \
        --prompt_path ${data_path} \
        --result_path ${result_path_prompt} \
        --user_resp_path ${user_resp_path} \
        --DB_schema_path ${DB_schema_path} \
        --external_kg_path ${external_kg_path} \
        --patience ${patience} \
        --max_sql_executions ${max_sql_executions} \
        --turn_num ${turn_num} \
        --phase amb
    
    if [ ! -s "$result_path_prompt" ]; then
        echo "   ✅ No more prompts generated - conversation complete"
        break
    fi
    
    result_path_response="${result_dir}/system_interaction_response.jsonl"
    python ${project_root}/bird_interact_conv_enhanced/code/call_api.py \
        --model_name ${system_model_name} \
        --prompt_path ${result_path_prompt} \
        --output_path ${result_path_response}
    
    result_path_selected_llm="${result_dir}/system_interaction.jsonl"
    python ${project_root}/bird_interact_conv_enhanced/code/collect_response_enhanced.py \
        --source_path ${result_path_selected_llm} \
        --response_path ${result_path_response} \
        --result_path ${result_path_selected_llm}
done

echo ""
echo "✅ Phase 1 Complete: Enhanced ambiguity resolution with SQL execution"

# ===========================================: SQL Extraction and Evaluation :===========================================
echo ""
echo "📝 Extracting final SQL queries and preparing for evaluation..."

data_path="${result_dir}/system_interaction.jsonl"
result_path_sql="${result_dir}/sql_results.jsonl"

python ${project_root}/bird_interact_conv_enhanced/code/wrap_up_sql.py \
    --data_path ${data_path} \
    --result_path ${result_path_sql}

echo "🔍 Evaluating Phase 1 results..."
jsonl_file="${result_dir}/sql_results.jsonl"
python ${project_root}/evaluation/src/eval_bird_interact_batch.py --jsonl "$jsonl_file"

# ===========================================: Phase 1 Debugging (if needed) :===========================================
echo ""
echo "🐛 Phase 1 Debugging: Enhanced debugging with SQL exploration"

exec_report="${result_dir}/sql_results_output_with_status.jsonl"
data_path="${result_dir}/system_interaction.jsonl"
result_path_prompt="${result_dir}/system_interaction_prompt.jsonl"
phase='debug'

echo "   Generating enhanced debug prompts..."
python ${project_root}/bird_interact_conv_enhanced/code/infer_api_system_enhanced.py \
    --prompt_path ${data_path} \
    --result_path ${result_path_prompt} \
    --user_resp_path ${exec_report} \
    --DB_schema_path ${DB_schema_path} \
    --external_kg_path ${external_kg_path} \
    --patience ${patience} \
    --max_sql_executions ${max_sql_executions} \
    --turn_num 999 \
    --phase ${phase}

if [ -s "$result_path_prompt" ]; then
    echo "   Calling LLM for enhanced debugging..."
    result_path_response="${result_dir}/system_interaction_response.jsonl"
    python ${project_root}/bird_interact_conv_enhanced/code/call_api.py \
        --model_name ${system_model_name} \
        --prompt_path ${result_path_prompt} \
        --output_path ${result_path_response}
    
    result_path_selected_llm="${result_dir}/system_interaction.jsonl"
    python ${project_root}/bird_interact_conv_enhanced/code/collect_response_enhanced.py \
        --source_path ${result_path_selected_llm} \
        --response_path ${result_path_response} \
        --result_path ${result_path_selected_llm}
fi

# Extract and evaluate debug results
data_path="${result_dir}/system_interaction.jsonl"
result_path_sql="${result_dir}/sql_results_debug.jsonl"

python ${project_root}/bird_interact_conv_enhanced/code/wrap_up_sql.py \
    --data_path ${data_path} \
    --result_path ${result_path_sql}

echo "🔍 Evaluating debug results..."
jsonl_file="${result_dir}/sql_results_debug.jsonl"
python ${project_root}/evaluation/src/eval_bird_interact_batch.py --jsonl "$jsonl_file"

# ===========================================: Phase 2 Enhanced Follow-up :===========================================
echo ""
echo "❓ Phase 2: Enhanced Follow-up Questions with SQL Exploration"

exec_report="${result_dir}/sql_results_debug_output_with_status.jsonl"
data_path="${result_dir}/system_interaction.jsonl"
result_path_prompt="${result_dir}/system_interaction_prompt.jsonl"
phase='follow'

echo "   Generating enhanced follow-up prompts..."
python ${project_root}/bird_interact_conv_enhanced/code/infer_api_system_enhanced.py \
    --prompt_path ${data_path} \
    --result_path ${result_path_prompt} \
    --user_resp_path ${exec_report} \
    --DB_schema_path ${DB_schema_path} \
    --external_kg_path ${external_kg_path} \
    --patience ${patience} \
    --max_sql_executions ${max_sql_executions} \
    --turn_num 1000 \
    --phase ${phase}

if [ -s "$result_path_prompt" ]; then
    echo "   Processing follow-up with enhanced SQL capabilities..."
    result_path_response="${result_dir}/system_interaction_response.jsonl"
    python ${project_root}/bird_interact_conv_enhanced/code/call_api.py \
        --model_name ${system_model_name} \
        --prompt_path ${result_path_prompt} \
        --output_path ${result_path_response}
    
    result_path_selected_llm="${result_dir}/system_interaction.jsonl"
    python ${project_root}/bird_interact_conv_enhanced/code/collect_response_enhanced.py \
        --source_path ${result_path_selected_llm} \
        --response_path ${result_path_response} \
        --result_path ${result_path_selected_llm}
fi

# Extract and evaluate follow-up results
data_path="${result_dir}/system_interaction.jsonl"
result_path_sql="${result_dir}/sql_results_fu.jsonl"

python ${project_root}/bird_interact_conv_enhanced/code/wrap_up_sql.py \
    --data_path ${data_path} \
    --result_path ${result_path_sql}

echo "🔍 Evaluating follow-up results..."
jsonl_file="${result_dir}/sql_results_fu.jsonl"
python ${project_root}/evaluation/src/eval_bird_interact_batch.py --jsonl "$jsonl_file"

# ===========================================: Phase 2 Debugging :===========================================
echo ""
echo "🐛 Phase 2 Debugging: Enhanced follow-up debugging"

exec_report="${result_dir}/sql_results_fu_output_with_status.jsonl"
data_path="${result_dir}/system_interaction.jsonl"
result_path_prompt="${result_dir}/system_interaction_prompt.jsonl"
phase='debug'

echo "   Generating enhanced follow-up debug prompts..."
python ${project_root}/bird_interact_conv_enhanced/code/infer_api_system_enhanced.py \
    --prompt_path ${data_path} \
    --result_path ${result_path_prompt} \
    --user_resp_path ${exec_report} \
    --DB_schema_path ${DB_schema_path} \
    --external_kg_path ${external_kg_path} \
    --patience ${patience} \
    --max_sql_executions ${max_sql_executions} \
    --turn_num 1001 \
    --phase ${phase}

if [ -s "$result_path_prompt" ]; then
    echo "   Final enhanced debugging..."
    result_path_response="${result_dir}/system_interaction_response.jsonl"
    python ${project_root}/bird_interact_conv_enhanced/code/call_api.py \
        --model_name ${system_model_name} \
        --prompt_path ${result_path_prompt} \
        --output_path ${result_path_response}
    
    result_path_selected_llm="${result_dir}/system_interaction.jsonl"
    python ${project_root}/bird_interact_conv_enhanced/code/collect_response_enhanced.py \
        --source_path ${result_path_selected_llm} \
        --response_path ${result_path_response} \
        --result_path ${result_path_selected_llm}
fi

# Final extraction and evaluation
data_path="${result_dir}/system_interaction.jsonl"
result_path_sql="${result_dir}/sql_results_fu_debug.jsonl"

python ${project_root}/bird_interact_conv_enhanced/code/wrap_up_sql.py \
    --data_path ${data_path} \
    --result_path ${result_path_sql}

echo "🔍 Final evaluation..."
jsonl_file="${result_dir}/sql_results_fu_debug.jsonl"
python ${project_root}/evaluation/src/eval_bird_interact_batch.py --jsonl "$jsonl_file"

# ===========================================: Final Score Calculation :===========================================
echo ""
echo "🏆 Calculating Final Enhanced BIRD-Interact Scores"

python ${project_root}/bird_interact_conv_enhanced/calculate_enhanced_score.py \
    --result_dir "${result_dir}" \
    --patience ${patience} \
    --sql_executions ${max_sql_executions}

echo ""
echo "🎉 Enhanced BIRD-Interact Pipeline Complete!"
echo "📊 Results saved in: $result_dir"
echo "💡 Key Enhancements:"
echo "   ✅ SQL execution tool integrated during clarification phase"
echo "   ✅ Separate budgets for questions ($patience) and SQL queries ($max_sql_executions)"  
echo "   ✅ Enhanced reflection and reasoning capabilities"
echo "   ✅ Better error handling and debugging with SQL exploration"
echo ""