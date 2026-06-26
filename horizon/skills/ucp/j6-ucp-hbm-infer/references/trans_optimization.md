# Transmission Optimization — Full Reference

Module: `hbm_infer.utils` (for `HTensor`), `hbm_infer.hbm_rpc_session` (for `output_config`)

Three optimization scenarios to reduce data transfer between X86 and board:

1. **Fixed/Periodic Input**: Cache input tensors on board, only re-transfer when changed
2. **Output Filtering**: Skip transferring unused outputs back to X86
3. **Model Chaining**: Keep intermediate outputs on board and pass directly to next model

## HTensor Class

`HTensor` is a wrapper class for tensors used in transmission optimization, providing a unified interface for X86-side and board-side tensors.

### HTensor.__init__

```python
def __init__(
    self,
    data: Union[np.ndarray, torch.Tensor, None],
    device: Union[str, List[str], None],
    key: Optional[str] = None,
) -> None:
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `data` | `Union[np.ndarray, torch.Tensor, None]` | Tensor data to wrap |
| `device` | `Union[str, List[str], None]` | Storage device(s). Options: `None`, `"cpu"`, `"bpu"`, `["cpu", "bpu"]`. `"cpu"` = X86 side, `"bpu"` = board side. |
| `key` | `Optional[str]` | Unique board-side key. Required when `device` includes `"bpu"`. |

### HTensor Properties

| Property | Access | Description |
|----------|--------|-------------|
| `data` | get/set | Tensor data. When setting, new data type must match original if original was not `None`. |
| `device` | get only | Storage device info. Immutable after construction. |
| `key` | get only | Board-side unique key. Only meaningful when `device` includes `"bpu"`. Immutable after construction. |
| `shape` | get only | Tensor shape. Auto-maintained by the tool. Immutable. |

## output_config Parameter

The `output_config` parameter in `HbmRpcSession.__call__()` controls output transmission behavior.

**Type**: `Dict[str, Dict[str, Any]]`

- **First-level keys**: Model output tensor names
- **Second-level keys**:
  - `"device"`: Where to store the output. Same semantics as HTensor's `device`.
  - `"key"`: Board-side unique key. Same semantics as HTensor's `key`. Optional.

Outputs configured in `output_config` return as `HTensor`. Unconfigured outputs return as `np.ndarray` or `torch.Tensor` (matching input type).

## Optimization Scenarios with Code

### 1. Fixed/Periodic Input

When model inputs don't change every frame, cache them on the board. Only the first frame (or frames after data updates) transfers data.

```python
import torch
import logging
from hbm_infer.hbm_rpc_session import HbmRpcSession, HTensor, logger

def periodic_input_update(epoch: int = 50):
    session = HbmRpcSession(host=<available_ip>, local_hbm_path=<local_hbm_path>)
    try:
        # Wrap fixed input with HTensor
        fixed_img = HTensor(
            data=torch.ones((1, 3, 224, 224), dtype=torch.int8),
            device=["cpu", "bpu"],  # Both X86 and board copies
            key="model.input_0",    # Unique board-side key
        )

        input = {"img": fixed_img}

        for e in range(epoch):
            print(f"Epoch: {e}")

            # Update img every 10 frames — only changed frames transfer data
            if e % 10 == 0:
                fixed_img.data = torch.ones((1, 3, 224, 224), dtype=torch.int8)

            output = session(data=input)

            for k, v in output.items():
                print(k, v.shape)
    finally:
        session.close_server()

if __name__ == "__main__":
    logger.setLevel(logging.DEBUG)
    periodic_input_update(epoch=50)
```

**Key constraint**: For fixed/periodic inputs, `device` must be `["cpu", "bpu"]`.

### 2. Output Filtering

When model outputs are not needed on X86, filter them to avoid unnecessary transfer.

```python
import torch
import logging
from hbm_infer.hbm_rpc_session import HbmRpcSession, HTensor, logger

def output_discard():
    session = HbmRpcSession(host=<available_ip>, local_hbm_path=<local_hbm_path>)
    try:
        input = {
            "input_0": torch.ones((4, 1024, 1024), dtype=torch.float32),
            "input_1": torch.ones((4, 1024, 1024), dtype=torch.float32),
        }

        # Configure output_config to filter unused outputs
        output_config = {
            # output_0 and output_1: not configured → normal return
            # output_2: filtered — not transferred, not stored on board
            "output_2": {"device": None}
        }

        output = session(data=input, output_config=output_config)

        print(type(output["output_0"]))  # <class 'torch.Tensor'>
        print(type(output["output_1"]))  # <class 'torch.Tensor'>
        print(type(output["output_2"]))  # <class 'hbm_infer.utils.HTensor'>
        print(output["output_2"].data)   # None — data not transferred
        print(output["output_2"].shape)  # (4, 1024, 1024) — shape always available
    finally:
        session.close_server()

if __name__ == "__main__":
    logger.setLevel(logging.DEBUG)
    output_discard()
```

### 3. Model Chaining

In multi-model scenarios, pass intermediate outputs directly between models on the board without transferring back to X86.

```python
import torch
import logging
from hbm_infer.hbm_rpc_session import HbmRpcSession, HTensor, logger

def model_chaining():
    session = HbmRpcSession(host=<available_ip>, local_hbm_path=<local_hbm_path>)
    try:
        # Check model names — model names ≠ HBM file names
        print(session.get_model_names())

        # Model0: keep output_0 on board
        model0_input = {"input_0": torch.ones((4, 1024, 1024), dtype=torch.float32)}
        model0_output_config = {
            "output_0": {"device": "bpu", "key": "model0.output_0"}
        }

        model0_output = session(
            data=model0_input, output_config=model0_output_config, model_name="model0"
        )

        # model0_output["output_0"] is HTensor
        print(type(model0_output["output_0"]))  # <class 'hbm_infer.utils.HTensor'>
        print(model0_output["output_0"].data)    # None — not transferred back
        print(model0_output["output_0"].shape)   # (4, 1024, 1024) — shape available

        # Model1: use model0's output directly as input — no data transfer
        model1_input = {"input_0": model0_output["output_0"]}
        model1_output = session(data=model1_input, model_name="model1")

        print(type(model1_output["output_0"]))  # <class 'torch.Tensor'>
    finally:
        session.close_server()

if __name__ == "__main__":
    logger.setLevel(logging.DEBUG)
    model_chaining()
```

### 4. Comprehensive Pipeline

Combines periodic input update, output filtering, and model chaining.

```python
import torch
import logging
from hbm_infer.hbm_rpc_session import HbmRpcSession, HTensor, logger

def test_pipeline(epoch=50):
    session = HbmRpcSession(host=<available_ip>, local_hbm_path=<pipeline_hbm_path>)
    try:
        print(f"Model list: {session.get_model_names()}")

        # Periodic input for model1
        model1_fixed_input1 = HTensor(
            data=torch.ones((4, 1024, 1024), dtype=torch.float32) * 2,
            device=["cpu", "bpu"],
            key="model1.input_1",
        )

        for e in range(epoch):
            print(f"Epoch: {e}")

            # Model0: normal input
            model0_input = {"input_0": torch.ones((4, 1024, 1024), dtype=torch.float32) * -1}
            model0_output_config = {"output_0": {"device": "bpu", "key": "model0.output_0"}}
            model0_output = session(
                data=model0_input, output_config=model0_output_config, model_name="model0"
            )

            # Update model1's fixed input periodically
            if e % 10 == 0:
                model1_fixed_input1.data = torch.ones((4, 1024, 1024), dtype=torch.float32) * 2

            model1_input = {
                "input_0": model0_output["output_0"],  # Chained from model0
                "input_1": model1_fixed_input1,         # Periodic input
            }
            model1_output_config = {
                "output_0": {"device": None},                      # Filtered out
                # output_1: not configured → normal return
                "output_2": {"device": ["bpu", "cpu"], "key": "model1.output2"},  # Stored on board AND returned
            }

            model1_output = session(
                data=model1_input, output_config=model1_output_config, model_name="model1"
            )

            # Model2: use model1's board-side output
            model2_input = {"input_0": model1_output["output_2"]}
            model2_output = session(data=model2_input, model_name="model2")
            print(f"{torch.all(model2_output['output_0'] == 1)}")

    finally:
        session.close_server()

if __name__ == "__main__":
    logger.setLevel(logging.DEBUG)
    test_pipeline(epoch=100)
```

## device Values Summary

| device Value | Meaning | Use Case |
|-------------|---------|----------|
| `None` | No storage | Output filtering — discard |
| `"cpu"` | X86 side only | Not typically used directly |
| `"bpu"` | Board side only | Model chaining intermediate output |
| `["cpu", "bpu"]` | Both X86 and board | Fixed/periodic input caching |
| `["bpu", "cpu"]` | Both board and X86 | Store on board AND return to X86 |
