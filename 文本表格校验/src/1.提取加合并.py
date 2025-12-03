import os
import re

DATA_DIR = r"..\data"  # 根据实际情况修改路径

# 正则：抓取行内的前缀、IP、wildcard 值和后缀
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
                # 如果之前已经在一个 block 里，可以视情况决定是否先保存
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

    # 理论上不需要这个（因为必须遇到#才算结束），但以防万一
    if in_block and current_block:
        blocks.append("".join(current_block))

    return blocks

def wildcard_to_prefixlen(wc: str) -> int:
    """
    将 wildcard（反掩码，如 0.0.0.7 或 0）转换为前缀长度（如 29、32）
    规则：掩码 = 255 - wildcard，每个字节数 1 的个数之和就是前缀长度
    """
    wc = wc.strip()
    # 兼容只有一个 "0" 的情况，视为 0.0.0.0
    if wc == "0":
        octets = [0, 0, 0, 0]
    else:
        parts = wc.split(".")
        # 不足 4 段的也补成 4 段（通常不会发生，但以防万一）
        parts = (parts + ["0"] * 4)[:4]
        octets = [int(x) for x in parts]

    # 反掩码 -> 正常子网掩码
    mask_octets = [255 - o for o in octets]
    # 统计子网掩码中所有位为 1 的个数
    prefix_len = sum(bin(o).count("1") for o in mask_octets)
    return prefix_len

def convert_line(line: str) -> str:
    """
    如果行中包含
    'address ... IP wildcard xxx ...'
    则改成
    'address ... IP/前缀 ...'
    否则原样返回
    """
    m = LINE_PATTERN.match(line.rstrip("\n"))
    if not m:
        return line  # 不匹配 address + wildcard 的行原样返回

    prefix = m.group("prefix")
    ip = m.group("ip")
    wc = m.group("wc")
    suffix = m.group("suffix")

    prefix_len = wildcard_to_prefixlen(wc)
    # 重新拼接行：去掉 "wildcard xxx"，改成 IP/前缀
    new_line = f"{prefix}{ip}/{prefix_len}{suffix}\n"
    return new_line

def process_all_txt_files(data_dir):
    for filename in os.listdir(data_dir):
        if not filename.lower().endswith(".txt"):
            continue

        old_path = os.path.join(data_dir, filename)
        base_name = os.path.splitext(filename)[0]  # 获取文件名（去除扩展名）

        # 提取段落
        blocks = extract_blocks_from_file(old_path)

        if not blocks:
            print(f"{filename} 中未找到匹配段落，跳过。")
            continue

        # 写入新的文件：xxx_Extract.txt
        new_filename = f"{base_name}_Extract.txt"
        new_path = os.path.join(data_dir, new_filename)

        with open(new_path, "w", encoding="utf-8") as f:
            f.write("\n".join(blocks))

        # 生成新的文件名并处理掩码合并
        out_filename = f"{base_name}_Extract_CIDR.txt"
        out_path = os.path.join(data_dir, out_filename)

        with open(new_path, "r", encoding="utf-8") as fin, \
             open(out_path, "w", encoding="utf-8") as fout:
            for line in fin:
                new_line = convert_line(line)
                fout.write(new_line)

        os.remove(new_path)
        print(f"已生成文件: {out_path}")

if __name__ == "__main__":
    process_all_txt_files(DATA_DIR)
