import json
import glob
import os
import google.auth
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

try:
    _, project_id = google.auth.default()
except Exception:
    project_id = None
project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT") or "genaillentsearch"
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

# Define schema for the evaluator output
class EvaluationScore(BaseModel):
    score: int = Field(description="Score from 1 to 5")
    explanation: str = Field(description="Detailed justification for the score")

# Evaluator prompts
PROMPTS = {
    "custom_response_quality": """You are an expert compliance auditor. Grade the general response quality of the Compliance Briefing on a scale of 1 to 5:
1: Unclear, contains major compliance errors, or fails to address the query.
2: Low quality; partially addresses query but lacks depth or has inaccuracies.
3: Acceptable; covers basic compliance issues but lacks thorough analysis.
4: Good; covers the query well, provides actionable details with minor issues.
5: Excellent; comprehensive, well-structured, highly actionable and tailored compliance briefing.

User Prompt: {prompt}
Final Response: {response}
""",
    "compliance_accuracy": """Evaluate the compliance briefing for accuracy. Specifically verify:
- Does it accurately reference the source materials (FCA, PRA, HMT, etc.)?
- Are the identified risks correctly classified as High, Medium, or Low urgency?
- Are the facts (such as sanctions or regulatory names) correct based on the trace?

Grade from 1 to 5:
1: Completely inaccurate or hallucinated.
5: Extremely accurate, all claims are verified by the trace.

User Prompt: {prompt}
Final Response: {response}
Trace Details: {agent_data}
"""
}

def get_latest_trace_file():
    files = glob.glob("artifacts/traces/traces_*.json")
    if not files:
        raise FileNotFoundError("No trace files found in artifacts/traces/")
    return max(files, key=os.path.getmtime)

def main():
    client = genai.Client()
    trace_file = get_latest_trace_file()
    print(f"Loading traces from: {trace_file}")
    
    with open(trace_file, "r") as f:
        data = json.load(f)
        
    eval_cases = data.get("eval_cases", [])
    results = {}
    
    for case in eval_cases:
        case_id = case.get("eval_case_id")
        print(f"\nEvaluating case: {case_id}...")
        
        # Extract prompt & response from trace
        turns = case.get("agent_data", {}).get("turns", [])
        if not turns:
            print(f"Skipping case {case_id}: no turns found")
            continue
            
        prompt = ""
        response = ""
        
        # First turn, first user event
        for event in turns[0].get("events", []):
            if event.get("author") == "user":
                parts = event.get("content", {}).get("parts", [])
                if parts and "text" in parts[0]:
                    prompt = parts[0]["text"]
                    break
        
        # Last turn, last model event (or text-bearing event)
        for turn in reversed(turns):
            for event in reversed(turn.get("events", [])):
                if event.get("author") == "synthesis_agent":
                    parts = event.get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        response = parts[0]["text"]
                        break
            if response:
                break
                
        if not response:
            # Fallback to any model event
            for turn in reversed(turns):
                for event in reversed(turn.get("events", [])):
                    if event.get("author") not in ("user", "tool"):
                        parts = event.get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            response = parts[0]["text"]
                            break
                if response:
                    break
                    
        results[case_id] = {
            "prompt": prompt,
            "response": response,
            "scores": {}
        }
        
        # Run each evaluation metric sequentially
        for metric, template in PROMPTS.items():
            formatted_prompt = template.format(
                prompt=prompt,
                response=response,
                agent_data=json.dumps(case.get("agent_data"), indent=2)
            )
            
            try:
                # Force structured JSON output
                response_obj = client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=formatted_prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=EvaluationScore,
                        temperature=0.0
                    )
                )
                eval_res = json.loads(response_obj.text)
                results[case_id]["scores"][metric] = eval_res
                print(f"  - {metric}: Score {eval_res['score']} - {eval_res['explanation'][:100]}...")
            except Exception as e:
                results[case_id]["scores"][metric] = {"score": 0, "explanation": f"Evaluation error: {str(e)}"}
                print(f"  - {metric}: FAILED with error: {str(e)}")

    # Write summary report
    print("\n" + "="*50)
    print("EVALUATION SUMMARY REPORT")
    print("="*50)
    
    # Calculate means
    metrics_sums = {m: 0 for m in PROMPTS.keys()}
    metrics_counts = {m: 0 for m in PROMPTS.keys()}
    
    for case_id, case_res in results.items():
        print(f"\nCase: {case_id}")
        for m, score_obj in case_res["scores"].items():
            s = score_obj["score"]
            print(f"  * {m:26}: Score {s}/5 - {score_obj['explanation']}")
            if s > 0:
                metrics_sums[m] += s
                metrics_counts[m] += 1
                
    print("\n" + "="*50)
    print("AVERAGES")
    print("="*50)
    for m in PROMPTS.keys():
        avg = metrics_sums[m] / metrics_counts[m] if metrics_counts[m] > 0 else 0
        print(f"  * {m:26}: Mean {avg:.2f}/5.00 ({metrics_counts[m]} valid cases)")
        
    os.makedirs("artifacts/grade_results", exist_ok=True)
    with open("artifacts/grade_results/local_eval_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved local evaluation results to: artifacts/grade_results/local_eval_results.json")

if __name__ == "__main__":
    main()
