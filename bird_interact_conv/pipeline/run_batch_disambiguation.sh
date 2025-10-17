#!/usr/bin/env bash
set -e

#####################################
# Batch Disambiguation Configuration
#####################################

# Parameters:
patience=3
disamb_tries=5
US_model_name="gemini-2.0-flash"
system_model="gemini-2.5-pro"
timestamp=$(date +"%Y%m%d_%H%M%S")
system_model_name="${system_model}_${timestamp}"
finetuned_model="projects/618488765595/locations/us-central1/endpoints/897266359451254784"
project_root="/app/"

# Setup directories
result_dir="${project_root}/bird_interact_conv/results/batch_disambiguation/${system_model_name}/"
mkdir -p "$result_dir"

data_path="${project_root}/bird_interact_conv/data/bird-interact-lite/bird_interact_data.jsonl"
DB_schema_path="${project_root}/bird_interact_conv/data/bird-interact-lite/[[DB_name]]/[[DB_name]]_schema.txt"
external_kg_path="${project_root}/bird_interact_conv/data/bird-interact-lite/[[DB_name]]/[[DB_name]]_kb.jsonl"

echo "=========================================="
echo "Batch Disambiguation Workflow"
echo "=========================================="
echo "Finetuned Model: ${finetuned_model}"
echo "Disambiguation Tries: ${disamb_tries}"
echo "User Simulator: ${US_model_name}"
echo "SQL Generator: ${system_model}"
echo "Result Directory: ${result_dir}"
echo "=========================================="

# ============================================
# Step 1: Batch Disambiguation (Finetuned Model) - Multiple Tries
# ============================================
echo ""
echo "Step 1: Generating disambiguation questions with finetuned model (${disamb_tries} tries)..."

# 1.1: Generate prompts for finetuned model (only once)
disambiguation_prompt="${result_dir}/disambiguation_prompt.jsonl"
python ${project_root}/bird_interact_conv/code/infer_api_disambiguate.py \
    --prompt_path ${data_path} \
    --result_path ${disambiguation_prompt} \
    --DB_schema_path ${DB_schema_path} \
    --external_kg_path ${external_kg_path}
wait

# 1.2: Call finetuned model multiple times
if [ ! -s "$disambiguation_prompt" ]; then
    echo "ERROR: Empty disambiguation prompt file!"
    exit 1
fi

echo "  - Calling finetuned model API ${disamb_tries} times for better coverage..."
all_response_files=()
for ((try_idx=1; try_idx<=disamb_tries; try_idx++)); do
    echo "    Try ${try_idx}/${disamb_tries}..."
    disambiguation_response="${result_dir}/disambiguation_response_try${try_idx}.jsonl"
    python ${project_root}/bird_interact_conv/code/call_api.py \
        --model_name ${finetuned_model} \
        --prompt_path ${disambiguation_prompt} \
        --output_path ${disambiguation_response}
    wait
    all_response_files+=("${disambiguation_response}")
done

# 1.3: Parse and aggregate disambiguation responses from all tries
echo "  - Aggregating and deduplicating questions from all ${disamb_tries} tries..."
disambiguation_parsed="${result_dir}/disambiguation_parsed.jsonl"
python ${project_root}/bird_interact_conv/code/parse_disambiguation_response.py \
    --source_path ${data_path} \
    --response_paths "${all_response_files[@]}" \
    --result_path ${disambiguation_parsed}
wait

echo "  ✓ Disambiguation questions generated, aggregated, and parsed"

# ============================================
# Step 2: User Simulator - Encoder Phase
# ============================================
echo ""
echo "Step 2: User simulator encoding actions..."

# 2.1: Generate encoder prompts
user_encoder_prompts="${result_dir}/user_encoder_prompts.jsonl"
python ${project_root}/bird_interact_conv/code/infer_api_batch_user_simulator.py \
    --parsed_path ${disambiguation_parsed} \
    --result_path ${user_encoder_prompts} \
    --DB_schema_path ${DB_schema_path} \
    --phase "encoder"
wait

# 2.2: Call user simulator (encoder)
if [ -s "$user_encoder_prompts" ]; then
    echo "  - Calling user simulator API (encoder)..."
    user_encoder_response="${result_dir}/user_encoder_response.jsonl"
    python ${project_root}/bird_interact_conv/code/call_api.py \
        --model_name ${US_model_name} \
        --prompt_path ${user_encoder_prompts} \
        --output_path ${user_encoder_response}
    wait
    echo "  ✓ Encoder phase completed"
else
    echo "  - No questions need clarification (all CLEAR)"
    user_encoder_response="${result_dir}/user_encoder_response.jsonl"
    touch ${user_encoder_response}
fi

# ============================================
# Step 3: User Simulator - Decoder Phase
# ============================================
echo ""
echo "Step 3: User simulator generating answers..."

# 3.1: Generate decoder prompts based on encoder actions
user_decoder_prompts="${result_dir}/user_decoder_prompts.jsonl"
python ${project_root}/bird_interact_conv/code/process_encoder_and_generate_decoder.py \
    --parsed_path ${disambiguation_parsed} \
    --encoder_response_path ${user_encoder_response} \
    --result_path ${user_decoder_prompts} \
    --DB_schema_path ${DB_schema_path}
wait

# 3.2: Call user simulator (decoder)
if [ -s "$user_decoder_prompts" ]; then
    echo "  - Calling user simulator API (decoder)..."
    user_decoder_response="${result_dir}/user_decoder_response.jsonl"
    python ${project_root}/bird_interact_conv/code/call_api.py \
        --model_name ${US_model_name} \
        --prompt_path ${user_decoder_prompts} \
        --output_path ${user_decoder_response}
    wait
    echo "  ✓ Decoder phase completed"
else
    user_decoder_response="${result_dir}/user_decoder_response.jsonl"
    touch ${user_decoder_response}
fi

# 3.3: Collect all Q&A pairs
echo "  - Collecting all Q&A pairs..."
disambiguation_complete="${result_dir}/disambiguation_complete.jsonl"
python ${project_root}/bird_interact_conv/code/collect_all_answers.py \
    --parsed_path ${disambiguation_parsed} \
    --decoder_response_path ${user_decoder_response} \
    --result_path ${disambiguation_complete}
wait

echo "  ✓ All answers collected and formatted"

# ============================================
# Step 4: Final SQL Generation (Gemini-2.5-Pro)
# ============================================
echo ""
echo "Step 4: Generating final SQL with ${system_model}..."

# 4.1: Generate final SQL prompts
final_sql_prompt="${result_dir}/final_sql_prompt.jsonl"
python ${project_root}/bird_interact_conv/code/infer_api_final_sql.py \
    --prompt_path ${disambiguation_complete} \
    --result_path ${final_sql_prompt} \
    --DB_schema_path ${DB_schema_path} \
    --external_kg_path ${external_kg_path}
wait

# 4.2: Call gemini-2.5-pro for SQL
echo "  - Calling ${system_model} API..."
final_sql_response="${result_dir}/final_sql_response.jsonl"
python ${project_root}/bird_interact_conv/code/call_api.py \
    --model_name ${system_model} \
    --prompt_path ${final_sql_prompt} \
    --output_path ${final_sql_response}
wait

# 4.3: Collect final SQL
echo "  - Collecting final SQL responses..."
final_sql_collected="${result_dir}/system_interaction.jsonl"
python ${project_root}/bird_interact_conv/code/collect_response.py \
    --source_path ${disambiguation_complete} \
    --response_path ${final_sql_response} \
    --result_path ${final_sql_collected}
wait

echo "  ✓ Final SQL generated"

# ============================================
# Step 5: Extract SQL and Evaluate
# ============================================
echo ""
echo "Step 5: Extracting SQL and evaluating..."

result_path_sql="${result_dir}/sql_results.jsonl"
python ${project_root}/bird_interact_conv/code/wrap_up_sql.py \
    --data_path ${final_sql_collected} \
    --result_path ${result_path_sql}
wait

echo "  - Running evaluation..."
python ${project_root}/evaluation/src/eval_bird_interact_batch.py --jsonl "$result_path_sql"

echo ""
echo "=========================================="
echo "✓ Batch disambiguation workflow complete!"
echo "=========================================="
echo "Results saved in: ${result_dir}"
echo "SQL results: ${result_path_sql}"

# ============================================
# Phase 1 Debugging: One More Chance for Debugging
# ============================================
echo ""
echo "=========================================="
echo "Phase 1 Debugging: SQL Error Correction"
echo "=========================================="

exec_report="${result_dir}/sql_results_output_with_status.jsonl"
if [ -f "$exec_report" ]; then
    data_path="${final_sql_collected}"
    result_path_prompt="${result_dir}/system_interaction_prompt.jsonl"
    phase='debug'
    turn_num=2

    echo "Step 6: Debugging failed SQL queries..."
    
    # System: Prompt Generation + Infer API + Response Collection
    python ${project_root}/bird_interact_conv/code/infer_api_system.py \
        --prompt_path ${data_path} \
        --result_path ${result_path_prompt} \
        --user_resp_path ${exec_report} \
        --DB_schema_path ${DB_schema_path} \
        --external_kg_path ${external_kg_path} \
        --patience ${patience} \
        --turn_num ${turn_num} \
        --phase ${phase}
    wait 
    
    if [ ! -s "$result_path_prompt" ]; then
        echo "  - No queries need debugging"
    else
        result_path_response="${result_dir}/system_interaction_response.jsonl"
        python ${project_root}/bird_interact_conv/code/call_api.py \
            --model_name ${system_model} \
            --prompt_path ${result_path_prompt} \
            --output_path ${result_path_response}
        wait

        result_path_selected_llm="${final_sql_collected}"
        python ${project_root}/bird_interact_conv/code/collect_response.py \
            --source_path ${result_path_selected_llm} \
            --response_path ${result_path_response} \
            --result_path ${result_path_selected_llm}
        wait
        
        # SQL extract
        result_path_sql="${result_dir}/sql_results_debug.jsonl"
        python ${project_root}/bird_interact_conv/code/wrap_up_sql.py \
            --data_path ${data_path} \
            --result_path ${result_path_sql}
        wait

        # Eval
        echo "  - Evaluating debugged SQL..."
        python ${project_root}/evaluation/src/eval_bird_interact_batch.py --jsonl "$result_path_sql"
        echo "  ✓ Debugging phase completed"
    fi
else
    echo "  - Execution report not found, skipping debug phase"
fi

# ============================================
# Phase 2: Follow Up Question
# ============================================
echo ""
echo "=========================================="
echo "Phase 2: Follow-up Questions"
echo "=========================================="

exec_report="${result_dir}/sql_results_debug_output_with_status.jsonl"
if [ ! -f "$exec_report" ]; then
    exec_report="${result_dir}/sql_results_output_with_status.jsonl"
fi

if [ -f "$exec_report" ]; then
    data_path="${final_sql_collected}"
    result_path_prompt="${result_dir}/system_interaction_prompt.jsonl"
    phase='follow'
    turn_num=2

    echo "Step 7: Processing follow-up questions..."
    
    # System: Prompt Generation + Infer API + Response Collection
    python ${project_root}/bird_interact_conv/code/infer_api_system.py \
        --prompt_path ${data_path} \
        --result_path ${result_path_prompt} \
        --user_resp_path ${exec_report} \
        --DB_schema_path ${DB_schema_path} \
        --external_kg_path ${external_kg_path} \
        --patience ${patience} \
        --turn_num ${turn_num} \
        --phase ${phase}
    wait 
    
    if [ ! -s "$result_path_prompt" ]; then
        echo "  - No follow-up questions to process"
    else
        result_path_response="${result_dir}/system_interaction_response.jsonl"
        python ${project_root}/bird_interact_conv/code/call_api.py \
            --model_name ${system_model} \
            --prompt_path ${result_path_prompt} \
            --output_path ${result_path_response}
        wait

        result_path_selected_llm="${final_sql_collected}"
        python ${project_root}/bird_interact_conv/code/collect_response.py \
            --source_path ${result_path_selected_llm} \
            --response_path ${result_path_response} \
            --result_path ${result_path_selected_llm}
        wait
        
        # SQL extract
        result_path_sql="${result_dir}/sql_results_fu.jsonl"
        follow_up_path="${result_path_prompt}"
        python ${project_root}/bird_interact_conv/code/wrap_up_sql.py \
            --data_path ${data_path} \
            --result_path ${result_path_sql} \
            --follow_up_path ${follow_up_path}
        wait

        # Eval
        echo "  - Evaluating follow-up SQL..."
        python ${project_root}/evaluation/src/eval_bird_interact_batch.py --jsonl "$result_path_sql"
        echo "  ✓ Follow-up phase completed"
    fi
else
    echo "  - Execution report not found, skipping follow-up phase"
fi

# ============================================
# Phase 2 Debugging: Follow Up Question Debugging
# ============================================
echo ""
echo "=========================================="
echo "Phase 2 Debugging: Follow-up SQL Correction"
echo "=========================================="

exec_report="${result_dir}/sql_results_fu_output_with_status.jsonl"
if [ -f "$exec_report" ]; then
    data_path="${final_sql_collected}"
    result_path_prompt="${result_dir}/system_interaction_prompt.jsonl"
    phase='debug'
    turn_num=3

    echo "Step 8: Debugging failed follow-up SQL queries..."
    
    # System: Prompt Generation + Infer API + Response Collection
    python ${project_root}/bird_interact_conv/code/infer_api_system.py \
        --prompt_path ${data_path} \
        --result_path ${result_path_prompt} \
        --user_resp_path ${exec_report} \
        --DB_schema_path ${DB_schema_path} \
        --external_kg_path ${external_kg_path} \
        --patience ${patience} \
        --turn_num ${turn_num} \
        --phase ${phase}
    wait 
    
    if [ ! -s "$result_path_prompt" ]; then
        echo "  - No follow-up queries need debugging"
    else
        result_path_response="${result_dir}/system_interaction_response.jsonl"
        python ${project_root}/bird_interact_conv/code/call_api.py \
            --model_name ${system_model} \
            --prompt_path ${result_path_prompt} \
            --output_path ${result_path_response}
        wait

        result_path_selected_llm="${final_sql_collected}"
        python ${project_root}/bird_interact_conv/code/collect_response.py \
            --source_path ${result_path_selected_llm} \
            --response_path ${result_path_response} \
            --result_path ${result_path_selected_llm}
        wait
        
        # SQL extract
        result_path_sql="${result_dir}/sql_results_fu_debug.jsonl"
        follow_up_path="${result_path_prompt}"
        python ${project_root}/bird_interact_conv/code/wrap_up_sql.py \
            --data_path ${data_path} \
            --result_path ${result_path_sql} \
            --follow_up_path ${follow_up_path}
        wait

        # Eval
        echo "  - Evaluating debugged follow-up SQL..."
        python ${project_root}/evaluation/src/eval_bird_interact_batch.py --jsonl "$result_path_sql"
        echo "  ✓ Follow-up debugging phase completed"
    fi
else
    echo "  - Follow-up execution report not found, skipping debug phase"
fi

echo ""
echo "=========================================="
echo "✓✓✓ ALL PHASES COMPLETE ✓✓✓"
echo "=========================================="
echo "Final results available in: ${result_dir}"
