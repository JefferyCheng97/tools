# -*- coding: utf-8 -*-
import os
import re
from collections import defaultdict

import pandas as pd

# data 目录：放 原始 txt 和 Excel
DATA_DIR = r".\data"

# Excel 文件路径
excel_path = os.path.join(DATA_DIR, "internationalgn.xls")

# ========= 提取段落且 wildcard 转 CIDR =========
LINE_PATTERN = re.compile(
    r'^(?P<prefix>\s*address\s+\d+\s+)'      # address 开头到 IP 之前
    r'(?P<ip>\d+\.\d+\.\d+\.\d+)\s+'         # IP 地址
    r'wildcard\s+(?P<wc>\S+)'                # wildcard 后面的通配符掩码
    r'(?P<suffix>.*)$'                       # 后面的 description 等
)

def extract_blocks_from_file(filepath):
    """
    从单个文件中提取以 'ip address-set internationalgn' 开头，
    以单独一行 '#' 结束的所有段落，返回这些段落的列表。
    """
    blocks = []
    current_block = []
    in_block = False

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()

            # 判断段落开始
            if stripped.startswith("ip address-set internationalgn"):
                if in_block and current_block:
                    blocks.append("".join(current_block))
                    current_block = []

                in_block = True
                current_block.append(line)
                continue

            # 如果已经在一个 block 里，就持续记录
            if in_block:
                current_block.append(line)
                # 判断段落结束: 一行只有一个 '#'
                if stripped == "#":
                    blocks.append("".join(current_block))
                    current_block = []
                    in_block = False

    if in_block and current_block:
        blocks.append("".join(current_block))

    return blocks


def wildcard_to_prefixlen(wc: str) -> int:
    """
    将 wildcard（反掩码，如 0.0.0.7 或 0）转换为前缀长度（如 29、32）
    """
    wc = wc.strip()
    if wc == "0":
        octets = [0, 0, 0, 0]
    else:
        parts = wc.split(".")
        parts = (parts + ["0"] * 4)[:4]
        octets = [int(x) for x in parts]

    mask_octets = [255 - o for o in octets]
    prefix_len = sum(bin(o).count("1") for o in mask_octets)
    return prefix_len


def convert_line(line: str) -> str:
    """
    把
      address ... IP wildcard xxx ...
    转成
      address ... IP/前缀 ...
    """
    m = LINE_PATTERN.match(line.rstrip("\n"))
    if not m:
        return line

    prefix = m.group("prefix")
    ip = m.group("ip")
    wc = m.group("wc")
    suffix = m.group("suffix")

    prefix_len = wildcard_to_prefixlen(wc)
    new_line = f"{prefix}{ip}/{prefix_len}{suffix}\n"
    return new_line


def process_all_txt_files(data_dir):
    """
    扫描 data_dir 下所有 .txt 文件：
      1) 提取 internationalgn 段落到 *_Extract.txt
      2) 转换 wildcard 为 CIDR 到 *_Extract_CIDR.txt
    返回：所有生成的 *_Extract_CIDR.txt 的完整路径列表
    """
    generated_cidr_files = []

    for filename in os.listdir(data_dir):
        if not filename.lower().endswith(".txt"):
            continue

        old_path = os.path.join(data_dir, filename)
        base_name = os.path.splitext(filename)[0]

        blocks = extract_blocks_from_file(old_path)
        if not blocks:
            print(f"{filename} 中未找到匹配段落，跳过。")
            continue

        # 先写入 *_Extract.txt
        new_filename = f"{base_name}_Extract.txt"
        new_path = os.path.join(data_dir, new_filename)

        with open(new_path, "w", encoding="utf-8") as f:
            f.write("\n".join(blocks))

        # 再生成 *_Extract_CIDR.txt
        out_filename = f"{base_name}_Extract_CIDR.txt"
        out_path_local = os.path.join(data_dir, out_filename)

        with open(new_path, "r", encoding="utf-8") as fin, \
             open(out_path_local, "w", encoding="utf-8") as fout:
            for line in fin:
                new_line = convert_line(line)
                fout.write(new_line)

        os.remove(new_path)
        generated_cidr_files.append(out_path_local)
        print(f"已生成文件: {out_path_local}")

    return generated_cidr_files


# ========= Excel vs TXT 比较 =========
def normalize_net(net: str) -> str:
    """
    将网段字符串标准化：
    - 去掉所有空白字符
    """
    if net is None:
        return ""
    return re.sub(r"\s+", "", net)


def safe_read_excel(path, sheet_name):
    """
    根据扩展名自动选择引擎，兼容 xls / xlsx
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        return pd.read_excel(path, sheet_name=sheet_name,
                             engine="openpyxl", dtype=str)
    elif ext == ".xls":
        return pd.read_excel(path, sheet_name=sheet_name,
                             engine="xlrd", dtype=str)
    else:
        raise ValueError(f"不支持的 Excel 格式: {ext}")


def load_excel_gn_map(path, sheet_name="国际Gn简表"):
    """
    从 Excel 中读取 运营商简拼(C列) 和 GN网段(H列)，
    返回: { 简拼: set([标准化后的GN网段1, ...]) }
    """
    df = safe_read_excel(path, sheet_name=sheet_name)

    if "运营商简拼" in df.columns and "GN网段" in df.columns:
        op_col = df["运营商简拼"]
        gn_col = df["GN网段"]
    else:
        op_col = df.iloc[:, 2]  # C列
        gn_col = df.iloc[:, 7]  # H列

    op_col = op_col.ffill()

    excel_map = defaultdict(set)

    for op, gn_cell in zip(op_col, gn_col):
        if pd.isna(gn_cell):
            continue

        op = str(op).strip()
        if not op:
            continue

        for part in str(gn_cell).splitlines():
            raw_net = part.strip()
            if not raw_net:
                continue
            norm_net = normalize_net(raw_net)
            if norm_net:
                excel_map[op].add(norm_net)

    return excel_map


def load_txt_gn_map(path):
    """
    从 txt 中读取：
       address ... <IP/掩码> description <运营商简拼>
    返回: { 简拼: set([txt中原始网段1, ...]) }
    """
    pattern = re.compile(
        r"\b(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\b.*?\bdescription\s+(\S+)",
        re.IGNORECASE
    )

    txt_map = defaultdict(set)

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.search(line)
            if not m:
                continue
            net = m.group(1).strip()
            op = m.group(2).strip()
            if op and net:
                txt_map[op].add(net)

    return txt_map


def compare_and_output(excel_path, txt_path, out_path):
    """
    读取 Excel & txt，输出：
    1) Excel 中存在的运营商，但网段不一致的内容
    2) txt 中存在但 Excel 中不存在的运营商
    并用分割线隔开
    """
    print(f"开始比较文件：{os.path.basename(txt_path)}")
    print("  从 Excel 载入运营商网段...")
    excel_map = load_excel_gn_map(excel_path, sheet_name="国际Gn简表")

    print("  从 TXT 载入网段...")
    txt_map = load_txt_gn_map(txt_path)

    diff_exist = {}      # Excel 中存在，但网段不同
    diff_not_exist = {}  # Excel 中不存在的运营商（全部输出）

    for op, nets_in_txt in txt_map.items():
        if op not in excel_map:
            # Excel 中没有该运营商 → 全部作为异常输出
            diff_not_exist[op] = sorted(list(nets_in_txt))
            continue

        # Excel 中存在 → 检查网段差异
        excel_nets_norm = {normalize_net(n) for n in excel_map[op]}
        diff_nets = []

        for net in nets_in_txt:
            if normalize_net(net) not in excel_nets_norm:
                diff_nets.append(net)

        if diff_nets:
            diff_exist[op] = sorted(diff_nets)

    # ========= 写入最终结果 =========
    with open(out_path, "w", encoding="utf-8") as f:

        # 第一部分：运营商存在于 Excel，但是网段不一致
        f.write("【Excel存在的运营商】\n")
        for op in sorted(diff_exist.keys()):
            f.write(f"{op}\n")
            for net in diff_exist[op]:
                f.write(f"{net}\n")
            f.write("\n")

        # 分割线
        f.write("=========================================================\n")
        f.write("=========================================================\n\n")

        # 第二部分：Excel 中不存在的运营商
        f.write("【Excel中不存在的运营商】\n")
        for op in sorted(diff_not_exist.keys()):
            f.write(f"{op}\n")
            for net in diff_not_exist[op]:
                f.write(f"{net}\n")
            f.write("\n")

    print("  完成！比较结果已输出：", out_path)


def main():
    print("=== 第一步：处理所有 txt，提取段落并转换 wildcard 为 CIDR ===")
    cidr_files = process_all_txt_files(DATA_DIR)

    print("=== 第二步：Excel vs TXT 比较，输出不一致网段 ===")
    for cidr_path in cidr_files:
        base = os.path.splitext(os.path.basename(cidr_path))[0]
        out_path = os.path.join(DATA_DIR, f"{base}_比较结果.txt")
        compare_and_output(excel_path, cidr_path, out_path)

    input("全部完成，按回车键退出...")


if __name__ == "__main__":
    main()
