
import sys

filename = sys.argv[1]

with open(filename, 'r', encoding='utf-8') as f:
    lines = f.readlines()

stack = []
for i, line in enumerate(lines):
    line_num = i + 1
    for char in line:
        if char == '{':
            stack.append(line_num)
        elif char == '}':
            if not stack:
                print(f"Error: Unexpected '}}' at line {line_num}")
                sys.exit(1)
            stack.pop()

if stack:
    print(f"Error: Unclosed '{{' at line {stack[-1]}")
    # Print the last few unclosed braces
    print("Unclosed braces stack (last 5):", stack[-5:])
else:
    print("Braces are balanced.")
