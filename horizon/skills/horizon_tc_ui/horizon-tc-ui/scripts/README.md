# Skill Scripts 统一调用规约

本目录下的脚本为 `horizon_tc_ui` 的辅助工具集，面向 CI 流水线、Claude Code 交互以及开发者日常使用。

## 运行环境

- **Python 版本**: 3.10 或 3.11
- **依赖策略**: 零第三方依赖优先，所有脚本仅复用 `horizon_tc_ui` 自身依赖（`pyyaml`、`schema`、`click`、`onnx` 等），不引入额外包
- **安装要求**: 需先安装 `horizon_tc_ui` 包（`pip install -e .` 或 `pip install horizon_tc_ui`）

## 统一 CLI 规约

### 标准参数

所有脚本支持以下通用参数（如适用）：

| 参数 | 说明 |
|------|------|
| `--input` / `-i` | 输入文件路径（yaml、log、模型等） |
| `--output` / `-o` | 输出文件路径，不指定时输出到 stdout |
| `--format` | 输出格式：`text`（人类可读）或 `json`（机器可解析），默认 `text` |
| `-v` | 详细模式，输出 DEBUG 级别日志 |
| `-q` | 静默模式，仅输出错误信息 |
| `--version` | 显示脚本版本 |

### 统一退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 执行成功 |
| 1 | 参数错误（缺少必填参数、格式不正确等） |
| 2 | 校验失败（yaml 校验、格式校验等未通过） |
| 3 | 运行时错误（文件不存在、解析失败、IO 错误等） |
| 4 | 环境不满足要求（依赖缺失、版本不匹配等） |

### 统一 JSON 输出契约

当 `--format json` 时，所有脚本输出遵循以下结构：

```json
{
  "status": "success" | "error",
  "exit_code": 0,
  "message": "简要描述",
  "data": { ... },
  "errors": [
    {
      "field": "字段路径",
      "expected": "期望值或类型",
      "actual": "实际值或类型",
      "suggestion": "修复建议"
    }
  ]
}
```

## 日志通道

- **stderr**: 人类可读的日志信息（INFO/WARNING/ERROR/DEBUG）
- **stdout**: 机器可解析的输出（JSON 或格式化文本）

这保证了 `script.py --format json | jq .` 不会被日志污染。

## 脚本列表

| 脚本 | 用途 | 退出码 |
|------|------|--------|
| `validate_yaml.py` | 校验 YAML 配置文件 | 0 / 1 / 2 |
| `parse_compile_log.py` | 解析 hb_compile.log | 0 / 1 / 3 |
| `extract_verifier_summary.py` | 提取 hb_verifier 汇总 | 0 / 1 / 3 |
| `diff_yaml.py` | 对比两份 YAML 差异 | 0 / 1 / 3 |
| `detect_env.py` | 检测运行环境 | 0 / 1 / 4 |
| `export_schema.py` | 导出 JSON Schema | 0 / 1 / 3 |

## CI 集成示例

### Jenkins Pipeline

```groovy
stage('Validate YAML') {
    steps {
        sh '''
            python skill/scripts/validate_yaml.py --input config.yaml --format json > report.json
            if [ $? -ne 0 ]; then
                echo "YAML validation failed"
                cat report.json
                exit 1
            fi
        '''
    }
}

stage('Compile Model') {
    steps {
        sh 'hb_compile -c config.yaml'
    }
    post {
        always {
            sh 'python skill/scripts/parse_compile_log.py --input hb_compile.log --format json > compile_report.json'
        }
    }
}
```

### Claude Code 集成

在 Claude Code 中，可以直接调用这些脚本来辅助开发：

```bash
# 校验配置
python skill/scripts/validate_yaml.py --input my_config.yaml

# 检查环境
python skill/scripts/detect_env.py --format json

# 对比配置变更
python skill/scripts/diff_yaml.py --input old.yaml --input new.yaml
```

## 贡献规则

1. 所有脚本必须使用中文注释和文档字符串
2. 每个脚本顶部必须包含模块 docstring（用途/输入/输出/退出码/示例）
3. 每个脚本必须包含版权声明
4. 每个脚本必须使用 `argparse` 并包含 `if __name__ == "__main__"` 入口
5. 新增脚本需在本文档的"脚本列表"表格中注册
6. 日志走 stderr，数据走 stdout，不得混用
7. 所有脚本不得引入 `horizon_tc_ui` 依赖之外的第三方包
