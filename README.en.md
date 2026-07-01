<p align="center">
  <a href="README.md">中文</a> | <b>English</b>
</p>

A collection of Agent skills for Horizon OpenExplorer (OE) toolchain scenarios. Centered around core steps such as PTQ/QAT quantization, HBDK compilation, UCP on-board inference, performance and accuracy evaluation, this manual modularizes path knowledge, stage dependencies, and verification processes, enabling Agents to complete end-to-end optimization from floating-point models to on-board deployment in a streamlined workflow.

# Features

* Toolchain Routing and Orchestration: `horizon-router` serves as the top-level entry point, dispatching requests to the appropriate sub-skill based on the `description` field of each skill in `skill-index.json`.

* End-to-End Deployment Pipeline: Covers the complete chain of "quantization → compilation → on-board inference → performance/accuracy evaluation". Full-pipeline deployment specifications take precedence over the default behavior of individual skills.

* Environment and Board Detection: Automatically detects development board model, OE package version, local Python/CUDA/PyTorch compatibility, and creates a venv with required installations as needed.

* Accuracy Tuning: QAT adaptation and export, PTQ quantization construction, mixed-precision tuning, training-deployment consistency debugging, cosine similarity analysis.

* Performance Analysis: Perfetto trace capture and analysis, `hb_analyzer` performance bottleneck localization, on-board BPU/DDR/memory resource monitoring.

* LLM Quantization and Compression: LightCompress batch quantization experiments (RTN/GPTQ/AWQ/SmoothQuant), `llm_compression` calibration/compilation/on-board evaluation.

# Quick Start

## Installation

### Install Skills

```python
#tell your Agent:
Install this skill: https://github.com/HorizonRobotics/OE-Skills/blob/main/agent-setup.md
```

### Configure MCP&#x20;

> The previous step is assumed to be already installed by default. It is recommended that users verify whether the MCP service is available after installation is complete. The following shows how to manually configure MCP:

<table><colgroup><col width="120"><col width="680"></colgroup>
<thead>
<tr>
<th></th>
<th>Command</th>
</tr>
</thead>
<tbody>
<tr>
<td>General</td>
<td>Tell your Agent: help me configure <strong>the following MCP service</strong><pre><code class="language-python">"oe-mcp": {
  "type": "http",
  "url": "https://mcp.oe.horizon.auto/mcp"
}
</code></pre></td>
</tr>
<tr>
<td>codex</td>
<td>codex mcp add oe-mcp --url https://mcp.oe.horizon.auto/mcp</td>
</tr>
<tr>
<td>Claude code</td>
<td><code>claude mcp add --transport http oe-mcp https://mcp.oe.horizon.auto/mcp</code></td>
</tr>
<tr>
<td>cursor</td>
<td>Press <code>command+shift+p</code>, open MCP settings, click New MCP Server, add the following config to the JSON and save:<pre><code class="language-json">{
  "mcpServers": {
    "oe-mcp": {
      "type": "http",
      "url": "https://mcp.oe.horizon.auto/mcp"
    }
  }
}
</code></pre></td>
</tr>
</tbody>
</table>

## Usage

<table>
<colgroup><col style="width:22%"/><col style="width:58%"/><col style="width:20%"/></colgroup>
<thead>
<tr>
<td><strong>Task Scenario</strong></td>
<td><strong>Prompt</strong></td>
<td><strong>Skill Called</strong></td>
</tr>
</thead>
<tbody>
<tr>
<td>Model latency measurement</td>
<td>Help me test the latency of <code>xxx.hbm</code> on the dev board <code>xx.xx.xx.xx</code></td>
<td>j6-ucp-model-perf-eval</td>
</tr>
<tr>
<td>Model latency analysis</td>
<td>Help me analyze the latency bottleneck of <code>xxx.hbm</code> on dev board <code>xx.xx.xx.xx</code></td>
<td>hb-analyzer-performance</td>
</tr>
<tr>
<td>ONNX accuracy optimization</td>
<td>Help me tune the accuracy of model <code>xxx.onnx</code>, calibration data path: <code>{calib_data}</code>, use <code>{OE_docker}</code></td>
<td>j6-hmct-cosine-similarity-tuning</td>
</tr>
<tr>
<td>PyTorch model accuracy optimization</td>
<td>After calibration, the validation top-1 dropped from 78% (float) to 55%. Please help me analyze and tune. Calibration/evaluation code: <code>{calib.py}</code></td>
<td>j6-plugin-precision-tuning</td>
</tr>
<tr>
<td>Quantization config check</td>
<td>Help me analyze model_check_result.txt to see where the quantization config is problematic</td>
<td>j6-plugin-model-check-result</td>
</tr>
<tr>
<td>Write HBM evaluation code</td>
<td>Help me evaluate the accuracy of <code>xxx.hbm</code>. Calibration evaluation code is <code>val.py</code>, dev board <code>xx.xx.xx.xx</code>. If network latency is high, reduce evaluation frames to 100</td>
<td>j6-ucp-hbm-infer</td>
</tr>
<tr>
<td>Write HBM deployment code</td>
<td>I have four small models under <code>{model_path}</code>. These models have no data dependencies and can run concurrently. Please write UCP deployment code and test using dev board <code>xx.xx.xx.xx</code></td>
<td>j6-ucp-infer-generating</td>
</tr>
<tr>
<td>Single operator test verification</td>
<td>Help me write a full quantization-compilation pipeline for Conv2d, input shape (1, 3, 32, 32), march nash-p</td>
<td>j6-plugin-hbdk-generating</td>
</tr>
<tr>
<td>ONNX model deployment</td>
<td colspan="2">Requires multiple Skills, see [ONNX Model Deployment Full Example](docs/en/onnx-deployment/index.md)</td>
</tr>
<tr>
<td>PyTorch model deployment</td>
<td colspan="2">Requires multiple Skills, see [PyTorch Model Deployment Full Example](docs/en/pytorch-deployment/index.md)</td>
</tr>
</tbody>
</table>

# Directory Structure

```yaml
OE-Skills/
├── README.md                # Chinese README
├── README.en.md             # This file
├── agent-setup.md           # Agent installation guide
├── setup.sh                 # Installation script, deploys horizon/ resources to target project .horizon/
├── docs/                    # Deployment full-process example documents
│   ├── zh/                  # Chinese docs
│   │   ├── onnx-deployment/  # ONNX model deployment full example
│   │   └── pytorch-deployment/  # PyTorch model deployment full example
│   └── en/                  # English docs
│       ├── onnx-deployment/  # ONNX model deployment full example
│       └── pytorch-deployment/  # PyTorch model deployment full example
├── horizon/                 # Resource directory (copied to target project during installation)
│   ├── HORIZON.md           # Workspace rules and usage instructions
│   ├── VERSION              # Current version number
│   ├── skill-index.json     # Skill index (module, path, description, trigger conditions)
│   ├── docs/                # Horizon toolchain offline documentation
│   └── skills/              # Skill collections organized by module
│       ├── horizon-router/  # Top-level routing skill
│       ├── hbdk/            # HBDK compilation related
│       ├── plugin/          # Horizon Plugin (QAT quantization)
│       ├── hmct/            # HMCT / PTQ quantization
│       ├── ucp/             # UCP / on-board inference
│       ├── horizon_tc_ui/   # Visualization analysis tools
│       └── llm/             # LLM quantization and compression
```

# Skills Overview

### Top-level Routing Skills

`horizon-router` is the toolchain entry point, handling PTQ/QAT quantization, compilation, on‑board deployment, performance and accuracy evaluation requests, and routing them to corresponding sub‑skills. Environmental detection skills are invoked on‑demand when on‑board tasks or toolchain operations are triggered.


| Skill                    | Function           | Trigger Conditions                                   |
| ------------------------ | ------------ | -------------------------------------- |
| horizon-router           | Top-level routing entry       | Any Horizon toolchain‑related request dispatching                  |
| board-detection          | Board hardware platform detection     | On‑board execution/inference/stress test and `.env.board` missing             |
| oe-package-detection     | OE package environment detection     | Normal PTQ/QAT quantization/compilation/deployment and `.env.oe-package` missing |
| oe-package-install       | Local OE package installation     | Triggered after `oe-package-detection` completes as needed         |
| oe-llm-package-detection | OE‑LLM package environment detection | Tasks that depend on OE‑LLM package (e.g., LightCompress)          |
| oe-llm-package-install   | Local OE‑LLM package installation | Triggered after `oe-llm-package-detection` completes as needed     |

### HBDK Module (Model Compilation)


| Skill           | Function               | Trigger Scenarios                                  |
| --------------- | ---------------- | ------------------------------------- |
| j6-hbdk-compile | YAML‑config‑driven general model compilation  | Model compilation, exporting hbm, generating on‑board artifacts, pyramid/resizer inputs |
| hbdk-manual     | HBDK4 compilation tool usage guide index | Querying usage of compilation tools by task scenario                      |

### Horizon Plugin Module (PyTorch Quantization)


| Skill                        | Function                     | Trigger Scenarios                                       |
| ---------------------------- | ---------------------- | ------------------------------------------ |
| j6-plugin-adaptation         | Floating PyTorch model QAT tool adaptation | Adapting a model for `horizon_plugin_pytorch`              |
| j6-plugin-export             | QAT model export to HBIR IR       | Exporting QAT model via `hbdk4.export`                   |
| j6-plugin-hbdk-generating    | Full quantization‑to‑compilation code generation           | Covering multiple quantization and compilation steps simultaneously                              |
| j6-plugin-model-check-result | Quantization config check result analysis             | Analyzing `model_check_result.txt` to locate structure/qconfig issues |
| j6-plugin-graph-diff         | FX Graph computational graph diff comparison       | Locating structural and operator parameter differences between two graphs                          |
| j6-plugin-consistency-debug  | Training‑deployment consistency issue diagnosis           | QAT training normal but export/convert/compile/HBM accuracy drops    |
| j6-plugin-precision-tuning   | PyTorch‑side accuracy tuning          | Calibration accuracy below target, QAT loss not converging, mixed‑precision tuning     |

### HMCT Module (ONNX Quantization)


| Skill                            | Function           | Trigger Scenarios                                   |
| -------------------------------- | ------------ | -------------------------------------- |
| hmct-workflow                    | Model conversion and accuracy tuning entry | HMCT, model conversion, model quantization, PTQ, accuracy tuning, node sensitivity          |
| j6-hmct-cosine-similarity-tuning | PTQ accuracy tuning workflow  | cosine similarity below target (default ≥0.99), mixed‑precision fallback |

### UCP Module (On‑board Inference)


| Skill                          | Function                           | Trigger Scenarios                                             |
| ------------------------------ | ---------------------------- | ------------------------------------------------ |
| j6-ucp-infer-generating        | UCP inference C++ code generation              | UCP/DNN inference API usage, parameter details, model loading, tensor memory, Cache synchronization    |
| j6-ucp-hbm-infer               | hbm\_infer Python client code generation    | X86‑side Python HBM model inference via HbmRpcSession/HTensor   |
| j6-ucp-model-perf-eval         | hrt\_model\_exec perf on‑board performance evaluation | Model performance testing, benchmarking, thread\_num/core\_id scanning, throughput/latency comparisons |
| j6-ucp-perfetto-trace-catcher  | Perfetto trace capture on board          | Capturing UCP `.pftrace`, J6 dev board trace collection                 |
| j6-ucp-perfetto-trace-analysis | Perfetto trace performance bottleneck analysis        | UCP inference trace diagnostics, latency/pipeline stall/BPU gap analysis            |
| j6-board-monitor               | On‑board resource monitoring and collection                    | BPU utilization, DDR bandwidth, memory usage, resource monitoring during LLM inference                 |

### Horizon TC UI Module (Visualization Analysis)


| Skill                   | Function                    | Trigger Scenarios                                                                             |
| ----------------------- | --------------------- | -------------------------------------------------------------------------------- |
| hb-analyzer-performance | hb\_analyzer model performance analysis   | Model performance/latency/bandwidth/BPU utilization/bottleneck analysis                                                        |
| horizon-tc-ui           | OpenExplorer CLI tool integration | hb\_compile/hb\_model\_info/hb\_verifier/hb\_analyzer, YAML config, PTQ quantization, HBIR/HBM artifacts |

### LLM Module (Quantization and Compression)


| Skill                        | Function                      | Trigger Scenarios                                                                                       |
| ---------------------------- | ----------------------- | ------------------------------------------------------------------------------------------ |
| lightcompress-batch-quantize | Batch quantization experiments and comparison table generation            | Batch quantization experiments across multiple models/methods/configurations                                                                          |
| lightcompress-quant-explore  | Single quantization experiment and accuracy report             | Quantization experiments, PPL evaluation, RTN/GPTQ/AWQ/SmoothQuant                                                       |
| llmcompression-add-model     | Adding new model support to llm\_compression | Integrating new LLM/VLM models into `llm_compression/models/`                                                  |
| llmcompression-operations    | llm\_compression daily operations   | Calibration, GPU accuracy evaluation (torch\_eval), HBM compilation, on‑board evaluation (hbm\_rpc\_eval), quantization analysis (quant\_analysis) |

> Full‑pipeline deployment specifications take precedence: When a request involves the complete chain of "quantization → compilation → deployment", the full‑pipeline specifications in `horizon-router/references/deployment-workflow.md` are the highest authority. If any sub‑skill's default behavior conflicts with the full‑pipeline specifications (e.g., `calibration_type`, `all_node_type`, `remove_node_type`, or deployment deliverable formats), the full‑pipeline specifications shall prevail.

# Disclaimer

Thank you for your interest in the OE-Skills project. We hope these skills and knowledge will help you develop more effectively with OpenExplorer.

Before using, please understand the following:

* The Agent skills content in this directory is provided for technical reference and learning purposes only, and does not imply that it is suitable for any production environment or critical business system.

* The code and other artifacts automatically generated by Agents are subject to various factors including model capabilities, skill capabilities, and user prompts. Developers must review the safety, compatibility, and correctness of all generated artifacts themselves. The authors and contributors assume no liability for any direct or indirect losses arising from the use of this content.

* This content may involve third‑party dependencies or API calls; developers are responsible for verifying the relevant permissions and compliance.

* Unless otherwise explicitly agreed, all content in this directory is released under an open‑source license and does not provide any form of technical support or warranty.
