import re

line = '第1章 - 乱葬岗：残次'
regex = r"^[#*\s]*第\s*(\d+)\s*章"
match = re.match(regex, line)

print(f"Line: '{line}'")
print(f"Regex: '{regex}'")
print(f"Match: {match}")
if match:
    print(f"Group 1: {match.group(1)}")

# Test with potential BOM or hidden chars
line_with_bom = '\ufeff第1章'
match_bom = re.match(regex, line_with_bom)
print(f"Match BOM: {match_bom}")

# Test with markdown
line_md = "### 第1章"
match_md = re.match(regex, line_md)
print(f"Match MD: {match_md}")
