# Evaluation Metrics

## Memory

Model size is reported as **weight file size from `ollama list`** (quantised weights on disk).

| Model | `ollama list` (disk) | `ollama ps` (runtime RAM) |
|---|---|---|
| llama3.1:8b | 4.9 GB | 28.6 GB |
| qwen2.5vl:32b | 21 GB | 127.7 GB |

### What each number means

**`ollama list` — quantised file size (reported in paper)**  
The model as stored on disk in its quantised format (e.g. Q4_K_M).  
This is the number that appears in model technical reports (e.g. Qwen2.5-VL) and is the standard size metric for comparing models across the literature.

**Decompressed runtime RAM (`ollama ps`)**  
When Ollama runs a model it fully loads and decompresses the weights into RAM (CPU + GPU).  
Runtime RAM is much larger than the disk file because quantised integers are expanded back to float16/bfloat16 for inference:

$$\text{Runtime RAM} = W_{\text{decompressed}}$$

On top of this, Ollama also allocates a KV cache that scales with context window size (128 k tokens ≈ 9 GB for qwen2.5vl), not with the task — two identical pick requests allocate the same cache. It carries no information about the model itself and is therefore not reported as a model property.

`ollama list` is a fixed, hardware-independent property of the model. Runtime RAM depends on quantisation expansion, GPU/CPU split, and context window — all deployment details, not model properties. Reviewers and practitioners comparing models use the quantised file size.

## Latency

End-to-end latency per request:

$$T_{e2e} = T_{\text{LLM}} + T_{\text{VLM}}$$

$T_{\text{LLM}}$ and $T_{\text{VLM}}$ are taken from Ollama's `total_duration` field, which covers load + prefill + decode and matches wall-clock time.