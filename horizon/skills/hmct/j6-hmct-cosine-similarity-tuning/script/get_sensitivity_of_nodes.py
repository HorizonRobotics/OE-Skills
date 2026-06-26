import argparse
from hmct.quantizer.debugger import select_sensitive_samples, get_sensitivity_of_nodes
import logging
logging.basicConfig(level=logging.INFO)

def parse_args():
    parser = argparse.ArgumentParser(description="HMCT select badcase")
    parser.add_argument(
        "--calibrated_model_path",
        default="",
        help="输入校准模型路径",
    )
    parser.add_argument(
        "--cali_data_dir",
        default="",
        help="校准数据目录（其下子目录名需与输入名一致）",
    )
    parser.add_argument(
        "--metric",
        default="cosine-similarity",
        help="选择badcase使用的metric",
    )
    parser.add_argument(
        "--num_sample",
        type=int,
        default=1,
        help="找到TopN的badcase",
    )
    parser.add_argument(
        "--save_dir",
        default="./",
        help="敏感度结果保存目录",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()

    logging.info("Start select bad case")
    badcase_dataset = select_sensitive_samples(
        calibrated_model=args.calibrated_model_path,
        calibration_data=args.cali_data_dir,
        metric=args.metric,
        num_sample=args.num_sample,
    )

    get_sensitivity_of_nodes(
        args.calibrated_model_path,
        calibrated_data=badcase_dataset,
        metrics=args.metric,
        output_node=None,
        data_num=None,
        verbose=True,
        save_dir=args.save_dir,
    )


if __name__ == "__main__":
    main()