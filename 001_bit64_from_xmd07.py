import streamlit as st
import pandas as pd
import os
from pathlib import Path

# --- config.xlsx から設定を読み込む関数 ---
def read_config():
    config = pd.read_excel("config.xlsx", header=None)
    config_dict = dict(zip(config[0], config[1]))
    input_path = config_dict["bit64_input_textfile"]
    output_path = config_dict["bit64_output_excel"]
    return input_path, output_path

# --- テキスト行から HEX64 を抽出する関数 ---
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
    for line in lines[start_idx+1:]:
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

# --- Streamlit アプリ本体 ---
st.title("bit64変換ツール - Streamlitランチャー")

# セッション状態の初期化
if "bit64_overwrite_confirmed" not in st.session_state:
    st.session_state.bit64_overwrite_confirmed = False
if "bit64_converted_df" not in st.session_state:
    st.session_state.bit64_converted_df = None

# 設定読み込みと表示
try:
    input_path, output_path = read_config()
    st.subheader("設定内容の確認")
    st.write("**入力ファイル:**", input_path)
    st.write("**出力ファイル:**", output_path)
except Exception as e:
    st.error(f"config.xlsx の読み込みに失敗しました: {e}")
    st.stop()

# 変換処理
if st.button("変換を実行"):
    st.info("変換処理を開始します...")

    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    value_hex_list = extract_hex64_list(lines, "XMD% mrd 0x40000000 65000")
    time_hex_list  = extract_hex64_list(lines, "XMD% mrd 0x42000000 65000")

    min_len = min(len(value_hex_list), len(time_hex_list))
    records = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    for i in range(min_len):
        value_int = int(value_hex_list[i], 16)
        value_bits = [int(b) for b in bin(value_int)[2:].zfill(64)][::-1]
        time_dec = int(time_hex_list[i], 16)
        record = [i, time_hex_list[i], time_dec, value_hex_list[i].upper()] + value_bits
        records.append(record)

        if i % max(min_len // 100, 1) == 0:
            progress_bar.progress(i / min_len)
            status_text.text(f"{i} / {min_len} レコード処理中...")

    columns = ["data_index", "time_hex", "time_dec", "value_hex"] + [f"b{i}" for i in range(64)]
    df = pd.DataFrame(records, columns=columns)
    st.session_state.bit64_converted_df = df
    st.success("変換処理が完了しました。出力の確認を行ってください。")
    progress_bar.progress(1.0)

# 保存処理
if st.session_state.bit64_converted_df is not None:
    if os.path.exists(output_path) and not st.session_state.bit64_overwrite_confirmed:
        if st.button("⚠ 出力ファイルが既に存在します。上書きしますか？"):
            st.session_state.bit64_overwrite_confirmed = True

    if not os.path.exists(output_path) or st.session_state.bit64_overwrite_confirmed:
        st.session_state.bit64_converted_df.to_excel(output_path, index=False)
        st.success(f"✅ 出力完了: {output_path}")
        # 後処理
        st.session_state.bit64_converted_df = None
        st.session_state.bit64_overwrite_confirmed = False
