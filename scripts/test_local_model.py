import httpx
import time
import subprocess
import json

def get_vram():
    try:
        res = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.used,memory.free,memory.total', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, check=True
        )
        used, free, total = res.stdout.strip().split(',')
        return int(used.strip()), int(free.strip()), int(total.strip())
    except Exception as e:
        return 0, 0, 0

print("="*60)
print("MY PERSONAL AI — LOCAL MODEL BENCHMARK (PHASE 2)")
print("="*60)

used_before, free_before, total = get_vram()
print(f"Initial GPU VRAM: Used {used_before} MB | Free {free_before} MB / {total} MB")

prompt = "Write a Python function called `calculate_fibonacci(n)` that returns the first n Fibonacci numbers as a list. Include docstring and type hints."

print(f"\nSending Prompt to local model 'qwen2.5-coder:3b'...")
print(f"Prompt: {prompt}")

start_time = time.time()
try:
    with httpx.Client(timeout=300.0) as client:
        response = client.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": "qwen2.5-coder:3b",
                "prompt": prompt,
                "stream": False
            }
        )
        response.raise_for_status()
        data = response.json()
except Exception as e:
    print(f"Error during inference: {e}")
    exit(1)

total_elapsed = time.time() - start_time
used_after, free_after, _ = get_vram()

generated_text = data.get("response", "").strip()
eval_count = data.get("eval_count", 0)
eval_duration_sec = data.get("eval_duration", 1) / 1e9
tokens_per_sec = eval_count / eval_duration_sec if eval_duration_sec > 0 else 0
load_duration_sec = data.get("load_duration", 0) / 1e9
prompt_eval_count = data.get("prompt_eval_count", 0)

print("\n" + "="*60)
print("GENERATED CODE OUTPUT:")
print("="*60)
print(generated_text)

print("\n" + "="*60)
print("BENCHMARK & HARDWARE METRICS:")
print("="*60)
print(f"Total Turnaround Time: {total_elapsed:.2f} seconds")
print(f"Model Cold-Load Duration: {load_duration_sec:.2f} seconds")
print(f"Prompt Tokens Evaluated: {prompt_eval_count}")
print(f"Completion Tokens Generated: {eval_count} tokens")
print(f"Generation Speed: {tokens_per_sec:.2f} tokens/second")
print(f"Active GPU VRAM Consumption: {used_after} MB (VRAM added: ~{used_after - used_before} MB)")
print("Offline Verification: 100% Local Inference via 127.0.0.1:11434 (Zero Cloud Calls)")
print("="*60)
