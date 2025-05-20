import re

input_file = "data/books.yaml"
output_file = "data/books_fixed.yaml"

with open(input_file, "r", encoding="utf-8") as f:
    content = f.read()

# 只匹配行首或缩进后的 No:，替换为 "No":
fixed_content = re.sub(r'(^|\s)(No):', r'\1"No":', content)

with open(output_file, "w", encoding="utf-8") as f:
    f.write(fixed_content)

print(f"已处理完毕，结果写入：{output_file}")
