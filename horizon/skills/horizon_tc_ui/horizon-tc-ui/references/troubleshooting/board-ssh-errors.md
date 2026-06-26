# 板端 SSH 错误排错指南

本文档按报错文本倒排索引，覆盖板端 SSH 连接、认证、文件传输和远程推理的常见错误。

---

## `Invalid IP address: {host}`

- **原因**：传入的板端 IP 地址格式不合法，不是有效的 IPv4 地址格式。
- **修法**：
  1. 确认 IP 地址格式为 `x.x.x.x`（如 `192.168.1.100`）。
  2. 检查是否混入了空格、换行或其他字符。
  3. 多块板端时使用逗号分隔，如 `--ip 192.168.1.100,192.168.1.101`。
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:604-606`

---

## `Connect to {host} without password failed! Please make sure you can connect the board with ssh command`

- **原因**：无密码 SSH 连接失败。通常因为：
  - 未配置 SSH 免密登录（SSH key）。
  - 板端 SSH 服务未启动或不可达。
  - 网络不通。
- **修法**：
  1. 先在终端手动测试 SSH 连接：`ssh root@{host}`。
  2. 如需免密登录，配置 SSH key：
     ```bash
     ssh-keygen -t rsa
     ssh-copy-id root@{host}
     ```
  3. 或者在 yaml/命令行中提供密码参数。
  4. 检查板端 SSH 服务是否运行：`systemctl status sshd`。
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:628-633`

---

## `Connect to {host} with host key failed! Please make sure you can connect the board with ssh command`

- **原因**：使用密码连接时，SSH host key 验证失败。
- **修法**：
  1. 清除旧的 host key：`ssh-keygen -R {host}`。
  2. 重新连接并接受新的 host key。
  3. 确认板端 IP 未被其他设备占用（IP 冲突）。
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:645-651`

---

## `Connect to {host} with username {username} and password {password} failed!`

- **原因**：SSH 用户名或密码不正确。
- **修法**：
  1. 确认用户名和密码正确（注意大小写）。
  2. 在终端手动验证：`ssh {username}@{host}`。
  3. 检查板端是否允许密码登录（`/etc/ssh/sshd_config` 中 `PasswordAuthentication yes`）。
  4. 如果密码为空字符串但实际需要密码，请正确传入密码。
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:652-657`

---

## `Only support HBM model run with board, currently only received {model_types}, input board info will not take effect.`

- **原因**：传入了板端信息但模型中没有 HBM 模型。只有 HBM 模型才能在板端运行推理。
- **修法**：
  1. 如果不需要板端推理，忽略此警告。
  2. 如果需要板端推理，确保模型参数中包含 `.hbm` 文件。
- **源码定位**：`horizon_tc_ui/verifier/params_check.py:197-203`

---

## `Expected two board IPs or None to set the board info, only received {board_ip}. Please check your input.`

- **原因**：验证两个 HBM 模型时只提供了一个板端 IP。两个 HBM 模型需要分别在两块板端（或同一板端的不同配置）上运行。
- **修法**：
  1. 提供两个板端 IP（逗号分隔）：`--ip 192.168.1.100,192.168.1.101`。
  2. 如果两块模型在同一板端验证，可以不提供 IP（使用模拟器）。
  3. 或者传入 `none` 跳过某块板端：`--ip 192.168.1.100,none`。
- **源码定位**：`horizon_tc_ui/verifier/params_check.py:204-208`

---

## `The number of {check} and board ip is not equal, currently only received {check}`

- **原因**：板端参数（username/password/port/remote_root）的数量与 IP 数量不匹配。
- **修法**：
  1. 确保每个 IP 都有对应的 username、password、port、remote_root。
  2. 例如两个 IP 时需要：`-u root,root -p pwd1,pwd2 --port 22,22`。
  3. 未指定的参数会使用默认值（username=root, password="", port=22）。
- **源码定位**：`horizon_tc_ui/verifier/params_check.py:223-227`

---

## `The two hbm models should have the same march, currently received march {march1} and {march2}`

- **原因**：两个 HBM 模型的 march（芯片架构）不一致，无法在同一板端环境下对比。
- **修法**：
  1. 重新编译其中一个 HBM 模型使其 march 与另一个一致。
  2. 检查 yaml 配置中的 `march` 参数是否相同。
- **源码定位**：`horizon_tc_ui/verifier/params_check.py:247-252`

---

## `Receive board info, run inference with board`

- **原因**：这是一条信息日志（非错误），表示已接收到板端信息并将在板端执行推理。
- **修法**：无需处理，正常流程。
- **源码定位**：`horizon_tc_ui/verifier/inference.py:79-80`

---

## SSH 连接超时（无明确报错文本，程序长时间挂起）

- **原因**：SSH 连接设置了 `timeout=None`（无限等待），在网络不通或板端无响应时会一直挂起。
- **修法**：
  1. 检查网络连通性：`ping {board_ip}`。
  2. 检查板端是否在线、SSH 端口是否开放：`nc -zv {board_ip} 22`。
  3. 检查防火墙规则是否阻止了 SSH 连接。
  4. 如果板端正在重启或异常，等待恢复后重试。
- **源码定位**：
  - `horizon_tc_ui/utils/tool_utils.py:614-619`（无密码连接，timeout=None）
  - `horizon_tc_ui/utils/tool_utils.py:637-644`（有密码连接，timeout=None）

---

## 板端远程路径不存在（推理时文件传输失败）

- **原因**：`remote_root` 指定的远程路径在板端不存在，或没有写权限。
- **修法**：
  1. 确认远程路径存在且有写权限。默认路径：
     - nash_b march：`/userdata/hb_verifier/`
     - 其他 march：`/map/hb_verifier/`
  2. 手动 SSH 到板端创建目录：`ssh root@{host} "mkdir -p {remote_root}"`。
  3. 通过 `--remote-root` 参数指定其他有效路径。
- **源码定位**：
  - `horizon_tc_ui/verifier/params_check.py:254-269`（remote_root 默认值设置）
  - `horizon_tc_ui/verifier/inference.py:79-89`（run_arm 调用）
  - `horizon_tc_ui/hb_hbmruntime.py:125-184`（run_arm 实现）

---

## hbm_infer 依赖缺失导致板端推理失败

- **原因**：`hbm_infer` 包未安装或版本不满足 `>=3.9.0`，板端推理无法初始化。
- **修法**：
  1. 安装 hbm_infer：`pip install hbm_infer>=3.9.0`。
  2. 确认版本：`python -c "from hbm_infer import hbm_rpc_session_flexible; print(hbm_rpc_session_flexible.__version__)"`。
- **源码定位**：
  - `horizon_tc_ui/verifier/params_check.py:297-300`（`check_hbm_infer`）
  - `horizon_tc_ui/hb_hbmruntime.py:135-137`（`import_from` 导入 hbm_infer）

---

## `Set remote_root to default value {remote_root} for board {ip}`

- **原因**：信息日志，表示未指定 `remote_root` 时使用了默认值。
- **修法**：无需处理。如需自定义路径，通过 `--remote-root` 参数指定。
- **源码定位**：`horizon_tc_ui/verifier/params_check.py:265-269`

---

## `{board_ip} is connected successfully.`

- **原因**：信息日志，SSH 连接成功。
- **修法**：无需处理，正常流程。
- **源码定位**：`horizon_tc_ui/verifier/params_check.py:286`

---

## 板端推理 RPC 超时或连接断开

- **原因**：板端推理过程中 RPC 连接中断或推理超时。可能原因：
  - 板端进程崩溃或被杀。
  - 网络不稳定。
  - 模型过大导致板端内存不足。
- **修法**：
  1. 检查板端日志和系统状态。
  2. 确认板端内存充足：`free -h`。
  3. 检查 HBM 模型与板端 march 是否匹配。
  4. 增大 `frame_timeout` 参数（当前默认 300 秒）。
  5. 确保板端 hbm_rpc_server 进程正常运行。
- **源码定位**：
  - `horizon_tc_ui/hb_hbmruntime.py:169-173`（HbmRpcSession 初始化，frame_timeout=300）
  - `horizon_tc_ui/hb_hbmruntime.py:176`（推理调用）
