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

---

## Evaluation Prompts

All prompts below are used verbatim during the benchmark. 5 trials per task × scene pair, ordered easy → hard.

> **Notation** — S = single object, M = multiple objects, O = overlapped objects

> The same 5 prompts are used verbatim for every scene condition (S / M / O).

### Pick

| Trial | Prompt |
|:---:|---|
| 1 | pick the yellow dice |
| 2 | grab the yellow dice |
| 3 | pick up the yellow dice not the red dice |
| 4 | can you pick up the yellow dice |
| 5 | I need you to pick the yellow dice |

### Place

| Trial | Prompt |
|:---:|---|
| 1 | place it to the left of the red dice |
| 2 | put it to the right of the red dice |
| 3 | place it above the red dice |
| 4 | place it below the red dice |
| 5 | put it right side of the red dice |

### Handover

| Trial | Prompt |
|:---:|---|
| 1 | give it to me |
| 2 | hand it over |
| 3 | pass it to me |
| 4 | can you give me the dice |
| 5 | deliver the dice carefully to my hand |