import os
import re
from collections import defaultdict

import pandas as pd

# ======== 需要你根据实际情况修改的三个路径 ========
excel_path = r"../data/附件2_GPRS核查国际漫游GN简表-20250805.xls" # Excel 文件路径
txt_path = r"../data/FW_Extract_CIDR.txt" # 原始 txt 文件路径
out_path= r"../data/比较结果.txt" # 输出结果 txt 文件路径
# =================================================


def normalize_net(net: str) -> str:
    """
    将网段字符串标准化：
    - 去掉所有空白字符（空格、制表符等）
    例如: "94. 201.225.0/24" -> "94.201.225.0/24"
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

    # 优先用列名；否则退回按列号
    if "运营商简拼" in df.columns and "GN网段" in df.columns:
        op_col = df["运营商简拼"]
        gn_col = df["GN网段"]
    else:
        op_col = df.iloc[:, 2]  # C 列
        gn_col = df.iloc[:, 7]  # H 列

    # **关键一步：向下填充运营商简拼**
    op_col = op_col.ffill()

    excel_map = defaultdict(set)  # {op: set(标准化网段)}

    for op, gn_cell in zip(op_col, gn_col):
        if pd.isna(gn_cell):
            # 没有 GN 网段就跳过
            continue

        op = str(op).strip()
        if not op:
            continue

        # 一行里可能有多段（有换行的情况），拆开
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
            net = m.group(1).strip()   # txt 里的原始网段，保留原样
            op = m.group(2).strip()
            if op and net:
                txt_map[op].add(net)

    return txt_map


def main():
    # 1. 载入 Excel 信息
    excel_map = load_excel_gn_map(excel_path, sheet_name="国际Gn简表")

    # 2. 载入 txt 信息
    txt_map = load_txt_gn_map(txt_path)

    # 3. 比对：
    #    - 若 op 在 Excel 中存在：比较“标准化后的网段”
    #    - 若 op 不在 Excel 中：视 Excel 网段集合为空 -> 全部输出
    diff_result = {}  # {op: [原始网段1, 原始网段2, ...]}

    for op, nets_in_txt in txt_map.items():
        excel_nets_norm = excel_map.get(op, set())  # 标准化后的集合

        diff_nets = []
        for net in nets_in_txt:
            net_norm = normalize_net(net)
            if net_norm not in excel_nets_norm:
                diff_nets.append(net)

        if diff_nets:
            diff_result[op] = sorted(diff_nets)

    # 4. 写出结果到新的 txt 文件
    with open(out_path, "w", encoding="utf-8") as f:
        for op in sorted(diff_result.keys()):
            f.write(f"{op}\n")
            for net in diff_result[op]:
                f.write(f"{net}\n")
            f.write("\n")  # 运营商之间空一行

    print("完成！不匹配的 GN 网段已输出到：", out_path)


if __name__ == "__main__":
    main()
