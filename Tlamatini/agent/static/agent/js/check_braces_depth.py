
import sys

filename = sys.argv[1]

milestones = [1818, 5083, 5500, 5509, 5532]

with open(filename, 'r', encoding='utf-8') as f:
    lines = f.readlines()

stack = []
for i, line in enumerate(lines):
    line_num = i + 1
    
    # Check milestones before processing the line (except for closing braces which affect state after?)
    # Actually, let's print state AT the line.
    
    for char in line:
        if char == '{':
            stack.append(line_num)
        elif char == '}':
            if stack:
                stack.pop()
    
    if line_num in milestones:
        print(f"Line {line_num}: Depth = {len(stack)}")
        if len(stack) > 0:
            print(f"  Top of stack: {stack[-1]}")
