#!/bin/bash

# 目标目录 (可以修改为您自己的目录)
DIR="content/en"

# 查找所有 .md 文件
find $DIR -type f -name "*.md" | while read file; do
  echo "Processing: $file"
  
  # 提取文件的前 3 行作为 frontmatter
  FRONTMATTER=$(head -n 20 "$file" | sed '/^---$/,$d')

  # 如果文件有 YAML frontmatter
  if [[ "$FRONTMATTER" =~ ^--- ]]; then
    # 修复 "categories" -> "tags"
    sed -i '/^categories:/s/^categories:/tags:/' "$file"
    
    # 删除无效字段，如 "boomdevs_metabox"
    sed -i '/boomdevs_metabox:/,/^$/d' "$file"

    # 处理冒号后面的空格问题
    sed -i 's/^\([a-zA-Z0-9_-]\+\):\([^\n]*\)/\1: \2/' "$file"

    # 确保冒号后面有空格
    sed -i 's/^\([a-zA-Z0-9_-]\+\):\([^\n]*\)/\1: \2/' "$file"

    # 确保 YAML 中的键值对格式正确
    sed -i 's/\([a-zA-Z0-9_-]\+\)[ \t]*:/\1: /g' "$file"
  fi
  
done

echo "Finished processing all files!"
