import cv2
import pandas as pd
import numpy as np
from pathlib import Path
import glob
import os

# ======================================================
# config 読み込み
# ======================================================

def read_config(path="config.xlsx"):
    df = pd.read_excel(path, header=None)
    cfg = dict(zip(df[0], df[1]))

    # 型補正
    cfg["camera_fps"] = float(cfg["camera_fps"])
    cfg["fpga_sampling_hz"] = float(cfg["fpga_sampling_hz"])
    cfg["trigger_fpga_count"] = int(cfg["trigger_fpga_count"])
    cfg["frame_start"] = int(cfg["frame_start"])
    cfg["frame_end"] = int(cfg["frame_end"])
    cfg["circle_radius"] = int(cfg["circle_radius"])
    cfg["font_scale"] = float(cfg["font_scale"])
    cfg["line_thickness"] = int(cfg["line_thickness"])
    cfg["draw_label"] = str(cfg["draw_label"]).upper() == "TRUE"
    cfg["draw_scale"] = int(cfg["draw_scale"])


    return cfg


# ======================================================
# FPGA parser（既存ロジック移植）
# ======================================================

def extract_hex64_list(lines, start_marker):
    hex_list = []
    start_idx = None

    for i, line in enumerate(lines):
        if start_marker in line:
            start_idx = i
            break

    if start_idx is None:
        return []

    data_lines = []
    for line in lines[start_idx + 1:]:
        line = line.strip()
        if not line or line.startswith("XMD%"):
            break

        if ":" in line:
            data_lines.append(line.split(":")[1].strip())

    for i in range(0, len(data_lines) - 1, 2):
        lower = data_lines[i]
        upper = data_lines[i + 1]
        hex64 = upper.zfill(8) + lower.zfill(8)
        hex_list.append(hex64)

    return hex_list


def parse_fpga_log(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    value_hex = extract_hex64_list(lines, "XMD% mrd 0x40000000")
    time_hex = extract_hex64_list(lines, "XMD% mrd 0x42000000")

    n = min(len(value_hex), len(time_hex))
    records = []

    for i in range(n):
        v = int(value_hex[i], 16)
        t = int(time_hex[i], 16)

        bits = [int(b) for b in bin(v)[2:].zfill(64)][::-1]

        records.append({
            "time": t,
            "bits": bits
        })

    return records


# ======================================================
# 時刻取得（step / hold方式）
# ======================================================

def get_bits_at_time(records, t):

    times = np.array([r["time"] for r in records])

    # t 以下で最後のイベントを取得
    idx = np.searchsorted(times, t, side="right") - 1

    # t が最初の記録より前の場合
    if idx < 0:
        return records[0]["bits"]

    return records[idx]["bits"]



# ======================================================
# IP位置読み込み
# ======================================================

def load_ip_position(path):
    df = pd.read_csv(path)

    df["idx"] = df["IP"].str.replace("D", "").astype(int) - 1
    return df


# ======================================================
# 描画
# ======================================================

def draw_ip_overlay(img, ip_df, bits, cfg):

    on_color = tuple(map(int, str(cfg["on_color"]).split(",")))
    off_color = tuple(map(int, str(cfg["off_color"]).split(",")))

    for _, row in ip_df.iterrows():

        idx = row["idx"]
        x = int((row["x"] * cfg["mm_to_px_ax"] + cfg["mm_to_px_bx"]) * cfg["draw_scale"])
        y = int((row["y"] * cfg["mm_to_px_ay"] + cfg["mm_to_px_by"]) * cfg["draw_scale"])

        color = on_color if bits[idx] == 1 else off_color

        cv2.circle(
            img,
            (x, y),
            cfg["circle_radius"] * cfg["draw_scale"],
            color,
            -1
        )

        if cfg["draw_label"]:
            cv2.putText(
                img,
                row["IP"],
                (x + 5, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                cfg["font_scale"],
                color,
                cfg["line_thickness"]
            )

    return img


# ======================================================
# main
# ======================================================

def main():

    cfg = read_config()

    print("config loaded")

    records = parse_fpga_log(cfg["fpga_log_file"])

    records = [r for r in records if r["time"] > 0]
    records = sorted(records, key=lambda r: r["time"])

    print("fpga parsed:", len(records))

    ip_df = load_ip_position(cfg["ip_position_csv"])

    image_dir = Path(cfg["image_dir"])
    output_dir = Path(cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    image_list = sorted(
        glob.glob(str(image_dir / f"*.{cfg['image_ext']}"))
    )

    trigger_idx = image_list.index(
        str(image_dir / cfg["trigger_frame_file"])
    )

    fs = cfg["fpga_sampling_hz"]
    fps = cfg["camera_fps"]

    trigger_fpga_count = cfg["trigger_fpga_count"]

    print("start rendering...")

    for i in range(cfg["frame_start"], cfg["frame_end"] + 1):

        if i >= len(image_list):
            break

        img_path = image_list[i]
        img = cv2.imdecode(
            np.fromfile(img_path, dtype=np.uint8),
            cv2.IMREAD_COLOR
        )

        scale = cfg["draw_scale"]

        img = cv2.resize(
            img,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_LINEAR
        )

        # frame → FPGA時間
        dt_frame = i - trigger_idx
        t_fpga = trigger_fpga_count + dt_frame * fs / fps

        bits = get_bits_at_time(records, t_fpga)

        img = draw_ip_overlay(img, ip_df, bits, cfg)

        img = cv2.resize(
            img,
            None,
            fx=1.0 / scale,
            fy=1.0 / scale,
            interpolation=cv2.INTER_AREA
        )

        out_name = Path(img_path).name
        out_path = output_dir / out_name

        ext = out_path.suffix  # ".jpg" など

        result, encoded = cv2.imencode(ext, img)

        if result:
            encoded.tofile(str(out_path))
        else:
            print("save failed:", out_path)

        if i % 100 == 0:
            print("frame:", i)

    print("done.")


if __name__ == "__main__":
    main()
