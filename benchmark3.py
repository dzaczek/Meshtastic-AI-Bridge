import timeit
import re
import string
import random

# Generating large content
content = ''.join(random.choices(string.ascii_letters + string.digits, k=100000))
content += " The temperature today is 25°C " + ''.join(random.choices(string.ascii_letters + string.digits, k=100000))

def test_uncompiled():
    temp_patterns = [
        r'(\d+)\s*°[CF]',
        r'(\d+)\s*degrees',
        r'temperature[:\s]*(\d+)',
    ]
    for pattern in temp_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)

RE_TEMP_PATTERNS = [
    re.compile(r'(\d+)\s*°[CF]', re.IGNORECASE),
    re.compile(r'(\d+)\s*degrees', re.IGNORECASE),
    re.compile(r'temperature[:\s]*(\d+)', re.IGNORECASE),
]

def test_compiled():
    for pattern in RE_TEMP_PATTERNS:
        matches = pattern.findall(content)

uncompiled_time = timeit.timeit(test_uncompiled, number=100)
compiled_time = timeit.timeit(test_compiled, number=100)

print(f"Uncompiled Time: {uncompiled_time:.6f} s")
print(f"Compiled Time: {compiled_time:.6f} s")
print(f"Improvement: {(uncompiled_time - compiled_time) / uncompiled_time * 100:.2f}%")
